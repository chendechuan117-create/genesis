"""
Genesis V4 - 白盒执行引擎 (The Glassbox Loop)
"""

from typing import List, Dict, Any, Optional
import logging
import time
import json
import asyncio
import inspect

from genesis.core.base import Message, MessageRole, LLMResponse, PerformanceMetrics, LLMProvider
from genesis.core.registry import ToolRegistry
from genesis.v4.manager import FactoryManager

logger = logging.getLogger(__name__)


class V4Loop:
    """V4 白盒装配与执行引擎"""

    def __init__(
        self,
        tools: ToolRegistry,
        provider: LLMProvider,
        max_iterations: int = 50,
    ):
        self.tools = tools
        self.provider = provider
        self.max_iterations = max_iterations
        self.manager = FactoryManager()

    async def run(
        self,
        user_input: str,
        step_callback: Optional[Any] = None,
    ) -> tuple[str, PerformanceMetrics]:
        """
        V4 的双阶段执行流：
        Phase 1: 强制输出装配蓝图 (JSON) 并渲染给人类
        Phase 2: 依据蓝图执行工具并反馈
        """
        start_time = time.time()
        tools_used = []
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        
        # 构建 V4 的初始弹药库 (Manager 出厂指令 + User 输入)
        system_prompt = self.manager.build_system_prompt()
        built_messages = [
            Message(role=MessageRole.SYSTEM, content=system_prompt),
            Message(role=MessageRole.USER, content=user_input)
        ]

        iteration = 0
        final_response = ""
        blueprint_shown = False

        while iteration < self.max_iterations:
            iteration += 1

            if step_callback:
                await self._call(step_callback, "loop_start", iteration)

            logger.info(f"V4 Loop: Iteration {iteration}/{self.max_iterations}")

            # ── 1. 调用 LLM (Assembly / Reasoning) ──
            try:
                async def stream_handler(chunk_type, chunk_data):
                    if step_callback and chunk_type == "reasoning":
                        await self._call(step_callback, "reasoning", chunk_data)

                # Phase 1: 第一轮不给工具，强迫输出文本蓝图
                force_text = (iteration == 1)
                
                response = await self.provider.chat(
                    messages=[m.to_dict() for m in built_messages],
                    tools=list(self.tools.get_definitions()) if not force_text else None,
                    stream=True,
                    stream_callback=stream_handler,
                )
                input_tokens += getattr(response, "input_tokens", 0) or 0
                output_tokens += getattr(response, "output_tokens", 0) or 0
                total_tokens += getattr(response, "total_tokens", 0) or 0

                if not response.content and getattr(response, "reasoning_content", None):
                    response.content = response.reasoning_content

            except Exception as e:
                logger.error(f"V4 Loop: LLM call failed: {e}", exc_info=True)
                final_response = f"Error: 认知核心连接失败 - {str(e)[:300]}"
                break

            # ── 2. 处理蓝图 / 文本回复 ──
            if response.content:
                content_str = response.content

                # 在 Phase 1（没有工具调用），尝试解析 JSON 蓝图
                if not response.has_tool_calls and "{" in content_str and "}" in content_str and not blueprint_shown:
                    try:
                        json_str = content_str[content_str.find("{"):content_str.rfind("}")+1]
                        blueprint_ui = self.manager.render_blueprint_for_human(json_str)
                        
                        if step_callback:
                            await self._call(step_callback, "blueprint", blueprint_ui)
                        blueprint_shown = True
                            
                        built_messages.append(Message(
                            role=MessageRole.ASSISTANT, 
                            content=content_str
                        ))
                        built_messages.append(Message(
                            role=MessageRole.USER,
                            content="[System] Blueprint received. Now execute the plan using the available tools. After completing all steps, provide a final summary response to the user WITHOUT calling any more tools."
                        ))
                        continue  # 回到循环头，这次带工具
                    except Exception as e:
                        logger.warning(f"Failed to parse blueprint JSON: {e}")

                # 没有工具调用 = 最终回复，结束循环
                if not response.has_tool_calls:
                    final_response = content_str
                    break

            # Phase 1 强制文本，万一模型没有输出带 JSON 的内容
            if force_text and not blueprint_shown:
                built_messages.append(Message(
                    role=MessageRole.ASSISTANT,
                    content=response.content or ""
                ))
                built_messages.append(Message(
                    role=MessageRole.USER,
                    content="[System] Please output your assembly plan as a JSON object with keys: op_intent, active_nodes, execution_plan. Then I will let you use tools."
                ))
                continue

            # ── 3. 工具管线执行 (Execution Phase) ──
            if response.has_tool_calls:
                normalized = self._normalize_tool_calls(response.tool_calls, iteration)

                # 记录 assistant 消息（含 tool_calls）
                built_messages.append(Message(
                    role=MessageRole.ASSISTANT,
                    content=response.content or "",
                    tool_calls=normalized,
                ))

                for tc in normalized:
                    tool_name = tc["function"]["name"]
                    tool_args_raw = tc["function"].get("arguments") or "{}"
                    tool_id = tc["id"]

                    try:
                        tool_args = json.loads(tool_args_raw) if isinstance(tool_args_raw, str) else tool_args_raw
                    except json.JSONDecodeError:
                        tool_args = {}

                    tools_used.append(tool_name)

                    if step_callback:
                        await self._call(step_callback, "tool_start", {"name": tool_name})
                        
                    try:
                        result = await asyncio.wait_for(
                            self.tools.execute(tool_name, tool_args),
                            timeout=300.0,
                        )
                    except asyncio.TimeoutError:
                        result = f"Error: 耗时过长，被强行中断 (>300s)"
                    except Exception as e:
                        result = f"Error: 节点执行异常 - {e}"

                    result_str = str(result)
                    
                    if step_callback:
                        await self._call(step_callback, "tool_result", {
                            "name": tool_name, 
                            "result": result_str[:500]
                        })

                    built_messages.append(Message(
                        role=MessageRole.TOOL,
                        content=result_str,
                        tool_call_id=tool_id,
                    ))

                # 工具执行完毕，回到循环头让 LLM 基于结果产出下一步或最终回复
                continue

            # 空响应兜底
            if not response.content and not response.has_tool_calls:
                logger.warning(f"V4 Loop: Empty response at iteration {iteration}")
                built_messages.append(Message(
                    role=MessageRole.USER,
                    content="[System] Empty response. Please provide your answer or use a tool."
                ))
                continue

        # 兜底
        if iteration >= self.max_iterations and not final_response:
            final_response = f"V4 管线触达 {iteration} 次迭代上限。已装配挂载的节点：{', '.join(set(tools_used))}."

        elapsed = time.time() - start_time
        metrics = PerformanceMetrics(
            iterations=iteration,
            total_time=elapsed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            prompt_cache_hit_tokens=0,
            tools_used=tools_used,
            success=True,
            tool_calls=[]
        )

        return final_response, metrics

    def _normalize_tool_calls(self, raw_calls, iteration: int) -> List[Dict]:
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

    @staticmethod
    async def _call(callback, event_type, data):
        """统一处理 sync/async callback（兼容 __call__ 类实例）"""
        import asyncio
        result = callback(event_type, data)
        if asyncio.iscoroutine(result):
            await result
