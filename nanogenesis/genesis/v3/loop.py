"""
Genesis V3 — 独立 ReAct Loop
纯净的 思考→行动→观察 循环。
没有熔断器，没有熵值检测，没有错误压缩，没有诊断注入。
V3 的自由度由 V3 自己决定。
"""

from typing import List, Dict, Any, Optional
import logging
import time
import json
import asyncio
import base64

from genesis.core.base import Message, MessageRole, LLMResponse, PerformanceMetrics, LLMProvider
from genesis.core.registry import ToolRegistry
from genesis.core.context import SimpleContextBuilder

logger = logging.getLogger(__name__)


class V3Loop:
    """V3 专属 ReAct 循环 — 无枷锁执行引擎"""

    def __init__(
        self,
        tools: ToolRegistry,
        context: SimpleContextBuilder,
        provider: LLMProvider,
        max_iterations: int = 50,
    ):
        self.tools = tools
        self.context = context
        self.provider = provider
        self.max_iterations = max_iterations

    async def run(
        self,
        user_input: str,
        step_callback: Optional[Any] = None,
    ) -> tuple[str, PerformanceMetrics]:
        """
        纯净的 ReAct 循环。

        Returns:
            (响应内容, 性能指标)
        """
        start_time = time.time()
        tools_used = []
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        prompt_cache_hit_tokens = 0
        tool_calls_recorded = []

        # 1. 构建初始消息序列
        built_messages = await self.context.build_stateless_messages(user_input)

        # 2. ReAct 循环
        iteration = 0
        final_response = ""

        while iteration < self.max_iterations:
            iteration += 1

            if step_callback:
                await self._call(step_callback, "loop_start", iteration)

            logger.debug(f"V3 Loop: Iteration {iteration}/{self.max_iterations}")

            # ── 2.1 净化消息序列（修复孤儿 tool 消息）──
            messages = self._sanitize_messages(built_messages)

            # ── 2.2 调用 LLM ──
            try:
                async def stream_handler(chunk_type, chunk_data):
                    if step_callback and chunk_type == "reasoning":
                        await self._call(step_callback, "reasoning", chunk_data)

                response = await self.provider.chat(
                    messages=messages,
                    tools=list(self.tools.get_definitions()),
                    stream=True,
                    stream_callback=stream_handler,
                )
                input_tokens += getattr(response, "input_tokens", 0) or 0
                output_tokens += getattr(response, "output_tokens", 0) or 0
                total_tokens += getattr(response, "total_tokens", 0) or 0
                prompt_cache_hit_tokens += getattr(response, "prompt_cache_hit_tokens", 0) or 0

                # DeepSeek R1 兼容：reasoning_content 降级为 content
                if not response.content and getattr(response, "reasoning_content", None):
                    response.content = response.reasoning_content

            except Exception as e:
                logger.error(f"V3 Loop: LLM call failed: {e}", exc_info=True)
                final_response = f"Error: LLM 调用失败 - {str(e)[:300]}"
                break

            # ── 2.3 空响应处理（温和重试，不杀进程）──
            if not response.content and not response.tool_calls:
                logger.warning(f"V3 Loop: Empty response at iteration {iteration}, retrying...")
                built_messages.append(Message(
                    role=MessageRole.USER,
                    content="[System] You returned an empty response. Please continue your work or provide an answer."
                ))
                continue

            # ── 2.4 纯文本响应 = 最终回答 ──
            if not response.tool_calls and response.content:
                final_response = response.content
                break

            # ── 2.5 工具调用处理 ──
            if response.has_tool_calls:
                normalized = self._normalize_tool_calls(response.tool_calls, iteration)
                tool_calls_recorded.extend(normalized)

                # 追加 assistant 消息（含 tool_calls）
                built_messages.append(Message(
                    role=MessageRole.ASSISTANT,
                    content=response.content or "",
                    tool_calls=normalized,
                ))

                # 逐个执行工具
                for tc in normalized:
                    tool_name = tc["function"]["name"]
                    tool_args_raw = tc["function"].get("arguments") or "{}"
                    tool_id = tc["id"]

                    try:
                        tool_args = json.loads(tool_args_raw) if isinstance(tool_args_raw, str) else tool_args_raw
                    except json.JSONDecodeError:
                        tool_args = {}

                    tools_used.append(tool_name)

                    # Callback: Tool Start
                    if step_callback:
                        await self._call(step_callback, "tool", {"name": tool_name, "args": tool_args})

                    # 执行工具（宽松超时 300 秒）
                    try:
                        result = await asyncio.wait_for(
                            self.tools.execute(tool_name, tool_args),
                            timeout=300.0,
                        )
                    except asyncio.TimeoutError:
                        result = f"Error: Tool '{tool_name}' timed out after 300 seconds."
                    except Exception as e:
                        result = f"Error executing '{tool_name}': {type(e).__name__} - {e}"

                    # 多模态处理（图片注入）
                    result_str, content_block = self._process_result(result, tool_name)

                    # Callback: Tool Result
                    if step_callback:
                        await self._call(step_callback, "tool_result", {
                            "name": tool_name, "args": tool_args,
                            "result": result_str[:800],
                        })

                    # 追加到消息序列
                    built_messages.append(Message(
                        role=MessageRole.TOOL,
                        content=content_block if content_block else result_str,
                        tool_call_id=tool_id,
                    ))

                continue

        # 3. 迭代上限兜底
        if iteration >= self.max_iterations and not final_response:
            final_response = f"V3 completed {iteration} iterations without a final response. Tools used: {', '.join(set(tools_used)) or 'none'}."

        elapsed = time.time() - start_time
        metrics = PerformanceMetrics(
            iterations=iteration,
            total_time=elapsed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            prompt_cache_hit_tokens=prompt_cache_hit_tokens,
            tools_used=tools_used,
            success=True,
            tool_calls=tool_calls_recorded or None,
        )

        logger.debug(f"V3 Loop done: {iteration} iters, {total_tokens} tokens, {elapsed:.2f}s")
        return final_response, metrics

    # ── 辅助方法 ──────────────────────────────────────────────────────────

    def _sanitize_messages(self, built_messages: List[Message]) -> List[Dict]:
        """净化消息序列：修复孤儿 tool 消息，保证 API schema 合规。"""
        messages = []
        for msg in built_messages:
            d = msg.to_dict()
            if d["role"] == "tool":
                prev = messages[-1] if messages else None
                is_orphan = True
                if prev and prev.get("role") == "assistant" and prev.get("tool_calls"):
                    tid = d.get("tool_call_id")
                    if tid and any(tc.get("id") == tid for tc in prev.get("tool_calls", [])):
                        is_orphan = False
                if is_orphan:
                    d["role"] = "user"
                    d["content"] = f"[System Observation (Tool Result)]:\n{d.get('content', '')}"
                    d.pop("tool_call_id", None)
                    d.pop("name", None)
            messages.append(d)
        return messages

    def _normalize_tool_calls(self, raw_calls, iteration: int) -> List[Dict]:
        """规范化 tool_calls 为统一格式。"""
        normalized = []
        for idx, tc in enumerate(raw_calls or []):
            fid = f"call_{iteration}_{idx}"
            if isinstance(tc, dict):
                fn = tc.get("function") or {}
                name = fn.get("name") or tc.get("name") or ""
                args_raw = fn.get("arguments") if fn else tc.get("arguments")
                args_str = json.dumps(args_raw, ensure_ascii=False) if isinstance(args_raw, dict) else (args_raw or "{}")
                normalized.append({
                    "id": tc.get("id") or fid,
                    "type": tc.get("type") or "function",
                    "function": {"name": name, "arguments": args_str},
                })
            else:
                name = getattr(tc, "name", "")
                args = getattr(tc, "arguments", {}) or {}
                normalized.append({
                    "id": getattr(tc, "id", None) or fid,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
                })
        return normalized

    def _process_result(self, result, tool_name: str):
        """处理工具返回值，包括多模态（图片）注入。"""
        result_str = str(result)
        content_block = None

        if isinstance(result, dict) and result.get("type") == "image":
            image_path = result.get("path")
            if image_path:
                try:
                    with open(image_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    content_block = [
                        {"type": "text", "text": f"Tool Output ({tool_name}): Screenshot captured at {image_path}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ]
                    result_str = f"Screenshot captured at {image_path}. (Image attached)"
                    logger.info(f"👁️ V3 Visual: {image_path} injected.")
                except Exception as e:
                    result_str = f"Error encoding image: {e}"

        return result_str, content_block

    @staticmethod
    async def _call(callback, event_type, data):
        """统一处理 sync/async callback。"""
        if asyncio.iscoroutinefunction(callback):
            await callback(event_type, data)
        else:
            callback(event_type, data)
