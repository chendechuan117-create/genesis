"""
Genesis V4 - 白盒执行引擎 (The Glassbox Loop)
核心：G 看标题组装蓝图 → Op 拉取内容执行 → 沉淀器提取新知识
"""

from typing import List, Dict, Any, Optional
import logging
import time
import json
import asyncio

from genesis.core.base import Message, MessageRole, LLMResponse, PerformanceMetrics, LLMProvider
from genesis.core.registry import ToolRegistry
from genesis.v4.manager import FactoryManager, Sedimenter

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
        
        # 将 G 的节点管理能力注册为临时工具（仅在反思阶段向 G 暴露）
        self.node_tools = self.manager.node_tools

    async def run(
        self,
        user_input: str,
        step_callback: Optional[Any] = None,
    ) -> tuple[str, PerformanceMetrics]:
        """
        V4 的三阶段执行流：
        Phase 1 (装配): 强制输出装配蓝图 (JSON) 并渲染给人类
        Phase 2 (执行): 依据蓝图执行工具并收集反馈
        Phase 3 (反思): G 审查执行结果，更新/删除元信息节点，给出最终结论
        """
        start_time = time.time()
        tools_used = []
        tool_results_log = []  # 收集工具结果，给沉淀器用
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
        selected_node_ids = []  # G 选中的节点 ID
        phase = "ASSEMBLY"  # ASSEMBLY, EXECUTION, REFLECTION

        while iteration < self.max_iterations:
            iteration += 1

            if step_callback:
                await self._call(step_callback, "loop_start", iteration)

            logger.info(f"V4 Loop: Iteration {iteration}/{self.max_iterations}")

            # ── 1. 调用 LLM ──
            try:
                async def stream_handler(chunk_type, chunk_data):
                    if step_callback and chunk_type == "reasoning":
                        await self._call(step_callback, "reasoning", chunk_data)

                # 根据当前阶段决定提供哪些工具
                current_tools = None
                if phase == "ASSEMBLY":
                    current_tools = None  # 装配阶段强制 JSON Text
                elif phase == "EXECUTION":
                    current_tools = list(self.tools.get_definitions())
                elif phase == "REFLECTION":
                    current_tools = [
                        {
                            "type": "function",
                            "function": {
                                "name": "create_or_update_node",
                                "description": "创建新节点或覆盖更新已有节点",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "node_id": {"type": "string", "description": "由大写字母和下划线组成，如 CTX_N8N_API 或 LESSON_DEPLOY"},
                                        "ntype": {"type": "string", "enum": ["CONTEXT", "LESSON"]},
                                        "title": {"type": "string", "description": "一句话标题，如 'n8n API认证方式'"},
                                        "content": {"type": "string", "description": "完整的知识详情"}
                                    },
                                    "required": ["node_id", "ntype", "title", "content"]
                                }
                            }
                        },
                        {
                            "type": "function",
                            "function": {
                                "name": "delete_node",
                                "description": "删除错误或过时的节点，避免污染未来",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "node_id": {"type": "string"}
                                    },
                                    "required": ["node_id"]
                                }
                            }
                        }
                    ]
                
                response = await self.provider.chat(
                    messages=[m.to_dict() for m in built_messages],
                    tools=current_tools,
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

                # Phase 1: 解析 JSON 蓝图
                if phase == "ASSEMBLY" and "{" in content_str and "}" in content_str:
                    try:
                        json_str = content_str[content_str.find("{"):content_str.rfind("}")+1]
                        plan = json.loads(json_str)
                        selected_node_ids = plan.get("active_nodes", [])
                        
                        blueprint_ui = self.manager.render_blueprint_for_human(json_str)
                        if step_callback:
                            await self._call(step_callback, "blueprint", blueprint_ui)
                        blueprint_shown = True
                        
                        node_contents = self.manager.vault.get_multiple_contents(selected_node_ids)
                        context_injection = ""
                        if node_contents:
                            ctx_lines = ["[已加载节点内容]"]
                            for nid, content in node_contents.items():
                                ctx_lines.append(f"[{nid}]: {content}")
                            context_injection = "\n".join(ctx_lines)
                        
                        self.manager.vault.increment_usage(selected_node_ids)
                            
                        built_messages.append(Message(
                            role=MessageRole.ASSISTANT, 
                            content=content_str
                        ))
                        built_messages.append(Message(
                            role=MessageRole.USER,
                            content=f"[System] 蓝图已收到。以下是所选节点的完整内容：\n{context_injection}\n\n执行阶段开始。请按计划调用工具执行。如果无需工具，请回复你的结论。"
                        ))
                        phase = "EXECUTION"
                        continue
                    except Exception as e:
                        logger.warning(f"Failed to parse blueprint JSON: {e}")

                # 纯文本处理
                if not response.has_tool_calls:
                    if phase == "EXECUTION":
                        # 执行阶段结束，强制进入反思阶段
                        built_messages.append(Message(
                            role=MessageRole.ASSISTANT,
                            content=content_str
                        ))
                        built_messages.append(Message(
                            role=MessageRole.USER,
                            content="[System] 执行阶段结束。现在进入反思阶段 (Phase 3)。\n你作为拥有意识的认知装配师，请审查刚才的对话和执行结果。是否有值得沉淀的新知识？是否有旧节点被证明是过时/错误的？用户的侧写/偏好（如 CTX_USER_PROFILE）是否需要更新？\n如果有，请务必使用 `create_or_update_node` 记录新知，或用 `delete_node` 删掉过时节点，给下一次苏醒的'你'留下干净、有用的上下文。\n完成反思的节点管理后（或如果不需要管理），再用中文向用户给出最终结论。"
                        ))
                        phase = "REFLECTION"
                        continue
                        
                    # 已经是反思阶段输出的结论了 -> 彻底结束
                    final_response = content_str
                    break

            # Phase 1 强制 JSON 文本，防跑偏
            if phase == "ASSEMBLY" and not blueprint_shown:
                built_messages.append(Message(
                    role=MessageRole.ASSISTANT,
                    content=response.content or ""
                ))
                built_messages.append(Message(
                    role=MessageRole.USER,
                    content='[System] 请必须输出装配蓝图 JSON：{"op_intent":"...", "active_nodes":[...], "execution_plan":[...]}'
                ))
                continue

            # ── 3. 工具管线执行 ──
            if response.has_tool_calls:
                normalized = self._normalize_tool_calls(response.tool_calls, iteration)

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

                    # 处理反思阶段的内置节点管理工具
                    if phase == "REFLECTION" and tool_name in ["create_or_update_node", "delete_node"]:
                        if step_callback:
                            await self._call(step_callback, "tool_start", {"name": f"🧠 {tool_name}"})
                            
                        try:
                            if tool_name == "create_or_update_node":
                                result_str = self.node_tools.create_or_update_node(**tool_args)
                            else:
                                result_str = self.node_tools.delete_node(**tool_args)
                        except Exception as e:
                            result_str = f"Error: 节点管理失败 - {e}"
                            
                        if step_callback:
                            await self._call(step_callback, "tool_result", {"name": f"🧠 {tool_name}", "result": result_str})
                        
                        built_messages.append(Message(
                            role=MessageRole.TOOL,
                            content=result_str,
                            tool_call_id=tool_id,
                        ))
                        continue

                    # 正常执行常规工具
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
                    tool_results_log.append({"name": tool_name, "result": result_str[:500]})
                    
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

                continue

            # 空响应兜底
            if not response.content and not response.has_tool_calls:
                logger.warning(f"V4 Loop: Empty response at iteration {iteration}")
                built_messages.append(Message(
                    role=MessageRole.USER,
                    content="[System] 空响应。请用中文回复或调用工具。"
                ))
                continue

        # 兜底
        if iteration >= self.max_iterations and not final_response:
            final_response = f"V4 管线触达 {iteration} 次迭代上限。已装配挂载的节点：{', '.join(set(tools_used))}."

        # ── POST: 对话记忆 ──
        try:
            # 存储本轮对话（为了 G 的初始上下文方向感）
            if final_response and user_input:
                self.node_tools.store_conversation(user_input, final_response)
        except Exception as e:
            logger.warning(f"Memory storage failed (non-critical): {e}")

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
        """统一处理 sync/async callback"""
        result = callback(event_type, data)
        if asyncio.iscoroutine(result):
            await result
