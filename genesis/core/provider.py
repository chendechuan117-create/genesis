"""
LLM 提供商实现
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional
import logging
import json
import os
import re
import asyncio
import time
import httpx

from .base import LLMProvider as BaseLLMProvider, LLMResponse, ToolCall

logger = logging.getLogger(__name__)


class WallClockTimeoutError(Exception):
    """LLM 调用总体超时（非 provider 故障，不应触发 failover）"""
    pass

# DeepSeek DSML 及其他模型特定控制标记的统一清洗正则
_CONTROL_MARKER_RE = re.compile(
    r'<[\uff5c|](?:DSML|tool_call|function_call)[\uff5c|][^>]*>'
    r'|</[\uff5c|](?:DSML|tool_call|function_call)[\uff5c|][^>]*>'
    r'|[\uff5c|](?:DSML|tool_call|function_call)[\uff5c|]',
    re.IGNORECASE
)


class NativeHTTPProvider(BaseLLMProvider):
    """基于原生 HTTP (httpx) 的提供商 - 高性能异步实现"""
    
    DEFAULT_STOP_SEQUENCES = ["User:", "Observation:", "用户:", "Model:", "Assistant:"]

    # ── Provider 质量漂移诊断：滑动窗口统计 ──
    _STATS_WINDOW = 100  # 滑动窗口大小
    _stats_total_calls: int = 0
    _stats_retries: int = 0
    _stats_timeouts: int = 0
    _stats_errors: int = 0
    _stats_wall_clock_timeouts: int = 0
    # 滑动窗口：每个元素是 ("ok" | "retry" | "timeout" | "error" | "wall_timeout")
    _stats_window: List[str] = []

    @classmethod
    def _record_stat(cls, event: str):
        """记录一次调用事件到滑动窗口"""
        cls._stats_window.append(event)
        if len(cls._stats_window) > cls._STATS_WINDOW:
            cls._stats_window = cls._stats_window[-cls._STATS_WINDOW:]

    @classmethod
    def get_provider_stats(cls) -> Dict[str, Any]:
        """供 heartbeat 获取 provider 质量指标（含全局累计 + 最近窗口）"""
        total = cls._stats_total_calls
        # 最近窗口统计
        w = cls._stats_window
        w_total = len(w)
        w_errors = sum(1 for e in w if e in ("error", "timeout", "wall_timeout"))
        w_retries = sum(1 for e in w if e == "retry")
        return {
            "total_calls": total,
            "retries": cls._stats_retries,
            "timeouts": cls._stats_timeouts,
            "errors": cls._stats_errors,
            "wall_clock_timeouts": cls._stats_wall_clock_timeouts,
            "retry_rate": round(cls._stats_retries / total, 3) if total > 0 else 0,
            "error_rate": round(cls._stats_errors / total, 3) if total > 0 else 0,
            "recent_window": w_total,
            "recent_error_rate": round(w_errors / w_total, 3) if w_total > 0 else 0,
            "recent_retry_rate": round(w_retries / w_total, 3) if w_total > 0 else 0,
        }

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = "https://api.deepseek.com/v1",
        default_model: str = "deepseek-chat",
        connect_timeout: int = 30,
        request_timeout: int = 180,
        read_timeout: int = 120,  # streaming 逐 chunk 超时(秒)：防止 API 停止发数据导致永久挂起
        wall_clock_timeout: int = 300,  # 整体超时(秒)：防止推理模型思考过久
        stop_sequences: Optional[List[str]] = None,
        provider_name: str = "default",
        use_proxy: bool = False,
        skip_content_type: bool = False,
        default_headers: Optional[Dict[str, str]] = None,
        ssl_verify: bool = True,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/') if base_url else "https://api.deepseek.com/v1"
        self.default_model = default_model
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout
        self.read_timeout = read_timeout
        self.wall_clock_timeout = wall_clock_timeout
        self.stop_sequences = stop_sequences if stop_sequences is not None else self.DEFAULT_STOP_SEQUENCES
        self.provider_name = provider_name
        self.use_proxy = use_proxy
        self.skip_content_type = skip_content_type
        self.default_headers = dict(default_headers or {})
        self.ssl_verify = ssl_verify
        self._http_client: Optional[httpx.AsyncClient] = None
    
    @staticmethod
    def _clean_error_text(text: str, max_len: int = 200) -> str:
        """清洗 API 错误文本：去除 HTML（如 Cloudflare 502 页面），截断过长内容"""
        if not text:
            return "(empty)"
        if "<html" in text.lower() or "<!doctype" in text.lower():
            import re
            # 尝试提取 <title> 内容作为摘要
            m = re.search(r'<title>(.*?)</title>', text, re.IGNORECASE | re.DOTALL)
            return m.group(1).strip() if m else "(HTML error page)"
        return text[:max_len] + ("..." if len(text) > max_len else "")

    def _get_http_client(self) -> httpx.AsyncClient:
        """延迟初始化的持久 httpx 客户端（复用 TCP 连接池）"""
        if self._http_client is None or self._http_client.is_closed:
            # Auto-detect proxy from env if use_proxy not explicitly set
            trust_env = self.use_proxy or bool(
                os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
                or os.environ.get("https_proxy") or os.environ.get("http_proxy")
                or os.environ.get("ALL_PROXY") or os.environ.get("all_proxy")
            )
            timeout = httpx.Timeout(
                timeout=self.request_timeout,
                connect=self.connect_timeout,
                read=self.read_timeout,
                write=30.0,
                pool=self.connect_timeout,
            )
            self._http_client = httpx.AsyncClient(
                timeout=timeout,
                trust_env=trust_env,
                verify=self.ssl_verify,
            )
        return self._http_client

    def get_default_model(self) -> str:
        """获取默认模型"""
        return self.default_model

    def _is_deepseek_reasoning_model(self) -> bool:
        """DeepSeek V4 Pro 等推理模型要求回传 thinking content"""
        model = self.default_model or ""
        return "deepseek-v4-pro" in model or "deepseek-v4-pro" in model.lower()

    # MiniMax 等模型在 assistant message 中注入的非标准字段，回传其他 API 会 400
    _STRIP_MSG_FIELDS = {"audio_content", "reasoning_details", "reasoning_content",
                         "input_sensitive", "output_sensitive", "input_sensitive_type",
                         "output_sensitive_type", "output_sensitive_int", "base_resp"}

    def _sanitize_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """清洗消息列表，修复会导致 API 400 的格式问题：
        - content 为 None/空 → 填充占位符
        - name 为空字符串 → 删除该字段
        - assistant 消息中的 name 字段 → 删除（MiniMax 注入 "MiniMax AI"，其他 API 拒绝）
        - tool_calls 中 name 为空 → 填充 'unknown'
        - 非标准字段（audio_content, reasoning_details 等）→ 删除
        - 对话中间的 system 消息 → 转为 user（K2.6/Kimi 等模型拒绝中间 system）
        """
        cleaned = []
        seen_non_system = False
        tool_call_id_map = {}
        tool_call_seq = 0
        for msg in messages:
            m = dict(msg)  # shallow copy
            role = m.get("role", "")

            # K2.6/Kimi 等模型只允许开头的 system，中间的 system → 转 user
            if role == "system":
                if seen_non_system:
                    m["role"] = "user"
                    m["content"] = f"[System] {m.get('content', '')}"
                    role = "user"
            else:
                seen_non_system = True

            # 修复空 content（xcode API 要求所有消息 content 非空非 null）
            if m.get("content") is None or m.get("content") == "":
                if role == "tool":
                    m["content"] = "(empty)"
                else:
                    m["content"] = " "

            # 修复空 name（API 拒绝空字符串）
            if "name" in m and (m["name"] is None or m["name"] == ""):
                if role == "tool":
                    m["name"] = "tool"
                else:
                    del m["name"]

            # MiniMax 注入 name="MiniMax AI" 到 assistant 消息，回传其他 API 会 400
            if role == "assistant" and "name" in m:
                del m["name"]

            # 修复 tool_calls 中的空 name
            if "tool_calls" in m and m["tool_calls"]:
                fixed_tcs = []
                for tc in m["tool_calls"]:
                    tc = dict(tc)
                    original_id = str(tc.get("id") or "tool_call")
                    tool_call_seq += 1
                    new_id = f"tool_sanitized_{tool_call_seq}"
                    tc["id"] = new_id
                    tool_call_id_map.setdefault(original_id, []).append(new_id)
                    if "function" in tc:
                        fn = dict(tc["function"])
                        if not fn.get("name"):
                            fn["name"] = "unknown"
                        tc["function"] = fn
                    fixed_tcs.append(tc)
                m["tool_calls"] = fixed_tcs

            if role == "tool":
                original_tool_call_id = str(m.get("tool_call_id") or "")
                mapped_ids = tool_call_id_map.get(original_tool_call_id)
                if mapped_ids:
                    m["tool_call_id"] = mapped_ids.pop(0)
                m.pop("name", None)

            # 清除非标准字段（MiniMax 等模型注入的额外字段）
            # DeepSeek V4 Pro reasoning mode 要求回传 reasoning_content，不能剥离
            strip_fields = NativeHTTPProvider._STRIP_MSG_FIELDS
            if role == "assistant" and m.get("reasoning_content") and self._is_deepseek_reasoning_model():
                strip_fields = [f for f in strip_fields if f != "reasoning_content"]
            for field in strip_fields:
                m.pop(field, None)

            cleaned.append(m)
        return cleaned

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        stream: bool = False,
        stream_callback: Any = None,
        **kwargs
    ) -> LLMResponse:
        """发送聊天请求 (httpx)"""
        messages = self._sanitize_messages(messages)
        model = model or self.default_model
        if model.startswith("deepseek/") and "api.deepseek.com" in (self.base_url or "").lower():
            model = model.replace("deepseek/", "")
            
        url = f"{self.base_url}/chat/completions"
        
        # Optional stop sequences and truncation limit
        stop_seqs = self.stop_sequences if "stop" not in kwargs else kwargs["stop"]
        if self.provider_name == 'groq' and len(stop_seqs) > 4:
            stop_seqs = stop_seqs[:4]
            
        request_params = {
            "model": model,
            "messages": messages,
            **kwargs
        }
        if stream:
            request_params["stream"] = True
        
        if "stop" not in request_params and stop_seqs:
             request_params["stop"] = stop_seqs
        
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = "auto"
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "NanoGenesis/1.0"
        }
        if self.default_headers:
            headers.update(self.default_headers)
        if not self.skip_content_type:
            headers["Content-Type"] = "application/json"
        
        # 复用持久 httpx 客户端（trust_env=False 在 _get_http_client 中设置）
        # ⚠️ 注意：trust_env=False 会绕过系统代理。如需翻墙访问 groq/cloudflare 等墙外免费池，
        #    参见 genesis/core/config.py:ConfigManager._apply_proxies 中的代理注入逻辑。
        client = self._get_http_client()
        NativeHTTPProvider._stats_total_calls += 1
        try:
            if stream:
                coro = self._stream_with_httpx(client, url, headers, request_params, stream_callback)
            else:
                coro = self._chat_with_httpx(client, url, headers, request_params)
            result = await asyncio.wait_for(coro, timeout=self.wall_clock_timeout)
            NativeHTTPProvider._record_stat("ok")
            return result
        except asyncio.TimeoutError:
            NativeHTTPProvider._stats_wall_clock_timeouts += 1
            NativeHTTPProvider._record_stat("wall_timeout")
            # 销毁可能处于半读状态的连接，防止复用污染连接池
            if self._http_client:
                try: await self._http_client.aclose()
                except Exception: pass
                self._http_client = None
            raise WallClockTimeoutError(
                f"LLM 调用总超时 ({self.wall_clock_timeout}s)。"
                f"推理模型可能思考过久，请简化问题或缩短上下文。"
            )

    async def _chat_with_httpx(self, client: httpx.AsyncClient, url: str, headers: Dict, params: Dict) -> LLMResponse:
        """非流式请求"""
        retries = 5
        last_exception = None
        
        for attempt in range(retries):
            try:
                if self.skip_content_type:
                    response = await client.post(url, headers=headers, content=json.dumps(params).encode())
                else:
                    response = await client.post(url, headers=headers, json=params)
                response.raise_for_status()
                return self._parse_response(response.json())
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                error_body = e.response.text
                try:
                    err_json = e.response.json()
                    error_msg = err_json.get('error', {}).get('message', error_body)
                except Exception:
                    error_msg = error_body
                # 400 偶发重试：K2.6 API 间歇性拒绝合法请求（同 payload 重发即成功）
                if status == 400 and attempt < retries - 1:
                    NativeHTTPProvider._stats_retries += 1
                    NativeHTTPProvider._record_stat("retry")
                    logger.warning(f"400 retry {attempt+1}/{retries}: {error_msg[:80]}")
                    last_exception = e
                    await asyncio.sleep(1)
                    continue
                # 5xx 瞬态错误可重试（502/503/504/524）
                # 524 = Cloudflare origin timeout, 短暂瞬态，重试通常能恢复
                if status in (502, 503, 504, 524) and attempt < retries - 1:
                    NativeHTTPProvider._stats_retries += 1
                    NativeHTTPProvider._record_stat("retry")
                    logger.warning(f"HTTP {status} (attempt {attempt+1}/{retries}): {error_msg[:100]}")
                    last_exception = e
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                # 400 诊断：记录请求关键信息
                if status == 400:
                    msgs = params.get("messages", [])
                    msgs_summary = []
                    tc_ids = []
                    result_ids = []
                    for m in msgs:
                        role = m.get("role", "?")
                        content = m.get("content")
                        tc = m.get("tool_calls")
                        if tc:
                            msgs_summary.append(f"{role}: [tc x{len(tc)} ids={[t.get('id','?')[:8] for t in tc]}]")
                            tc_ids.extend([t.get('id') for t in tc if t.get('id')])
                        elif role == "tool":
                            tid = m.get("tool_call_id", "?")
                            result_ids.append(tid)
                            msgs_summary.append(f"tool(res:{tid[:8]})")
                        elif content is None:
                            msgs_summary.append(f"{role}: [content=None]")
                        else:
                            msgs_summary.append(f"{role}: {str(content)[:40]}")
                    missing = [t for t in tc_ids if t not in result_ids]
                    orphan = [r for r in result_ids if r not in tc_ids]
                    detail = f"model={params.get('model')} | n_msgs={len(msgs)} | msgs=[{', '.join(msgs_summary)}] | tc_ids={len(tc_ids)} res_ids={len(result_ids)} missing={len(missing)} orphan={len(orphan)} | tools={len(params.get('tools',[]))} | stream={params.get('stream')}"
                    logger.warning(f"🔍 Stream 400 debug | {detail}")
                    try:
                        with open("/tmp/genesis_400_debug.log", "a") as f:
                            f.write(f"\n=== {time.strftime('%H:%M:%S')} ===\n{detail}\n")
                        with open(f"/tmp/genesis_400_payload_{int(time.time())}.json", "w") as f:
                            dump_data = {"params_keys": list(params.keys()), "model": params.get("model"),
                                        "n_msgs": len(msgs), "messages": msgs}
                            tools_raw = params.get("tools", [])
                            tools_dump = []
                            for t in tools_raw:
                                td = dict(t)
                                if "function" in td:
                                    fn = dict(td["function"])
                                    if "description" in fn and len(fn["description"]) > 200:
                                        fn["description"] = fn["description"][:200] + "...[TRUNCATED]"
                                    td["function"] = fn
                                tools_dump.append(td)
                            dump_data["tools"] = tools_dump
                            dump_data["stream"] = params.get("stream")
                            dump_data["stop"] = params.get("stop")
                            dump_data["tool_choice"] = params.get("tool_choice")
                            json.dump(dump_data, f, ensure_ascii=False, indent=1)
                    except Exception: pass
                NativeHTTPProvider._stats_errors += 1
                NativeHTTPProvider._record_stat("error")
                raise Exception(f"API Error ({status}): {self._clean_error_text(e.response.text)}")
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as e:
                logger.warning(f"httpx connection error (attempt {attempt+1}/{retries}): {e}")
                last_exception = e
                if attempt < retries - 1:
                    NativeHTTPProvider._stats_retries += 1
                    NativeHTTPProvider._record_stat("retry")
                    await asyncio.sleep(1)
                    continue
                NativeHTTPProvider._stats_timeouts += 1
                NativeHTTPProvider._record_stat("timeout")
                raise Exception(f"Network Error after {retries} retries: {e}")
            except Exception as e:
                 NativeHTTPProvider._stats_errors += 1
                 NativeHTTPProvider._record_stat("error")
                 logger.error(f"httpx unexpected error: {e}")
                 raise

        raise last_exception

    def _parse_response(self, resp_data: Dict) -> LLMResponse:
        """解析 API 响应"""
        if 'error' in resp_data:
             error_msg = resp_data['error'].get('message', str(resp_data['error']))
             raise Exception(f"API Error: {error_msg}")
             
        if 'choices' not in resp_data or not resp_data['choices']:
             raise Exception(f"Invalid API Response: Missing 'choices'. Data: {resp_data}")

        choice = resp_data['choices'][0]
        message = choice['message']
        finish_reason = choice.get('finish_reason')
        
        # 提取工具调用
        # 修复 xcode split-chunk：非流式响应也会把一个 tool call 拆成两个条目
        # 第一个有 name/id 但 arguments 为空，第二个有 arguments 但 name/id 为空
        tool_calls = []
        if 'tool_calls' in message and message['tool_calls']:
            raw_tcs = message['tool_calls']
            # 预处理：合并拆分的 tool call 条目
            merged_tcs = []
            for tc in raw_tcs:
                fn = tc.get('function', {})
                has_name = bool(fn.get('name', '').strip())
                has_args = bool(fn.get('arguments', '').strip())
                has_id = bool(tc.get('id', '').strip())
                if has_name and has_id and not has_args and merged_tcs is not None:
                    # 有 name/id 但没 args：暂存，等下一个补充
                    merged_tcs.append(tc)
                elif not has_name and not has_id and has_args and merged_tcs:
                    # 没 name/id 但有 args：合并到前一个
                    prev = merged_tcs[-1]
                    prev['function']['arguments'] = fn['arguments']
                    logger.info(f"[split-chunk fix] Merged args into tool call: {prev['function'].get('name')}")
                else:
                    merged_tcs.append(tc)

            for tc in merged_tcs:
                raw_args = tc['function'].get('arguments', '{}')
                if not raw_args or not raw_args.strip():
                    raw_args = '{}'
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    repaired = raw_args.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                    try:
                        args = json.loads(repaired)
                    except json.JSONDecodeError:
                        args = {"__json_decode_error__": raw_args}
                tc_id = tc.get('id') or f"call_{len(tool_calls)}"
                tc_name = tc['function'].get('name') or ''
                if tc_name:
                    tool_calls.append(ToolCall(
                        id=tc_id,
                        name=tc_name,
                        arguments=args
                    ))
        
        content = message.get('content') or ""
        reasoning = message.get('reasoning_content') or message.get('reasoning') or ""
        
        if "<reflection>" in content:
            content = re.sub(r"<reflection>.*?</reflection>", "", content, flags=re.DOTALL)
            content = content.strip()
        
        # 清洗模型特定控制标记（DeepSeek DSML 等）
        if _CONTROL_MARKER_RE.search(content):
            content = _CONTROL_MARKER_RE.sub('', content).strip()

        # 兜底：DeepSeek 等模型可能把输出放在 reasoning_content 而非 content
        # 与流式路径 (_stream_with_httpx line 560-563) 保持一致
        if not content and not tool_calls and reasoning.strip():
            content = reasoning

        usage = resp_data.get('usage', {})
        
        return LLMResponse(
            content=content,
            reasoning_content=reasoning or None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            input_tokens=usage.get('prompt_tokens', 0),
            output_tokens=usage.get('completion_tokens', 0),
            total_tokens=usage.get('total_tokens', 0),
            prompt_cache_hit_tokens=usage.get('prompt_cache_hit_tokens', 0)
        )

    @staticmethod
    def _try_split_concat_tool_call(raw_name: str, raw_args: str, base_idx: int) -> Optional[List[ToolCall]]:
        """检测 K2.6 并行工具名拼接并拆分为独立 ToolCall。

        K2.6 streaming 不遵守 OpenAI index 协议：多个 tool_calls 的 name/args
        被拼接到同一个 index，产生如 name="shellsearch_knowledge_nodes",
        args='{"command":"ps aux"}{"keywords":["daemon"]}'。

        拆分策略：
        1. 用已知工具名贪婪匹配 raw_name，找出所有拼接片段
        2. 在 args 的 }{ 边界处拆分，与 name 片段一一对应
        3. 无法拆分时返回 None（走原有 JSON 解析兜底）
        """
        if not raw_name or not raw_args:
            return None

        # 从 tools 定义中获取已知工具名（延迟导入避免循环依赖）
        try:
            from genesis.core.registry import ToolRegistry
            known_names = set(ToolRegistry._global_known_names())
        except Exception:
            return None

        if not known_names:
            return None

        # 贪婪匹配：按名称长度降序，确保最长匹配优先
        sorted_known = sorted(known_names, key=len, reverse=True)
        name_parts = []
        remaining = raw_name
        while remaining:
            matched = False
            for name in sorted_known:
                if remaining.startswith(name):
                    name_parts.append(name)
                    remaining = remaining[len(name):]
                    matched = True
                    break
            if not matched:
                # 有无法匹配的残留，不是拼接场景
                return None

        # 只有一个匹配 → 不是拼接，走正常流程
        if len(name_parts) <= 1:
            return None

        logger.warning(f"K2.6 拼接拆分: '{raw_name}' → {name_parts}")

        # 拆分 args：在顶级 }{ 边界处切割
        # 策略：逐字符追踪花括号深度，depth=0 且遇到 }{ 时切割
        arg_parts = []
        depth = 0
        start = 0
        in_string = False
        escape_next = False
        for pos, ch in enumerate(raw_args):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and pos + 1 < len(raw_args) and raw_args[pos + 1] == '{':
                    arg_parts.append(raw_args[start:pos + 1])
                    start = pos + 1

        # 最后一段
        if start < len(raw_args):
            arg_parts.append(raw_args[start:])

        # name_parts 和 arg_parts 数量必须一致
        if len(arg_parts) != len(name_parts):
            logger.warning(f"K2.6 拼接拆分失败: name_parts={len(name_parts)} != arg_parts={len(arg_parts)}, 降级走正常解析")
            return None

        result = []
        for i, (name, arg_str) in enumerate(zip(name_parts, arg_parts)):
            try:
                args = json.loads(arg_str) if arg_str.strip() else {}
            except json.JSONDecodeError:
                repaired = arg_str.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                try:
                    args = json.loads(repaired)
                except Exception:
                    args = {"__json_decode_error__": arg_str}
            result.append(ToolCall(
                id=f"call_split_{base_idx}_{i}",
                name=name,
                arguments=args,
            ))
        return result

    async def _stream_with_httpx(self, client: httpx.AsyncClient, url: str, headers: Dict, params: Dict, callback) -> LLMResponse:
        """流式请求"""
        full_content = []
        reasoning_content = []
        tool_call_chunks = {}
        final_tool_calls = []
        finish_reason = None
        input_tokens = 0
        output_tokens = 0
        prompt_cache_hit_tokens = 0
        
        retries = 5
        
        for attempt in range(retries):
            # 重试时重置累积器，防止部分流残留导致内容重复/工具调用损坏
            full_content = []
            reasoning_content = []
            tool_call_chunks = {}
            final_tool_calls = []
            finish_reason = None
            input_tokens = 0
            output_tokens = 0
            prompt_cache_hit_tokens = 0
            try:
                if self.skip_content_type:
                    stream_ctx = client.stream("POST", url, headers=headers, content=json.dumps(params).encode())
                else:
                    stream_ctx = client.stream("POST", url, headers=headers, json=params)
                async with stream_ctx as response:
                    if response.status_code != 200:
                        await response.aread()
                    response.raise_for_status()
                    
                    # Per-chunk timeout: 防止 API 停止发数据导致永久挂起
                    # httpx read timeout 是 per-syscall，但 streaming 下可能不生效
                    chunk_timeout = self.read_timeout + 30  # 比 httpx read 多 30s 余量
                    aiter = response.aiter_lines()
                    while True:
                        try:
                            line = await asyncio.wait_for(aiter.__anext__(), timeout=chunk_timeout)
                        except StopAsyncIteration:
                            break
                        except asyncio.TimeoutError:
                            logger.warning(f"Stream chunk timeout ({chunk_timeout}s): API 停止发送数据")
                            raise httpx.ReadTimeout(f"Stream read timeout ({chunk_timeout}s): no data from API")
                        
                        line = line.strip()
                        if not line:
                            continue
                        if not line.startswith('data: '):
                            continue
                            
                        chunk_str = line[6:]
                        if chunk_str == '[DONE]':
                            break
                            
                        try:
                            chunk = json.loads(chunk_str)
                            choices = chunk.get('choices')
                            if not choices: continue
                            
                            choice0 = choices[0] if choices else None
                            if not choice0: continue
                            
                            # finish_reason 可出现在任何 chunk（MiniMax 在中间 chunk 就带 finish_reason）
                            if choice0.get('finish_reason'):
                                finish_reason = choice0['finish_reason']
                            
                            # MiniMax 最终 chunk 用 'message' 而非 'delta'（含完整 reasoning + usage）
                            # 优先用 delta，fallback 到 message（兼容 MiniMax 格式）
                            delta = choice0.get('delta')
                            if delta is None:
                                msg = choice0.get('message')
                                if msg is not None:
                                    # MiniMax 最终 chunk：提取 reasoning（仅当之前未累积时），跳过已累积的 content
                                    rc = msg.get('reasoning_content') or msg.get('reasoning')
                                    if rc and not reasoning_content:
                                        reasoning_content.append(rc)
                                    delta = {}
                            
                            if not delta: delta = {}
                            
                            # Reasoning
                            rc = delta.get('reasoning_content') or delta.get('reasoning')
                            if rc:
                                reasoning_content.append(rc)
                                if callback:
                                    res = callback("reasoning", rc)
                                    if asyncio.iscoroutine(res): await res
                                        
                            # Content
                            if 'content' in delta:
                                c = delta['content']
                                if c:
                                    full_content.append(c)
                                    if callback:
                                        res = callback("content", c)
                                        if asyncio.iscoroutine(res): await res
                            
                            # Tool Calls
                            if delta.get('tool_calls'):
                                for tc in delta['tool_calls']:
                                    idx = tc.get('index', len(tool_call_chunks))
                                    has_id = 'id' in tc and tc['id']
                                    has_name = 'function' in tc and 'name' in tc['function'] and tc['function']['name']
                                    
                                    # xcode 特殊格式：名字在 index N，参数在 index N+1（无 name/id）
                                    # 检测：新 index 且无 name/id，只有 args → 合并到上一个有名字的 call
                                    if idx not in tool_call_chunks and not has_id and not has_name:
                                        # 找最近一个有 name 的 index
                                        named = [k for k in tool_call_chunks if tool_call_chunks[k]["name"]]
                                        if named:
                                            merge_idx = max(named)
                                            if 'function' in tc and 'arguments' in tc['function']:
                                                tool_call_chunks[merge_idx]["args"] += tc['function']['arguments']
                                            continue
                                    
                                    if idx not in tool_call_chunks:
                                        tool_call_chunks[idx] = {"id": "", "name": "", "args": ""}
                                    if has_id: tool_call_chunks[idx]["id"] = tc['id']
                                    if 'function' in tc:
                                        if 'name' in tc['function']: tool_call_chunks[idx]["name"] += tc['function']['name']
                                        if 'arguments' in tc['function']: tool_call_chunks[idx]["args"] += tc['function']['arguments']
                            
                            if 'usage' in chunk and chunk['usage']:
                                output_tokens = chunk['usage'].get('completion_tokens', 0)
                                input_tokens = chunk['usage'].get('prompt_tokens', 0)
                                prompt_cache_hit_tokens = chunk['usage'].get('prompt_cache_hit_tokens', 0)

                        except json.JSONDecodeError:
                            continue
                            
                # If we get here, stream completed — but check for empty response
                if not full_content and not tool_call_chunks and not reasoning_content:
                    if attempt < retries - 1:
                        NativeHTTPProvider._stats_retries += 1
                        NativeHTTPProvider._record_stat("retry")
                        logger.warning(f"Empty stream response (attempt {attempt+1}/{retries}), retrying...")
                        await asyncio.sleep(1 * (attempt + 1))
                        continue
                break
                
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                # 400 偶发重试：K2.6 API 间歇性拒绝合法请求（同 payload 重发即成功）
                # skip_content_type 模式下更频繁，但所有 provider 都可能遇到
                if status == 400 and attempt < retries - 1:
                    NativeHTTPProvider._stats_retries += 1
                    NativeHTTPProvider._record_stat("retry")
                    body_bytes = json.dumps(params, ensure_ascii=False).encode('utf-8')
                    if attempt == 0:
                        try:
                            with open(f"/tmp/genesis_400_{int(time.time())}.json", 'wb') as f:
                                f.write(body_bytes)
                        except Exception: pass
                    logger.warning(f"400 retry {attempt+1}/{retries} ({len(body_bytes)}B), fresh client")
                    # 销毁旧 client，下次循环 _get_http_client() 会创新的
                    if self._http_client:
                        try: await self._http_client.aclose()
                        except Exception: pass
                        self._http_client = None
                    client = self._get_http_client()
                    await asyncio.sleep(1)
                    continue
                # 5xx 瞬态错误可重试（502/503/504/524）
                # 524 = Cloudflare origin timeout
                if status in (502, 503, 504, 524) and attempt < retries - 1:
                    NativeHTTPProvider._stats_retries += 1
                    NativeHTTPProvider._record_stat("retry")
                    logger.warning(f"Stream HTTP {status} (attempt {attempt+1}/{retries}): {e.response.text[:100]}")
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                # 400 诊断：记录请求关键信息
                if status == 400:
                    msgs = params.get("messages", [])
                    msgs_summary = []
                    tc_ids = []
                    result_ids = []
                    for m in msgs:
                        role = m.get("role", "?")
                        content = m.get("content")
                        tc = m.get("tool_calls")
                        if tc:
                            msgs_summary.append(f"{role}: [tc x{len(tc)} ids={[t.get('id','?')[:8] for t in tc]}]")
                            tc_ids.extend([t.get('id') for t in tc if t.get('id')])
                        elif role == "tool":
                            tid = m.get("tool_call_id", "?")
                            result_ids.append(tid)
                            msgs_summary.append(f"tool(res:{tid[:8]})")
                        elif content is None:
                            msgs_summary.append(f"{role}: [content=None]")
                        else:
                            msgs_summary.append(f"{role}: {str(content)[:40]}")
                    missing = [t for t in tc_ids if t not in result_ids]
                    orphan = [r for r in result_ids if r not in tc_ids]
                    detail = f"model={params.get('model')} | n_msgs={len(msgs)} | msgs=[{', '.join(msgs_summary)}] | tc_ids={len(tc_ids)} res_ids={len(result_ids)} missing={len(missing)} orphan={len(orphan)} | tools={len(params.get('tools',[]))} | stream={params.get('stream')}"
                    logger.warning(f"🔍 Stream 400 debug | {detail}")
                    try:
                        with open("/tmp/genesis_400_debug.log", "a") as f:
                            f.write(f"\n=== {time.strftime('%H:%M:%S')} (stream) ===\n{detail}\n")
                        # 完整请求体转储（用于定位 400 根因）
                        with open(f"/tmp/genesis_400_payload_{int(time.time())}.json", "w") as f:
                            dump_data = {"params_keys": list(params.keys()), "model": params.get("model"),
                                        "n_msgs": len(msgs), "messages": msgs}
                            # Include tools schema (truncated descriptions to keep file size manageable)
                            tools_raw = params.get("tools", [])
                            tools_dump = []
                            for t in tools_raw:
                                td = dict(t)
                                if "function" in td:
                                    fn = dict(td["function"])
                                    if "description" in fn and len(fn["description"]) > 200:
                                        fn["description"] = fn["description"][:200] + "...[TRUNCATED]"
                                    td["function"] = fn
                                tools_dump.append(td)
                            dump_data["tools"] = tools_dump
                            dump_data["stream"] = params.get("stream")
                            dump_data["stop"] = params.get("stop")
                            dump_data["tool_choice"] = params.get("tool_choice")
                            json.dump(dump_data, f, ensure_ascii=False, indent=1)
                    except Exception: pass
                NativeHTTPProvider._stats_errors += 1
                NativeHTTPProvider._record_stat("error")
                raise Exception(f"API Error ({status}): {self._clean_error_text(e.response.text)}")
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as e:
                logger.warning(f"httpx stream error (attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    NativeHTTPProvider._stats_retries += 1
                    NativeHTTPProvider._record_stat("retry")
                    logger.warning(f"Empty stream response (attempt {attempt+1}/{retries}), retrying...")
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                NativeHTTPProvider._stats_timeouts += 1
                NativeHTTPProvider._record_stat("timeout")
                raise Exception(f"Stream Network Error after {retries} retries: {e}")
            except Exception as e:
                NativeHTTPProvider._stats_errors += 1
                NativeHTTPProvider._record_stat("error")
                raise
                
        # Post-processing
        for idx in sorted(tool_call_chunks.keys()):
            tc_data = tool_call_chunks[idx]
            raw_name = tc_data["name"]
            raw_args = tc_data["args"]

            # ── K2.6 并行工具名拼接修复 ──
            # K2.6 streaming 不遵守 index 协议，多个 tool_calls 的 name/args
            # 被拼接到同一个 index，导致 name="shellsearch_knowledge_nodes",
            # args="{\"command\":\"...\"}{\"keywords\":[...]\"}"
            split_calls = self._try_split_concat_tool_call(raw_name, raw_args, idx)
            if split_calls is not None:
                for sc in split_calls:
                    final_tool_calls.append(sc)
                continue

            try:
                args = json.loads(raw_args) if raw_args else {}
                final_tool_calls.append(ToolCall(
                    id=tc_data["id"] or f"call_{idx}",
                    name=raw_name,
                    arguments=args
                ))
            except json.JSONDecodeError:
                # Try simple repair for newlines
                repaired = raw_args.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                try:
                    args = json.loads(repaired)
                    final_tool_calls.append(ToolCall(
                        id=tc_data["id"] or f"call_{idx}",
                        name=raw_name,
                        arguments=args
                    ))
                except Exception:
                     final_tool_calls.append(ToolCall(
                        id=tc_data["id"] or f"call_{idx}",
                        name=raw_name,
                        arguments={"__json_decode_error__": raw_args}
                    ))

        final_content = "".join(full_content)
        
        # 清洗模型特定控制标记（DeepSeek DSML 等）
        if _CONTROL_MARKER_RE.search(final_content):
            final_content = _CONTROL_MARKER_RE.sub('', final_content).strip()
        
        if not final_content and not final_tool_calls:
            rc_text = "".join(reasoning_content)
            if rc_text.strip():
                final_content = rc_text
            else:
                raise Exception("Empty LLM response from stream")

        return LLMResponse(
            content=final_content,
            reasoning_content="".join(reasoning_content),
            tool_calls=final_tool_calls,
            finish_reason=finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            prompt_cache_hit_tokens=prompt_cache_hit_tokens
        )

class MockLLMProvider(BaseLLMProvider):
    """Mock LLM 提供商 - 用于测试"""
    
    def __init__(self):
        self.call_count = 0
    
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """模拟 LLM 响应"""
        
        self.call_count += 1
        
        return LLMResponse(
            content=f"Mock response #{self.call_count}",
            tool_calls=[],
            finish_reason="stop",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150
        )
    
    def get_default_model(self) -> str:
        return "mock-model"

