"""
Genesis V4 核心执行引擎 (State Machine)
实现 G-Process (Thinker) -> Op-Process (Executor) -> C-Process (Reflector) 的解耦管线
"""

import json
import re
import time
import asyncio
import logging
import traceback
from typing import List, Dict, Any, Tuple, Optional

from genesis.core.base import Message, MessageRole, LLMProvider, PerformanceMetrics, ToolCall
from genesis.core.registry import ToolRegistry
from genesis.v4.manager import FactoryManager, NodeVault, NodeManagementTools

logger = logging.getLogger(__name__)

# C-Process 专属工具名（G/Op 禁止调用）
C_EXCLUSIVE_TOOLS = frozenset([
    "record_context_node", "record_lesson_node", "create_meta_node",
    "delete_node", "search_knowledge_nodes", "create_graph_node", "create_node_edge"
])

class V4Loop:
    """
    V4 核心管线
    
    Phases:
    1. G_PHASE (大脑): 拥有历史上下文，只能搜索。循环直至输出 Task Payload。
    2. OP_PHASE (手脚): 纯净上下文，接收 Payload，拥有执行工具，执行完退出。
    3. C_PHASE (反思): (Post-loop) 仅允许节点管理工具，沉淀知识。
    """

    def __init__(
        self,
        tools: ToolRegistry,
        provider: LLMProvider,
        max_iterations: int = 200,
    ):
        self.tools = tools
        self.provider = provider
        self.max_iterations = max_iterations
        
        # 单例管理器
        self.factory = FactoryManager()
        self.vault = NodeVault()
        
        self.metrics = PerformanceMetrics()
        
        # 共享状态（用于最后反思和记忆）
        self.user_input = ""
        self.g_messages: List[Message] = []
        self.op_messages: List[Message] = []
        self.execution_messages: List[Message] = []
        self.execution_reports: List[Dict[str, Any]] = []
        self.inferred_signature: Dict[str, Any] = {}

    async def run(self, user_input: str, step_callback: Any = None) -> Tuple[str, PerformanceMetrics]:
        """执行主管线 G -> Op -> G -> C (Subroutine Mode)"""
        self.metrics.start_time = time.time()
        self.user_input = user_input
        self.g_messages = []
        self.op_messages = []
        self.execution_messages = []
        self.execution_reports = []
        self.inferred_signature = self.vault.infer_metadata_signature(user_input)
        
        final_response = ""
        
        try:
            # === Phase 1 & 2: G-Process Main Loop & Op-Process Subroutine ===
            final_response = await self._run_main_loop(user_input, step_callback)
            
        except Exception as e:
            logger.error(f"Pipeline execution error: {traceback.format_exc()}")
            final_response = f"系统执行异常: {str(e)}"
            self.metrics.success = False
            
        self.metrics.total_time = time.time() - self.metrics.start_time
        
        # === Phase 3: C-Process (反思沉淀) ===
        # 只有在有足够执行动作时才进行反思
        if self._should_run_c_phase():
            await self._run_c_phase(step_callback)
        elif len(self.execution_messages) > 0:
            logger.info("Skipping C-Process: no high-value reflection signal detected.")
            
        # 保存这轮完整对话作为短期记忆
        self._save_memory(final_response)
        
        return final_response, self.metrics

    async def _run_main_loop(self, user_input: str, step_callback: Any) -> str:
        """运行 G-Process 主循环，按需挂起调用 Op"""
        logger.info(">>> Entering Phase 1: G-Process (Thinker)")
        await self._safe_callback(step_callback, "loop_start", {"phase": "G_PHASE"})
        
        g_prompt = self.factory.build_g_prompt(
            recent_memory=self.vault.get_recent_memory(),
            available_tools_info=self._build_op_tools_info(),
            knowledge_digest=self.vault.get_digest(),
            inferred_signature=self.vault.render_metadata_signature(self.inferred_signature)
        )
        self.g_messages = [
            Message(role=MessageRole.SYSTEM, content=g_prompt),
            Message(role=MessageRole.USER, content=user_input)
        ]
        
        search_tools = [self.tools.get("search_knowledge_nodes")]
        search_tools = [t for t in search_tools if t]
        schema = [t.to_schema() for t in search_tools]
        
        for i in range(self.max_iterations):
            response = await self.provider.chat(
                messages=[m.to_dict() for m in self.g_messages],
                tools=schema,
                stream=True,
                stream_callback=lambda ev, data: self._stream_proxy(step_callback, ev, data)
            )
            
            self._update_metrics(response)
            
            self.g_messages.append(Message(
                role=MessageRole.ASSISTANT,
                content=response.content,
                tool_calls=[tc.__dict__ for tc in response.tool_calls] if response.tool_calls else None
            ))
            
            if response.tool_calls:
                for tc in response.tool_calls:
                    await self._safe_callback(step_callback, "tool_start", {"name": tc.name, "args": tc.arguments})
                    
                    if tc.name == "search_knowledge_nodes":
                        search_args = dict(tc.arguments or {})
                        if self.inferred_signature:
                            search_args["signature"] = self.vault.merge_metadata_signatures(
                                self.inferred_signature,
                                search_args.get("signature")
                            )
                        res = await self.tools.execute(tc.name, search_args)
                        await self._safe_callback(step_callback, "search_result", {"name": tc.name, "result": res})
                    else:
                        res = f"G-Process has no permission to run tool {tc.name}"
                        
                    self.metrics.tools_used.append(tc.name)
                    
                    self.g_messages.append(Message(role=MessageRole.TOOL, content=res, tool_call_id=tc.id, name=tc.name))
                continue
                
            # 纯文本回复，检查是否包含 Dispatch Payload
            payload = self._parse_dispatch_payload(response.content)
            if payload:
                review_message = self._review_task_payload(payload)
                if review_message and not self._has_dispatch_review_override(payload):
                    logger.info("Dispatch reviewer requested payload revision before invoking Op.")
                    self.g_messages.append(Message(role=MessageRole.SYSTEM, content=review_message))
                    continue

                payload = self._strip_dispatch_review_override(payload)
                self._merge_signature_from_texts(payload.get("op_intent", ""), payload.get("instructions", ""))
                self._merge_signature_from_nodes(payload.get("active_nodes", []))
                logger.info("G-Process created Task Payload. Invoking Op-Process Subroutine...")
                # 渲染派发书给用户看
                rendered = self.factory.render_dispatch_for_human(payload)
                await self._safe_callback(step_callback, "blueprint", rendered)
                
                # 阻塞调用 Op-Process
                op_result = await self._run_op_phase(payload, step_callback)
                op_result_text = self.factory.render_op_result_for_g(op_result)
                signature_text = self.vault.render_metadata_signature(self.inferred_signature)
                signature_update_block = f"[任务签名更新]\n{signature_text}\n\n" if signature_text else ""
                
                # Op 执行完毕，将结果反馈给 G
                self.g_messages.append(Message(
                    role=MessageRole.SYSTEM,
                    content=f"[Op-Process 执行完毕]\n返回结果如下：\n{op_result_text}\n\n{signature_update_block}请基于上述执行结果，继续思考，或向用户输出最终回答。"
                ))
                
                # 重新将控制权交还给 G
                logger.info(">>> Resuming Phase 1: G-Process (Thinker)")
                await self._safe_callback(step_callback, "loop_start", {"phase": "G_PHASE"})
                continue
            else:
                # G 输出了普通文本且没有 payload，这被视为对用户的直接回复，管线结束
                logger.info("G-Process provided final response.")
                return response.content
                
        logger.warning("G-Process reached max iterations without finalizing.")
        return "大脑 (G) 思考达到最大迭代限制。"

    def _parse_dispatch_payload(self, content: str) -> Optional[Dict[str, Any]]:
        """从 G 的输出中提取 dispatch 块并转换为字典"""
        match = re.search(r"```dispatch\n(.*?)```", content, re.DOTALL | re.IGNORECASE)
        if not match:
            return None
            
        block = match.group(1).strip()
        
        payload = {
            "op_intent": "未定义目标",
            "active_nodes": [],
            "instructions": ""
        }
        
        # 简单提取，按关键字分割
        lines = block.split('\n')
        current_key = None
        instructions_lines = []
        
        for line in lines:
            if line.startswith("OP_INTENT:"):
                payload["op_intent"] = line[10:].strip()
            elif line.startswith("ACTIVE_NODES:"):
                nodes_str = line[13:].strip()
                if nodes_str and nodes_str.upper() != "NONE":
                    payload["active_nodes"] = [n.strip() for n in nodes_str.split(',')]
            elif line.startswith("INSTRUCTIONS:"):
                current_key = "instructions"
            elif current_key == "instructions":
                instructions_lines.append(line)
                
        if instructions_lines:
            payload["instructions"] = "\n".join(instructions_lines).strip()
            
        return payload

    def _has_dispatch_review_override(self, payload: Dict[str, Any]) -> bool:
        instructions = (payload.get("instructions") or "").strip()
        if not instructions:
            return False
        first_line = instructions.splitlines()[0].strip()
        return first_line.startswith("[REVIEW_OVERRIDE]")

    def _strip_dispatch_review_override(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        instructions = (payload.get("instructions") or "").strip()
        if not instructions:
            return payload
        lines = instructions.splitlines()
        if lines and lines[0].strip().startswith("[REVIEW_OVERRIDE]"):
            payload = dict(payload)
            payload["instructions"] = "\n".join(lines[1:]).strip()
        return payload

    def _merge_signature_from_texts(self, *texts: str):
        inferred_parts = [self.vault.infer_metadata_signature(text) for text in texts if text and str(text).strip()]
        self.inferred_signature = self.vault.merge_metadata_signatures(self.inferred_signature, *inferred_parts)

    def _merge_signature_from_artifacts(self, artifacts: List[str]):
        if not artifacts:
            return
        artifact_signature = self.vault.infer_metadata_signature_from_artifacts(artifacts)
        self.inferred_signature = self.vault.merge_metadata_signatures(self.inferred_signature, artifact_signature)

    def _merge_signature_from_nodes(self, node_ids: List[str]):
        if not node_ids:
            return
        expanded_signature = self.vault.expand_signature_from_node_ids(node_ids)
        self.inferred_signature = self.vault.merge_metadata_signatures(self.inferred_signature, expanded_signature)

    def _prepare_c_tool_args(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        prepared = dict(arguments or {})

        if tool_name == "search_knowledge_nodes":
            if self.inferred_signature:
                prepared["signature"] = self.vault.merge_metadata_signatures(
                    self.inferred_signature,
                    prepared.get("signature")
                )
            return prepared

        signature_write_tools = {"record_context_node", "record_lesson_node", "create_meta_node", "create_graph_node"}
        if tool_name not in signature_write_tools:
            return prepared

        text_parts: List[str] = []
        for key in ["title", "state_description", "trigger_verb", "trigger_noun", "trigger_context", "because_reason", "resolves", "content", "tags"]:
            value = prepared.get(key)
            if value:
                text_parts.append(str(value))
        action_steps = prepared.get("action_steps") or []
        if isinstance(action_steps, list):
            text_parts.extend([str(item) for item in action_steps if item])

        inferred_from_payload = self.vault.infer_metadata_signature("\n".join(text_parts))
        merged_signature = self.vault.merge_metadata_signatures(
            self.inferred_signature,
            inferred_from_payload,
            prepared.get("metadata_signature")
        )
        if merged_signature:
            prepared["metadata_signature"] = merged_signature

        if merged_signature and not prepared.get("verification_source"):
            prepared["verification_source"] = "reflection"

        return prepared

    def _review_task_payload(self, payload: Dict[str, Any]) -> Optional[str]:
        node_ids = [nid for nid in (payload.get("active_nodes") or []) if nid]
        if not node_ids:
            return None

        warnings: List[str] = []
        briefs = self.vault.get_node_briefs(node_ids)
        actionable_types = {"ASSET", "LESSON", "CONTEXT"}
        conditional_types = {"EPISODE"}
        support_types = {"ENTITY", "EVENT", "ACTION", "TOOL"}

        duplicate_ids = []
        seen = set()
        for nid in node_ids:
            if nid in seen and nid not in duplicate_ids:
                duplicate_ids.append(nid)
            seen.add(nid)
        if duplicate_ids:
            warnings.append(f"- ACTIVE_NODES 中存在重复节点: {', '.join(duplicate_ids)}")

        if len(node_ids) > 6:
            warnings.append(f"- 当前 ACTIVE_NODES 共有 {len(node_ids)} 个，可能过载；请优先保留最关键的 3-6 个节点。")

        missing_nodes = [nid for nid in node_ids if nid not in briefs]
        if missing_nodes:
            warnings.append(f"- 这些 ACTIVE_NODES 在知识库中不存在或当前不可见: {', '.join(missing_nodes)}")

        selected_briefs = [briefs[nid] for nid in node_ids if nid in briefs]
        if selected_briefs:
            actionable_selected = [b['node_id'] for b in selected_briefs if (b.get('type') or '').upper() in actionable_types]
            if not actionable_selected:
                selected_types = {(b.get('type') or '').upper() for b in selected_briefs}
                if selected_types and selected_types.issubset(conditional_types | support_types):
                    warnings.append("- 当前挂载节点几乎都是轨迹/图谱背景节点，缺少 ASSET / LESSON / CONTEXT，Op 可能拿不到直接可执行的指导。")

            expanded_selected_signature = self.vault.expand_signature_from_node_ids(node_ids)
            hard_keys = ["os_family", "runtime", "language", "framework", "environment_scope"]
            for key in hard_keys:
                normalized_inferred = self.vault.normalize_metadata_signature(self.inferred_signature)
                raw_expected = normalized_inferred.get(key)
                expected = set(raw_expected if isinstance(raw_expected, list) else ([raw_expected] if raw_expected else []))
                if not expected:
                    continue
                expanded_raw = expanded_selected_signature.get(key) if expanded_selected_signature else None
                expanded_values = set(expanded_raw if isinstance(expanded_raw, list) else ([expanded_raw] if expanded_raw else []))
                if expanded_values and not (expected & expanded_values):
                    warnings.append(f"- 当前任务推测签名的 {key}={','.join(sorted(expected))}，但这组 ACTIVE_NODES 的闭包签名更接近: {','.join(sorted(expanded_values))}")
                    continue
                conflicting_nodes = []
                matched = False
                for brief in selected_briefs:
                    node_signature = self.vault.parse_metadata_signature(brief.get("metadata_signature"))
                    node_values = set(node_signature.get(key, [])) if isinstance(node_signature.get(key), list) else ({node_signature.get(key)} if node_signature.get(key) else set())
                    if not node_values:
                        continue
                    if expected & node_values:
                        matched = True
                    else:
                        conflicting_nodes.append(f"{brief['node_id']}({','.join(sorted(node_values))})")
                if conflicting_nodes and not matched:
                    warnings.append(f"- 当前任务推测签名的 {key}={','.join(sorted(expected))}，但所选节点在该维度上整体更接近: {', '.join(conflicting_nodes)}")

            missing_prereqs: List[str] = []
            for brief in selected_briefs:
                prereq_str = (brief.get('prerequisites') or '').strip()
                if not prereq_str:
                    continue
                for prereq in [p.strip() for p in prereq_str.split(',') if p.strip()]:
                    if prereq not in node_ids and prereq not in missing_prereqs:
                        missing_prereqs.append(prereq)
            if missing_prereqs:
                warnings.append(f"- 有些已挂载节点声明了前置依赖，但这些依赖尚未纳入 ACTIVE_NODES: {', '.join(missing_prereqs)}")

        if not warnings:
            return None

        signature_text = self.vault.render_metadata_signature(self.inferred_signature)
        signature_block = f"当前任务推测签名: {signature_text}\n" if signature_text else ""

        return (
            "[Dispatch Review]\n"
            + signature_block
            + "检测到这份派发书的 ACTIVE_NODES 可能存在以下问题：\n"
            + "\n".join(warnings)
            + "\n请优先修正后重新输出 `dispatch`。"
            + "如果你确认当前派发是有意为之，请重新输出 `dispatch`，并让 `INSTRUCTIONS:` 第一行以 `[REVIEW_OVERRIDE]` 开头说明理由。"
        )

    def _parse_op_result(self, content: str) -> Dict[str, Any]:
        match = re.search(r"```op_result\n(.*?)```", content, re.DOTALL | re.IGNORECASE)
        block = match.group(1).strip() if match else content.strip()

        result = {
            "status": "UNKNOWN",
            "summary": "",
            "changes_made": [],
            "artifacts": [],
            "open_questions": [],
            "raw_output": content.strip()
        }

        current_key = None
        summary_lines: List[str] = []
        section_map = {
            "CHANGES_MADE:": "changes_made",
            "ARTIFACTS:": "artifacts",
            "OPEN_QUESTIONS:": "open_questions"
        }

        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("STATUS:"):
                result["status"] = line.split(":", 1)[1].strip() or "UNKNOWN"
                current_key = None
                continue
            if line == "SUMMARY:":
                current_key = "summary"
                continue
            if line in section_map:
                current_key = section_map[line]
                continue

            if current_key == "summary":
                summary_lines.append(line)
                continue

            if current_key in ["changes_made", "artifacts", "open_questions"]:
                item = line[1:].strip() if line.startswith("-") else line
                if item and item.upper() != "NONE":
                    result[current_key].append(item)

        result["summary"] = "\n".join(summary_lines).strip()

        has_structured_signal = match is not None or any(marker in block for marker in ["STATUS:", "SUMMARY:", "CHANGES_MADE:", "ARTIFACTS:", "OPEN_QUESTIONS:"])
        if not has_structured_signal:
            fallback_summary = block[:300] + ("..." if len(block) > 300 else "")
            result["status"] = "PARTIAL"
            result["summary"] = fallback_summary or "Op 返回了空白结果。"
            result["open_questions"] = ["Op 未按约定输出结构化执行报告，请 G 判断是否需要重新派发。"]
        elif not result["summary"]:
            result["summary"] = block[:300] + ("..." if len(block) > 300 else "")

        return result

    def _get_op_tools(self) -> List[Any]:
        op_tools = []
        for name in self.tools.list_tools():
            if name not in C_EXCLUSIVE_TOOLS:
                tool = self.tools.get(name)
                if tool:
                    op_tools.append(tool)
        return op_tools

    def _build_op_tools_info(self) -> str:
        tool_lines = []
        for tool in self._get_op_tools():
            tool_lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(tool_lines)

    def _should_run_c_phase(self) -> bool:
        if not self.execution_reports:
            return False
        if len(self.execution_reports) > 1:
            return True
        if any(report.get("artifacts") for report in self.execution_reports):
            return True
        if any(report.get("open_questions") for report in self.execution_reports):
            return True
        if any((report.get("status", "UNKNOWN") or "UNKNOWN").upper() in ["FAILED", "PARTIAL", "UNKNOWN"] for report in self.execution_reports):
            return True
        if sum(len(report.get("changes_made", []) or []) for report in self.execution_reports) >= 3:
            return True
        tool_steps = sum(1 for message in self.execution_messages if message.role == MessageRole.TOOL)
        if tool_steps >= 4:
            return True
        return False

    def _build_execution_report_summary(self) -> str:
        if not self.execution_reports:
            return "[Op 执行报告]\n- NONE"

        lines = ["[Op 执行报告]"]
        for idx, report in enumerate(self.execution_reports, 1):
            lines.append(f"{idx}. STATUS: {report.get('status', 'UNKNOWN')}")
            lines.append(f"   SUMMARY: {report.get('summary', '无摘要')}")

            changes = report.get("changes_made", []) or []
            lines.append("   CHANGES_MADE:")
            if changes:
                lines.extend([f"   - {item}" for item in changes])
            else:
                lines.append("   - NONE")

            artifacts = report.get("artifacts", []) or []
            lines.append("   ARTIFACTS:")
            if artifacts:
                lines.extend([f"   - {item}" for item in artifacts])
            else:
                lines.append("   - NONE")

            open_questions = report.get("open_questions", []) or []
            lines.append("   OPEN_QUESTIONS:")
            if open_questions:
                lines.extend([f"   - {item}" for item in open_questions])
            else:
                lines.append("   - NONE")

        return "\n".join(lines)

    async def _run_op_phase(self, task_payload: Dict[str, Any], step_callback: Any) -> Dict[str, Any]:
        """运行 Op-Process，纯粹的执行器"""
        logger.info(">>> Entering Phase 2: Op-Process (Executor)")
        await self._safe_callback(step_callback, "loop_start", {"phase": "OP_PHASE"})
        
        op_prompt = self.factory.build_op_prompt(task_payload)
        
        # Op 只有 system prompt，没有 user prompt (意图在 system 里了)
        self.op_messages = [Message(role=MessageRole.SYSTEM, content=op_prompt)]
        
        # 获取所有执行工具 (除了反思专属的)
        all_tools = self._get_op_tools()

        schema = [t.to_schema() for t in all_tools]
        
        for i in range(self.max_iterations):
            response = await self.provider.chat(
                messages=[m.to_dict() for m in self.op_messages],
                tools=schema,
                stream=True,
                stream_callback=lambda ev, data: self._stream_proxy(step_callback, ev, data)
            )
            
            self._update_metrics(response)
            
            self.op_messages.append(Message(
                role=MessageRole.ASSISTANT,
                content=response.content,
                tool_calls=[tc.__dict__ for tc in response.tool_calls] if response.tool_calls else None
            ))
            
            if response.tool_calls:
                for tc in response.tool_calls:
                    await self._safe_callback(step_callback, "tool_start", {"name": tc.name, "args": tc.arguments})
                    
                    if tc.name in C_EXCLUSIVE_TOOLS:
                        res = f"Error: Op-Process 禁止使用工具 {tc.name}"
                    else:
                        res = await self.tools.execute(tc.name, tc.arguments)
                        
                    await self._safe_callback(step_callback, "tool_result", {"name": tc.name, "result": res})
                    
                    self.metrics.tools_used.append(tc.name)
                    
                    self.op_messages.append(Message(role=MessageRole.TOOL, content=res, tool_call_id=tc.id, name=tc.name))
                continue
                
            # 没有工具调用，Op 结束任务并给出最终结果
            if not response.content.strip():
                self.op_messages.append(Message(role=MessageRole.SYSTEM, content="[系统警告] 收到空响应。请继续执行或总结最终结果。"))
                continue

            self.execution_messages.extend(self.op_messages)
            op_result = self._parse_op_result(response.content)
            self.execution_reports.append(op_result)
            self._merge_signature_from_texts(
                op_result.get("summary", ""),
                "\n".join(op_result.get("changes_made", []) or []),
                "\n".join(op_result.get("open_questions", []) or []),
                (op_result.get("raw_output", "") or "")[:1200]
            )
            self._merge_signature_from_artifacts(op_result.get("artifacts", []) or [])
            return op_result
            
        logger.warning("Op-Process reached max iterations.")
        self.execution_messages.extend(self.op_messages)
        timeout_result = {
            "status": "FAILED",
            "summary": "达到最大迭代次数限制，Op 被强制终止。",
            "changes_made": [],
            "artifacts": [],
            "open_questions": ["请 G 判断是否需要缩小任务范围后重新派发。"],
            "raw_output": "达到最大迭代次数限制，强制终止。"
        }
        self.execution_reports.append(timeout_result)
        self._merge_signature_from_texts(timeout_result.get("summary", ""), "\n".join(timeout_result.get("open_questions", []) or []))
        return timeout_result

    async def _run_c_phase(self, step_callback: Any):
        """运行 C-Process 反思循环，基于 Op 的执行轨迹"""
        logger.info(">>> Entering Phase 3: C-Process (Reflector)")
        
        report_summary = self._build_execution_report_summary()
        summary_lines = ["[Op 执行过程摘要]"]
        
        step_idx = 1
        for m in self.execution_messages:
            if m.role == MessageRole.TOOL:
                preview = str(m.content)[:200].replace("\n", " ") + "..." if len(str(m.content)) > 200 else str(m.content)
                summary_lines.append(f"{step_idx}. [TOOL] {m.name} -> {preview}")
                step_idx += 1
            elif m.role == MessageRole.ASSISTANT and not m.tool_calls:
                preview = str(m.content)[:100].replace("\n", " ") + "..."
                summary_lines.append(f"{step_idx}. [AI Result] {preview}")
                step_idx += 1
                
        execution_summary = "\n".join(summary_lines)
        signature_text = self.vault.render_metadata_signature(self.inferred_signature)
        signature_block = f"[当前任务推测签名]\n{signature_text}\n\n" if signature_text else ""
        
        reflection_system_prompt = f"""你是 Genesis 的后台反思进程 (C-Process)，你的代号是 "The Cartographer" (制图师)。
你的任务是审查以下执行器 (Op) 的 [执行过程摘要]，将其转化为结构化的 **Genesis Experience Graph (经验图谱)**。

{signature_block}

{report_summary}

{execution_summary}

[核心使命]
不要写日记！不要记流水账！你的职责是把执行轨迹转化为高价值元信息。
你必须先判断最小但最有用的沉淀形式，而不是默认画图。

[沉淀优先级]
1. **ASSET**: 如果这轮产出了可复用脚本、模板、配置、命令集合、验证器，优先创建 `ASSET`。
2. **LESSON**: 如果这轮暴露了错误假设、稳定排错路线、可复用方法，优先创建 `LESSON`。
3. **CONTEXT**: 如果这轮确认了稳定环境事实、约束、配置状态，创建 `CONTEXT`。
4. **EPISODE**: 只有当阶段性轨迹本身对未来继续工作有帮助时，才创建 `EPISODE`。
5. **GRAPH**: 只有在存在明确、高置信因果链时，才创建 `ENTITY / EVENT / ACTION` 节点及其边。

[LESSON 提炼原则]
- 不要总结“这次用了几个工具”或“先做了什么后做了什么”。
- 要优先问：**到底是哪一个错误假设，导致了这条轨迹？**
- 一个高价值 LESSON 应该长成：
  - 误判了什么
  - 哪个证据推翻了它
  - 以后再遇到什么信号时，应该先检查什么
- 如果只是一次性过程，没有可泛化原则，就不要写成 LESSON。

[图谱节点类型]
1. **ENTITY (实体)**: 静态对象/工具/服务/配置。
2. **EVENT (事件)**: 发生的现象 (报错/结果/日志)。
3. **ACTION (动作)**: 具体的执行动作/命令。

[关系类型 (Edges)]
- `TRIGGERS` (Action -> Event): 动作触发了现象 (e.g. pip install -> ssl error)
- `RESOLVES` (Action -> Event): 动作解决了现象 (e.g. use mirror -> ssl error)
- `REQUIRES` (Action -> Entity): 动作依赖某实体 (e.g. git clone -> proxy config)
- `LOCATED_AT` (Entity -> Entity): 实体的物理位置 (e.g. proxy -> localhost:20170)
- `RELATED_TO` (Any <-> Any): 弱相关性

[工作流]
1. 先判断这轮是否存在明确的长期价值；如果没有，直接回复 `NO_ACTION`。
2. 优先选择最小的高价值表示，避免重复写入。同一事实不要同时写成 LESSON、EPISODE 和图谱。
3. 如果你能从日志中稳定识别环境/任务特征（如 `os_family`、`runtime`、`language`、`framework`、`task_kind`、`error_kind`），在创建节点时尽量同时填写 `metadata_signature`。
4. 只有当命令输出、日志或明确证据已经确认某事实成立时，才把 `metadata_signature.validation_status` 标为 `validated`；否则优先用 `unverified` 或留空。
5. 如果你填写了验证结论，尽量同时给出 `verification_source`；只有在你明确知道验证时间时才填写 `last_verified_at`。
6. 对可复用产物使用 `create_meta_node` 创建 `ASSET`。
7. 对稳定环境事实使用 `record_context_node` 创建 `CONTEXT`。
8. 对错误假设修正、稳定方法、排错原则使用 `record_lesson_node` 创建 `LESSON`，其中 `because_reason` 要写“为什么原假设错了、正确判断依据是什么”。
9. 只有当阶段性轨迹本身值得未来继续推进时，才使用 `create_meta_node` 创建 `EPISODE`。
10. 只有当日志中存在清晰的因果关系时，才使用 `create_graph_node` 与 `create_node_edge` 构建图谱。

[可用工具]
- record_context_node: 创建 CONTEXT 环境事实节点
- record_lesson_node: 创建 LESSON 经验原则节点
- create_meta_node: 创建 ASSET / EPISODE 元信息节点
- create_graph_node: 创建节点
- create_node_edge: 创建边
- search_knowledge_nodes: 查重
- delete_node: 删错误节点
"""
        c_messages = [Message(role=MessageRole.SYSTEM, content=reflection_system_prompt)]
        
        c_tool_names = ["search_knowledge_nodes", "record_context_node", "record_lesson_node", "create_meta_node", "create_graph_node", "create_node_edge", "delete_node"]
        c_tools = [self.tools.get(n) for n in c_tool_names if self.tools.get(n)]
        c_schema = [t.to_schema() for t in c_tools]
        
        for _ in range(5): # 增加迭代次数以允许更复杂的图谱构建
            try:
                response = await self.provider.chat(
                    messages=[m.to_dict() for m in c_messages],
                    tools=c_schema,
                    stream=False
                )
                
                content = response.content
                tool_calls = response.tool_calls
                
                c_messages.append(Message(
                    role=MessageRole.ASSISTANT,
                    content=content,
                    tool_calls=[tc.__dict__ for tc in tool_calls] if tool_calls else None
                ))
                
                if "NO_ACTION" in content:
                    logger.info("C-Process decided NO_ACTION.")
                    break
                    
                if not tool_calls:
                    break
                    
                for tc in tool_calls:
                    if tc.name not in c_tool_names:
                        res = f"Error: C-Process 禁止使用工具 {tc.name}"
                    else:
                        prepared_args = self._prepare_c_tool_args(tc.name, tc.arguments)
                        res = await self.tools.execute(tc.name, prepared_args)
                        await self._safe_callback(step_callback, "tool_result", {"name": f"C-Process::{tc.name}", "result": res})
                    
                    c_messages.append(Message(role=MessageRole.TOOL, content=res, tool_call_id=tc.id, name=tc.name))
            except Exception as e:
                logger.error(f"Reflection step failed: {e}")
                break

    def _save_memory(self, agent_response: str):
        """保存本次对话到短期记忆"""
        try:
            if not self.user_input:
                return
            mgmt = NodeManagementTools(self.vault)
            mgmt.store_conversation(self.user_input, agent_response)
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")

    def _update_metrics(self, response: Any):
        self.metrics.input_tokens += response.input_tokens
        self.metrics.output_tokens += response.output_tokens
        self.metrics.total_tokens += response.total_tokens
        self.metrics.iterations += 1

    async def _safe_callback(self, callback, event, data):
        """安全调用回调"""
        if not callback: return
        try:
            res = callback(event, data)
            if asyncio.iscoroutine(res): await res
        except Exception as e:
            logger.error(f"Callback error ({event}): {e}")

    async def _stream_proxy(self, callback, event, data):
        """LLM 流式回调代理"""
        if callback: await self._safe_callback(callback, event, data)
