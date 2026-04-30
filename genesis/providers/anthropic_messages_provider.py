"""
Anthropic Messages API Provider

适配 DeepSeek V4 等模型通过 Anthropic Messages API 端点调用的场景。
waibibabo 等中转服务的 /v1/chat/completions (OpenAI 格式) 在 DeepSeek V4
thinking + tool_calls 多轮场景下存在转换层 bug，但 /v1/messages (Anthropic 格式)
可以正常工作。此 Provider 将 Genesis 内部的 OpenAI 格式消息转换为 Anthropic 格式。

Anthropic Messages API 格式关键差异：
- system 消息是顶层参数，不在 messages 数组中
- assistant 的 thinking/tool_use 都在 content 数组里
- tool result 是 user 消息中的 tool_result block
- 流式 SSE 事件格式不同
"""

from typing import List, Dict, Any, Optional
import json
import asyncio
import logging
import time

from genesis.core.provider import NativeHTTPProvider, LLMResponse, ToolCall
from genesis.core.base import LLMProvider as BaseLLMProvider

logger = logging.getLogger(__name__)


class AnthropicMessagesProvider(NativeHTTPProvider):
    """Anthropic Messages API Provider

    将 Genesis 内部 OpenAI 格式的消息/工具转换为 Anthropic Messages API 格式，
    并将响应转回 LLMResponse。适用于 waibibabo 等中转服务的 Anthropic 端点。
    """

    def __init__(self, *args, anthropic_version: str = "2023-06-01", **kwargs):
        super().__init__(*args, **kwargs)
        self.anthropic_version = anthropic_version

    # ── OpenAI → Anthropic 消息格式转换 ──────────────────────────

    @staticmethod
    def _convert_tools_to_anthropic(tools: List[Dict]) -> List[Dict]:
        """OpenAI tools → Anthropic tools"""
        anthropic_tools = []
        for t in tools:
            func = t.get("function", {})
            anthropic_tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })
        return anthropic_tools

    @staticmethod
    def _convert_messages_to_anthropic(messages: List[Dict]) -> tuple:
        """OpenAI messages → (system_prompt, anthropic_messages)

        返回 (system_prompt: str | None, messages: list)
        """
        system_prompt = None
        anthropic_msgs = []

        for m in messages:
            role = m.get("role", "")
            content = m.get("content")

            # system 消息提取为顶层参数
            if role == "system":
                if isinstance(content, str):
                    system_prompt = content
                elif isinstance(content, list):
                    # 多模态 system：拼接文本
                    parts = [b.get("text", "") for b in content if b.get("type") == "text"]
                    system_prompt = "\n".join(parts)
                continue

            # user 消息
            if role == "user":
                if isinstance(content, list):
                    # 已经是 Anthropic content block 格式（如 tool_result）
                    anthropic_msgs.append({"role": "user", "content": content})
                else:
                    anthropic_msgs.append({"role": "user", "content": [{"type": "text", "text": str(content or "")}]})
                continue

            # assistant 消息
            if role == "assistant":
                blocks = []

                # reasoning_content → thinking block
                rc = m.get("reasoning_content")
                if rc:
                    blocks.append({"type": "thinking", "thinking": rc})

                # content → text block
                if content:
                    if isinstance(content, list):
                        # 已经是 content block 格式
                        blocks.extend(content)
                    elif isinstance(content, str) and content.strip():
                        blocks.append({"type": "text", "text": content})

                # tool_calls → tool_use blocks
                tool_calls = m.get("tool_calls")
                if tool_calls:
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        raw_args = fn.get("arguments", "{}")
                        if isinstance(raw_args, str):
                            try:
                                args = json.loads(raw_args)
                            except json.JSONDecodeError:
                                args = {"__raw__": raw_args}
                        else:
                            args = raw_args
                        blocks.append({
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": fn.get("name", ""),
                            "input": args,
                        })

                # 至少要有一个 block
                if not blocks:
                    blocks.append({"type": "text", "text": " "})

                anthropic_msgs.append({"role": "assistant", "content": blocks})
                continue

            # tool 消息 → user 消息中的 tool_result block
            if role == "tool":
                tool_call_id = m.get("tool_call_id", "")
                tool_content = m.get("content", "")
                # 合并到前一个 user 消息（如果前一个是 user 且包含 tool_result），
                # 或创建新 user 消息
                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": str(tool_content),
                }
                # Anthropic 要求连续的 tool_result 在同一个 user 消息里
                if (anthropic_msgs
                        and anthropic_msgs[-1]["role"] == "user"
                        and isinstance(anthropic_msgs[-1]["content"], list)
                        and any(b.get("type") == "tool_result" for b in anthropic_msgs[-1]["content"])):
                    anthropic_msgs[-1]["content"].append(tool_result_block)
                else:
                    anthropic_msgs.append({"role": "user", "content": [tool_result_block]})
                continue

        return system_prompt, anthropic_msgs

    # ── Anthropic → LLMResponse 响应转换 ──────────────────────────

    @staticmethod
    def _parse_anthropic_response(resp_data: Dict) -> LLMResponse:
        """解析 Anthropic Messages API 响应 → LLMResponse"""
        if resp_data.get("type") == "error":
            err = resp_data.get("error", {})
            raise Exception(f"Anthropic API Error: {err.get('message', str(err))}")

        content_blocks = resp_data.get("content", [])
        stop_reason = resp_data.get("stop_reason")

        text_parts = []
        reasoning_parts = []
        tool_calls = []

        for block in content_blocks:
            btype = block.get("type", "")

            if btype == "text":
                text_parts.append(block.get("text", ""))

            elif btype == "thinking":
                reasoning_parts.append(block.get("thinking", ""))

            elif btype == "tool_use":
                raw_input = block.get("input", {})
                if isinstance(raw_input, dict):
                    args = raw_input
                else:
                    try:
                        args = json.loads(str(raw_input))
                    except Exception:
                        args = {"__raw__": str(raw_input)}
                tool_calls.append(ToolCall(
                    id=block.get("id", ""),
                    name=block.get("name", ""),
                    arguments=args,
                ))

        content = "".join(text_parts)
        reasoning = "".join(reasoning_parts)

        # 兜底：如果 content 为空但有 reasoning
        if not content and not tool_calls and reasoning.strip():
            content = reasoning

        usage = resp_data.get("usage", {})

        return LLMResponse(
            content=content,
            reasoning_content=reasoning or None,
            tool_calls=tool_calls,
            finish_reason=stop_reason,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        )

    # ── 消息清洗覆写 ──────────────────────────────────────────────

    def _sanitize_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """覆写父类：Anthropic 格式转换需要 reasoning_content，绝不能剥离。

        父类 _sanitize_messages 会把 reasoning_content 从 _STRIP_MSG_FIELDS 中剥离
        （仅对 deepseek-v4-pro 例外），但 AnthropicMessagesProvider 需要它来转换成
        content[].thinking block。所以这里跳过 reasoning_content 的剥离。
        """
        # 调用父类清洗（content None 修复、name 清理等），但强制保留 reasoning_content
        cleaned = super()._sanitize_messages(messages)
        # 父类可能已剥离 reasoning_content，从原始消息恢复
        for i, original in enumerate(messages):
            if original.get("role") == "assistant" and original.get("reasoning_content"):
                if not cleaned[i].get("reasoning_content"):
                    cleaned[i]["reasoning_content"] = original["reasoning_content"]
        return cleaned

    # ── chat 主入口 ──────────────────────────────────────────────

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        stream: bool = False,
        stream_callback: Any = None,
        **kwargs
    ) -> LLMResponse:
        """发送聊天请求 (Anthropic Messages API 格式)"""
        messages = self._sanitize_messages(messages)
        model = model or self.default_model

        # 过滤内部参数（以 _ 开头的，如 _trace_id），Anthropic API 不接受未知字段
        api_kwargs = {k: v for k, v in kwargs.items() if not k.startswith("_")}

        # 格式转换
        system_prompt, anthropic_msgs = self._convert_messages_to_anthropic(messages)

        request_params = {
            "model": model,
            "messages": anthropic_msgs,
            "max_tokens": api_kwargs.pop("max_tokens", 8192),
        }
        if system_prompt:
            request_params["system"] = system_prompt
        if tools:
            request_params["tools"] = self._convert_tools_to_anthropic(tools)
            request_params["tool_choice"] = {"type": "auto"}

        # DeepSeek V4 thinking 参数
        thinking_type = api_kwargs.pop("thinking_type", None)
        if thinking_type:
            request_params["thinking"] = {"type": thinking_type}

        if stream:
            request_params["stream"] = True

        # Anthropic 风格 headers
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.anthropic_version,
            "Content-Type": "application/json",
        }
        if self.default_headers:
            headers.update(self.default_headers)

        # URL: base_url + /messages
        url = f"{self.base_url}/messages"

        client = self._get_http_client()
        NativeHTTPProvider._stats_total_calls += 1
        try:
            if stream:
                coro = self._stream_anthropic(client, url, headers, request_params, stream_callback)
            else:
                coro = self._chat_anthropic(client, url, headers, request_params)
            result = await asyncio.wait_for(coro, timeout=self.wall_clock_timeout)
            NativeHTTPProvider._record_stat("ok")
            return result
        except asyncio.TimeoutError:
            NativeHTTPProvider._stats_wall_clock_timeouts += 1
            NativeHTTPProvider._record_stat("wall_timeout")
            if self._http_client:
                try: await self._http_client.aclose()
                except Exception: pass
                self._http_client = None
            raise Exception(
                f"LLM 调用总超时 ({self.wall_clock_timeout}s)。"
                f"推理模型可能思考过久，请简化问题或缩短上下文。"
            )

    async def _chat_anthropic(self, client, url, headers, params) -> LLMResponse:
        """非流式 Anthropic 请求"""
        retries = 5
        for attempt in range(retries):
            try:
                response = await client.post(url, headers=headers, json=params)
                response.raise_for_status()
                return self._parse_anthropic_response(response.json())
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                error_body = e.response.text

                if status in (502, 503, 504, 524) and attempt < retries - 1:
                    NativeHTTPProvider._stats_retries += 1
                    NativeHTTPProvider._record_stat("retry")
                    logger.warning(f"Anthropic HTTP {status} (attempt {attempt+1}/{retries})")
                    await asyncio.sleep(1 * (attempt + 1))
                    continue

                if status == 400 and attempt < retries - 1:
                    NativeHTTPProvider._stats_retries += 1
                    NativeHTTPProvider._record_stat("retry")
                    logger.warning(f"Anthropic 400 retry {attempt+1}/{retries}: {error_body[:80]}")
                    await asyncio.sleep(1)
                    continue

                NativeHTTPProvider._stats_errors += 1
                NativeHTTPProvider._record_stat("error")
                raise Exception(f"Anthropic API Error ({status}): {self._clean_error_text(error_body)}")

            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as e:
                logger.warning(f"Anthropic connection error (attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    NativeHTTPProvider._stats_retries += 1
                    NativeHTTPProvider._record_stat("retry")
                    await asyncio.sleep(1)
                    continue
                NativeHTTPProvider._stats_timeouts += 1
                NativeHTTPProvider._record_stat("timeout")
                raise Exception(f"Anthropic Network Error after {retries} retries: {e}")

            except Exception as e:
                NativeHTTPProvider._stats_errors += 1
                NativeHTTPProvider._record_stat("error")
                logger.error(f"Anthropic unexpected error: {e}")
                raise

        raise Exception("Anthropic API: max retries exceeded")

    async def _stream_anthropic(self, client, url, headers, params, callback) -> LLMResponse:
        """流式 Anthropic Messages API 请求

        Anthropic SSE 事件类型：
        - message_start: 消息开始，含 metadata
        - content_block_start: 新 content block 开始
        - content_block_delta: content block 增量数据
        - content_block_stop: content block 结束
        - message_delta: 消息级更新（stop_reason, usage）
        - message_stop: 消息结束
        - ping: 心跳
        """
        full_content = []
        reasoning_content = []
        tool_call_blocks = {}  # index → {id, name, input_str}
        final_tool_calls = []
        finish_reason = None
        input_tokens = 0
        output_tokens = 0

        # 当前正在累积的 block 信息
        current_block_type = None
        current_block_index = None

        retries = 3
        for attempt in range(retries):
            # 重置
            full_content = []
            reasoning_content = []
            tool_call_blocks = {}
            final_tool_calls = []
            finish_reason = None
            input_tokens = 0
            output_tokens = 0
            current_block_type = None
            current_block_index = None

            try:
                async with client.stream("POST", url, headers=headers, json=params) as response:
                    if response.status_code != 200:
                        await response.aread()
                    response.raise_for_status()

                    chunk_timeout = self.read_timeout + 30
                    aiter = response.aiter_lines()
                    while True:
                        try:
                            line = await asyncio.wait_for(aiter.__anext__(), timeout=chunk_timeout)
                        except StopAsyncIteration:
                            break
                        except asyncio.TimeoutError:
                            logger.warning(f"Anthropic stream chunk timeout ({chunk_timeout}s)")
                            raise Exception(f"Anthropic stream read timeout ({chunk_timeout}s)")

                        line = line.strip()
                        if not line:
                            continue

                        # Anthropic SSE 格式: "event: xxx" + "data: {...}"
                        if line.startswith("event: "):
                            continue  # 事件类型在下一行 data 里也能判断
                        if not line.startswith("data: "):
                            continue

                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        event_type = data.get("type", "")

                        # message_start: 提取 input_tokens
                        if event_type == "message_start":
                            msg = data.get("message", {})
                            usage = msg.get("usage", {})
                            input_tokens = usage.get("input_tokens", 0)

                        # content_block_start: 新 block
                        elif event_type == "content_block_start":
                            block = data.get("content_block", {})
                            current_block_type = block.get("type", "")
                            current_block_index = data.get("index", len(tool_call_blocks))

                            if current_block_type == "tool_use":
                                tool_call_blocks[current_block_index] = {
                                    "id": block.get("id", ""),
                                    "name": block.get("name", ""),
                                    "input_str": "",
                                }

                        # content_block_delta: 增量内容
                        elif event_type == "content_block_delta":
                            delta = data.get("delta", {})
                            delta_type = delta.get("type", "")

                            if delta_type == "thinking_delta":
                                text = delta.get("thinking", "")
                                if text:
                                    reasoning_content.append(text)
                                    if callback:
                                        res = callback("reasoning", text)
                                        if asyncio.iscoroutine(res): await res

                            elif delta_type == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    full_content.append(text)
                                    if callback:
                                        res = callback("content", text)
                                        if asyncio.iscoroutine(res): await res

                            elif delta_type == "input_json_delta":
                                partial = delta.get("partial_json", "")
                                idx = data.get("index", current_block_index)
                                if idx in tool_call_blocks:
                                    tool_call_blocks[idx]["input_str"] += partial

                        # message_delta: stop_reason + usage
                        elif event_type == "message_delta":
                            delta = data.get("delta", {})
                            if delta.get("stop_reason"):
                                finish_reason = delta["stop_reason"]
                            usage = data.get("usage", {})
                            output_tokens = usage.get("output_tokens", output_tokens)

                        # message_stop / ping: 忽略
                        elif event_type in ("message_stop", "ping", "content_block_stop"):
                            pass

                # 流结束
                if not full_content and not tool_call_blocks and not reasoning_content:
                    if attempt < retries - 1:
                        NativeHTTPProvider._stats_retries += 1
                        NativeHTTPProvider._record_stat("retry")
                        logger.warning(f"Anthropic empty stream (attempt {attempt+1}/{retries})")
                        await asyncio.sleep(1 * (attempt + 1))
                        continue
                break

            except Exception as e:
                status = getattr(getattr(e, 'response', None), 'status_code', 0)
                if status in (502, 503, 504, 524) and attempt < retries - 1:
                    NativeHTTPProvider._stats_retries += 1
                    NativeHTTPProvider._record_stat("retry")
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                if status == 400 and attempt < retries - 1:
                    NativeHTTPProvider._stats_retries += 1
                    NativeHTTPProvider._record_stat("retry")
                    await asyncio.sleep(1)
                    continue
                NativeHTTPProvider._stats_errors += 1
                NativeHTTPProvider._record_stat("error")
                raise

        # 组装 tool_calls
        for idx in sorted(tool_call_blocks.keys()):
            tc_data = tool_call_blocks[idx]
            raw_input = tc_data["input_str"]
            try:
                args = json.loads(raw_input) if raw_input.strip() else {}
            except json.JSONDecodeError:
                args = {"__json_decode_error__": raw_input}
            final_tool_calls.append(ToolCall(
                id=tc_data["id"] or f"call_{idx}",
                name=tc_data["name"],
                arguments=args,
            ))

        final_content = "".join(full_content)
        final_reasoning = "".join(reasoning_content)

        if not final_content and not final_tool_calls:
            if final_reasoning.strip():
                final_content = final_reasoning
            else:
                raise Exception("Empty LLM response from Anthropic stream")

        return LLMResponse(
            content=final_content,
            reasoning_content=final_reasoning or None,
            tool_calls=final_tool_calls,
            finish_reason=finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )
