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
from genesis.v4.manager import FactoryManager, NodeManagementTools

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
        self.node_tools = NodeManagementTools(self.manager.vault)

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

            # ── 1. 调用 LLM (Phase 1/2/3) ──
            try:
                async def stream_handler(chunk_type, chunk_data):
                    if step_callback and chunk_type == "reasoning":
                        await self._call(step_callback, "reasoning", chunk_data)

                # 根据当前阶段决定提供哪些工具
                current_tools = None
                if phase == "ASSEMBLY":
                    current_tools = None  # 装配阶段强制不给工具
                elif phase == "EXECUTION":
                    current_tools = list(self.tools.get_definitions())
                
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
                    # G的自然总结和回复：
                    # 这里没有任何多余的思想包袱提示词，G 看到 Op 的执行结果后，
                    # 本身就会得出自然的人类的回复或结论。直接跳出循环即可。
                    final_response = content_str
                    built_messages.append(Message(
                        role=MessageRole.ASSISTANT,
                        content=content_str
                    ))
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

        # ── Phase 4: 独立反思 (C) ──
        if final_response:
            try:
                reflection_sys = """[System] (C进程) 交互已结束。请以认知节点管理员的身份，纵观上述所有对话上下文（包括你最初选配的节点目录、Op的工具执行反馈、以及最终得出的结论）。
如果发现：
1. 存在值得长期沉淀的新知识、新经验。
2. (关键) 刚才Op的工具执行反馈证明，你之前加载的某些节点内容有误、过时了。
3. 用户的侧写(如 CTX_USER_PROFILE)需要更新。

请综合上述前因后果，调用 `create_or_update_node` 或 `delete_node` 维护知识库。
如果不涉及上述情况，只需直接输出 "NO_ACTION" 即可。禁止回答任何多余废话。"""

                # 完美继承 G 和 Op 的全部上下文时间线 (G的图纸、报错、结论都在这里)
                reflection_msgs = list(built_messages)
                reflection_msgs.append(Message(role=MessageRole.USER, content=reflection_sys))

                reflection_tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": "create_or_update_node",
                            "description": "创建新节点或覆盖更新已有节点",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "node_id": {"type": "string", "description": "如 CTX_USER_PROFILE, LESSON_PYTHON_ENV"},
                                    "ntype": {"type": "string", "enum": ["CONTEXT", "LESSON"]},
                                    "title": {"type": "string"},
                                    "content": {"type": "string", "description": "节点详细内容"}
                                },
                                "required": ["node_id", "ntype", "title", "content"]
                            }
                        }
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "delete_node",
                            "description": "删除错误或过时的节点",
                            "parameters": {
                                "type": "object",
                                "properties": {"node_id": {"type": "string"}}
                            },
                            "required": ["node_id"]
                        }
                    }
                ]

                # 独立的一轮 LLM Call 用来反思
                c_resp = await self.provider.chat(
                    messages=[m.to_dict() for m in reflection_msgs],
                    tools=reflection_tools,
                    stream=False
                )
                
                input_tokens += getattr(c_resp, "input_tokens", 0) or 0
                output_tokens += getattr(c_resp, "output_tokens", 0) or 0
                total_tokens += getattr(c_resp, "total_tokens", 0) or 0

                if c_resp.has_tool_calls:
                    norm_calls = self._normalize_tool_calls(c_resp.tool_calls, 999)
                    for tc in norm_calls:
                        t_name = tc["function"]["name"]
                        t_args = json.loads(tc["function"].get("arguments", "{}"))
                        
                        if step_callback:
                            await self._call(step_callback, "tool_start", {"name": f"🧠 {t_name}"})
                            
                        # 执行反思节点的动作
                        try:
                            if t_name == "create_or_update_node":
                                res = self.node_tools.create_or_update_node(**t_args)
                            elif t_name == "delete_node":
                                res = self.node_tools.delete_node(**t_args)
                            else:
                                res = "Unknown node management tool"
                        except Exception as e:
                            res = f"Error interacting with node vault: {e}"
                            
                        if step_callback:
                            await self._call(step_callback, "tool_result", {"name": f"🧠 {t_name}", "result": res})

            except Exception as e:
                logger.warning(f"Phase 4 Reflection (C) failed: {e}")

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
