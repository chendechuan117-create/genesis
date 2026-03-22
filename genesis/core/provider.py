"""
LLM 提供商实现
"""

from typing import List, Dict, Any, Optional
import logging
import json
import re
import asyncio
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
        wall_clock_timeout: int = 300,  # 整体超时(秒)：防止推理模型思考过久
        stop_sequences: Optional[List[str]] = None,
        provider_name: str = "default",
        use_proxy: bool = False
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/') if base_url else "https://api.deepseek.com/v1"
        self.default_model = default_model
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout
        self.wall_clock_timeout = wall_clock_timeout
        self.stop_sequences = stop_sequences if stop_sequences is not None else self.DEFAULT_STOP_SEQUENCES
        self.provider_name = provider_name
        self.use_proxy = use_proxy
        self._http_client: Optional[httpx.AsyncClient] = None
    
    def _get_http_client(self) -> httpx.AsyncClient:
        """延迟初始化的持久 httpx 客户端（复用 TCP 连接池）"""
        if self._http_client is None or self._http_client.is_closed:
            timeout = httpx.Timeout(self.request_timeout, connect=self.connect_timeout)
            self._http_client = httpx.AsyncClient(timeout=timeout, trust_env=self.use_proxy)
        return self._http_client

    def get_default_model(self) -> str:
        """获取默认模型"""
        return self.default_model

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
        model = model or self.default_model
        if model.startswith("deepseek/"):
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
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "NanoGenesis/1.0"
        }
        
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
            raise WallClockTimeoutError(
                f"LLM 调用总超时 ({self.wall_clock_timeout}s)。"
                f"推理模型可能思考过久，请简化问题或缩短上下文。"
            )

    async def _chat_with_httpx(self, client: httpx.AsyncClient, url: str, headers: Dict, params: Dict) -> LLMResponse:
        """非流式请求"""
        retries = 3
        last_exception = None
        
        for attempt in range(retries):
            try:
                response = await client.post(url, headers=headers, json=params)
                response.raise_for_status()
                return self._parse_response(response.json())
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                error_body = e.response.text
                try:
                    err_json = e.response.json()
                    error_msg = err_json.get('error', {}).get('message', error_body)
                except:
                    error_msg = error_body
                # 5xx 瞬态错误可重试（502/503/504）
                if status in (502, 503, 504) and attempt < retries - 1:
                    NativeHTTPProvider._stats_retries += 1
                    NativeHTTPProvider._record_stat("retry")
                    logger.warning(f"HTTP {status} (attempt {attempt+1}/{retries}): {error_msg[:100]}")
                    last_exception = e
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                NativeHTTPProvider._stats_errors += 1
                NativeHTTPProvider._record_stat("error")
                raise Exception(f"API Error ({status}): {error_msg}")
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
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
        tool_calls = []
        if 'tool_calls' in message and message['tool_calls']:
            for tc in message['tool_calls']:
                raw_args = tc['function'].get('arguments', '{}')
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    # 修复：与流式路径对齐的 3 层回退
                    repaired = raw_args.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                    try:
                        args = json.loads(repaired)
                    except json.JSONDecodeError:
                        args = {"__json_decode_error__": raw_args}
                tool_calls.append(ToolCall(
                    id=tc['id'],
                    name=tc['function']['name'],
                    arguments=args
                ))
        
        content = message.get('content') or ""
        
        if "<reflection>" in content:
            content = re.sub(r"<reflection>.*?</reflection>", "", content, flags=re.DOTALL)
            content = content.strip()
        
        # 清洗模型特定控制标记（DeepSeek DSML 等）
        if _CONTROL_MARKER_RE.search(content):
            content = _CONTROL_MARKER_RE.sub('', content).strip()

        usage = resp_data.get('usage', {})
        
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            input_tokens=usage.get('prompt_tokens', 0),
            output_tokens=usage.get('completion_tokens', 0),
            total_tokens=usage.get('total_tokens', 0),
            prompt_cache_hit_tokens=usage.get('prompt_cache_hit_tokens', 0)
        )

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
        
        retries = 3
        
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
                async with client.stream("POST", url, headers=headers, json=params) as response:
                    if response.status_code != 200:
                        await response.aread()
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
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
                            
                            delta = choices[0].get('delta', {})
                            
                            # Reasoning
                            if 'reasoning_content' in delta:
                                rc = delta['reasoning_content']
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
                            if 'tool_calls' in delta:
                                for tc in delta['tool_calls']:
                                    idx = tc['index']
                                    if idx not in tool_call_chunks:
                                        tool_call_chunks[idx] = {"id": "", "name": "", "args": ""}
                                    if 'id' in tc and tc['id']: tool_call_chunks[idx]["id"] = tc['id']
                                    if 'function' in tc:
                                        if 'name' in tc['function']: tool_call_chunks[idx]["name"] += tc['function']['name']
                                        if 'arguments' in tc['function']: tool_call_chunks[idx]["args"] += tc['function']['arguments']
                            
                            if 'usage' in chunk:
                                output_tokens = chunk['usage'].get('completion_tokens', 0)
                                input_tokens = chunk['usage'].get('prompt_tokens', 0)
                                prompt_cache_hit_tokens = chunk['usage'].get('prompt_cache_hit_tokens', 0)

                        except json.JSONDecodeError:
                            continue
                            
                # If we get here, stream completed successfully
                break
                
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                # 5xx 瞬态错误可重试
                if status in (502, 503, 504) and attempt < retries - 1:
                    NativeHTTPProvider._stats_retries += 1
                    NativeHTTPProvider._record_stat("retry")
                    logger.warning(f"Stream HTTP {status} (attempt {attempt+1}/{retries}): {e.response.text[:100]}")
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                NativeHTTPProvider._stats_errors += 1
                NativeHTTPProvider._record_stat("error")
                raise Exception(f"API Error ({status}): {e.response.text}")
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
                logger.warning(f"httpx stream error (attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    NativeHTTPProvider._stats_retries += 1
                    NativeHTTPProvider._record_stat("retry")
                    await asyncio.sleep(1)
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
            try:
                args = json.loads(tc_data["args"]) if tc_data["args"] else {}
                final_tool_calls.append(ToolCall(
                    id=tc_data["id"] or f"call_{idx}",
                    name=tc_data["name"],
                    arguments=args
                ))
            except json.JSONDecodeError:
                # Try simple repair for newlines
                repaired = tc_data["args"].replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                try:
                    args = json.loads(repaired)
                    final_tool_calls.append(ToolCall(
                        id=tc_data["id"] or f"call_{idx}",
                        name=tc_data["name"],
                        arguments=args
                    ))
                except:
                     final_tool_calls.append(ToolCall(
                        id=tc_data["id"] or f"call_{idx}",
                        name=tc_data["name"],
                        arguments={"__json_decode_error__": tc_data["args"]}
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

