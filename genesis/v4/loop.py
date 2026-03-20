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
from genesis.core.tracer import Tracer
from genesis.core.models import DispatchPayload, OpResult
from genesis.v4.manager import FactoryManager, NodeVault, NodeManagementTools, TRUST_TIER_RANK, TOOL_EXEC_MIN_TIER

logger = logging.getLogger(__name__)

# Op 禁用工具名（G 和 C 可用，但 Op 不能调用）
OP_BLOCKED_TOOLS = frozenset([
    "record_context_node", "record_lesson_node", "create_meta_node",
    "delete_node", "search_knowledge_nodes", "create_graph_node", "create_node_edge",
    "record_tool_node"
])

# ── dispatch_to_op 工具 Schema ──────────────────────────────────
# 这是一个虚拟工具：LLM 看到它的 Schema 并通过 function calling 调用它，
# 但 loop 层拦截该调用并路由到 Op-Process，而非走普通 tool.execute 路径。
# 这从协议层（而非字符串层）消除了 "dispatch 意图" 与 "最终回复" 的歧义。
DISPATCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "dispatch_to_op",
        "description": "派发任务给执行器 Op-Process。当你完成思考和信息收集，需要 Op 去执行具体操作（如读写文件、运行命令、网络请求等）时，调用此工具。调用后系统会挂起你的运行，将参数交给 Op 执行，执行完毕后结果会作为此工具的返回值回传给你。",
        "parameters": {
            "type": "object",
            "properties": {
                "op_intent": {
                    "type": "string",
                    "description": "对 Op 目标的一句话明确指令"
                },
                "active_nodes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需要挂载给 Op 参考的节点 ID 列表（如 CTX_XXX, LESSON_XXX）。没有则传空数组 []"
                },
                "instructions": {
                    "type": "string",
                    "description": "给 Op 的详细执行步骤和上下文信息"
                }
            },
            "required": ["op_intent", "instructions"]
        }
    }
}

class V4Loop:
    """
    V4 核心管线
    
    Phases:
    1. G_PHASE (大脑): 拥有历史上下文，只能搜索和派发。循环直至输出最终回复。
    2. OP_PHASE (手脚): 纯净上下文，接收 Payload，拥有执行工具，执行完退出。
    3. C_PHASE (反思): (Post-loop) 仅允许节点管理工具，沉淀知识。
    """

    OP_MAX_ITERATIONS = 30  # Op 独立上限：30 轮足够完成单次派发，超出说明任务应拆分
    C_PHASE_MAX_ITER = {"FULL": 30, "LIGHT": 5, "SKIP": 0}
    TOOL_EXEC_TIMEOUT = 120  # 工具执行超时（秒），防止挂起的 HTTP/命令阻塞整个管线

    def __init__(
        self,
        tools: ToolRegistry,
        provider: LLMProvider,
        max_iterations: int = 20,
        c_phase_blocking: bool = False,
    ):
        self.tools = tools
        self.provider = provider
        self.max_iterations = max_iterations
        self.c_phase_blocking = c_phase_blocking
        
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

    async def run(self, user_input: str, step_callback: Any = None, image_paths: Optional[List[str]] = None) -> Tuple[str, PerformanceMetrics]:
        """执行主管线 G -> Op -> G -> C (Subroutine Mode)"""
        self.metrics.start_time = time.time()
        self.user_input = user_input
        self.image_paths = image_paths or []
        self.g_messages = []
        self.op_messages = []
        self.execution_messages = []
        self.execution_reports = []
        self.execution_active_nodes: List[str] = []  # Knowledge Arena: 追踪被使用的节点
        # 签名推断只用用户实际请求，排除频道历史等上下文噪音
        _sig_input = user_input
        if "[GENESIS_USER_REQUEST_START]" in user_input:
            _sig_input = user_input.split("[GENESIS_USER_REQUEST_START]", 1)[1]
        self.inferred_signature = self.vault.infer_metadata_signature(_sig_input)
        
        # === Tracing ===
        self.tracer = Tracer.get_instance()
        self.trace_id = self.tracer.start_trace(user_input)
        self._phase_count = 0
        self._llm_call_count = 0
        self._tool_call_count = 0
        
        final_response = ""
        
        try:
            # === Phase 1 & 2: G-Process Main Loop & Op-Process Subroutine ===
            final_response = await self._run_main_loop(user_input, step_callback)
            
        except Exception as e:
            logger.error(f"Pipeline execution error: {traceback.format_exc()}")
            final_response = f"系统执行异常: {str(e)}"
            self.metrics.success = False
            
        # 兜底防护：确保 final_response 永不为空
        if not final_response or not str(final_response).strip():
            logger.error(f"CRITICAL: final_response is empty after pipeline. g_messages count: {len(self.g_messages)}, op_messages count: {len(self.op_messages)}, llm_calls: {self._llm_call_count}, tool_calls: {self._tool_call_count}")
            # 尝试从 g_messages 中提取最后一条 assistant 消息作为备用
            for msg in reversed(self.g_messages):
                if msg.role == MessageRole.ASSISTANT and msg.content and msg.content.strip():
                    final_response = msg.content
                    logger.info("Recovered response from last assistant message in g_messages.")
                    break
            if not final_response or not str(final_response).strip():
                final_response = "抱歉，我在处理你的请求时遇到了问题，没有生成有效的回复。请再试一次。"
        
        self.metrics.total_time = time.time() - self.metrics.start_time
        
        # 保存这轮完整对话作为短期记忆（同步，确保记忆不丢）
        self._save_memory(final_response)
        
        # === Phase 3: C-Process (反思沉淀) ===
        # 长生命周期（Discord bot）: 后台 create_task，不阻塞用户
        # 短生命周期（API server）: await 等待完成，防止 event loop 关闭时截断
        c_mode = self._determine_c_phase_mode()
        if c_mode != "SKIP":
            if self.c_phase_blocking:
                await self._run_c_phase_safe(step_callback, c_mode)
                logger.info(f"C-Process completed (blocking mode={c_mode}, G={self.metrics.g_tokens}t, Op={self.metrics.op_tokens}t).")
            else:
                asyncio.create_task(self._run_c_phase_safe(step_callback, c_mode))
                logger.info(f"C-Process launched in background (mode={c_mode}, G={self.metrics.g_tokens}t, Op={self.metrics.op_tokens}t).")
        elif len(self.execution_messages) > 0:
            logger.info(f"Skipping C-Process: mode=SKIP (G={self.metrics.g_tokens}t, Op={self.metrics.op_tokens}t).")
        
        self.vault.heartbeat("main_loop", "idle", f"done G={self.metrics.g_tokens}t Op={self.metrics.op_tokens}t")
        
        # === End Trace ===
        self.tracer.end_trace(
            self.trace_id,
            status="completed" if self.metrics.success else "error",
            final_response=final_response,
            input_tokens=self.metrics.input_tokens,
            output_tokens=self.metrics.output_tokens,
            total_tokens=self.metrics.total_tokens,
            phase_count=self._phase_count,
            llm_call_count=self._llm_call_count,
            tool_call_count=self._tool_call_count
        )
        
        return final_response, self.metrics

    async def _run_c_phase_safe(self, step_callback: Any, mode: str = "FULL"):
        """后台安全包装器：捕获 C-Process 异常，防止后台任务静默崩溃"""
        try:
            await self._run_c_phase(step_callback, mode)
        except Exception as e:
            logger.error(f"C-Process background task failed: {e}", exc_info=True)

    async def _run_main_loop(self, user_input: str, step_callback: Any) -> str:
        """运行 G-Process 主循环，按需挂起调用 Op"""
        logger.info(">>> Entering Phase 1: G-Process (Thinker)")
        await self._safe_callback(step_callback, "loop_start", {"phase": "G_PHASE"})
        self._phase_count += 1
        self._g_span = self.tracer.start_span(self.trace_id, "G_PHASE", span_type="phase", phase="G")
        
        self.vault.heartbeat("main_loop", "running", f"G-Phase start: {user_input[:60]}")
        g_prompt = self.factory.build_g_prompt(
            recent_memory=self.vault.get_recent_memory(),
            available_tools_info=self._build_op_tools_info(),
            knowledge_digest=self.vault.get_digest(),
            inferred_signature=self.vault.render_metadata_signature(self.inferred_signature),
            daemon_status=self.vault.get_daemon_status_summary()
        )
        
        # Build User Content (Multimodal if images exist)
        if hasattr(self, 'image_paths') and self.image_paths:
            import base64
            user_content = [{"type": "text", "text": user_input}]
            for path in self.image_paths:
                try:
                    with open(path, "rb") as f:
                        b64_data = base64.b64encode(f.read()).decode('utf-8')
                        user_content.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}
                        })
                except Exception as e:
                    logger.error(f"Failed to read image {path}: {e}")
        else:
            user_content = user_input

        self.g_messages = [
            Message(role=MessageRole.SYSTEM, content=g_prompt),
            Message(role=MessageRole.USER, content=user_content)
        ]
        
        search_tools = [self.tools.get("search_knowledge_nodes")]
        search_tools = [t for t in search_tools if t]
        schema = [t.to_schema() for t in search_tools] + [DISPATCH_TOOL_SCHEMA]
        
        for i in range(self.max_iterations):
            # === 跨进程向量同步：拉取 Scavenger/Fermentor 新增的节点向量 ===
            self.vault.sync_vector_matrix_incremental()
            # === G 蒸发机制：压缩旧的搜索结果和 Op 返回 ===
            self._evaporate_g_messages()
            
            self._llm_call_count += 1
            response = await self.provider.chat(
                messages=[m.to_dict() for m in self.g_messages],
                tools=schema,
                stream=True,
                stream_callback=lambda ev, data: self._stream_proxy(step_callback, ev, data),
                _trace_id=self.trace_id, _trace_phase="G", _trace_parent=self._g_span
            )
            
            self._update_metrics(response)
            
            self.g_messages.append(Message(
                role=MessageRole.ASSISTANT,
                content=response.content,
                tool_calls=[tc.__dict__ for tc in response.tool_calls] if response.tool_calls else None
            ))
            
            if response.tool_calls:
                # ── 分拣：将 dispatch_to_op 从普通工具调用中分离 ──
                dispatch_tc = None
                regular_calls = []
                for tc in response.tool_calls:
                    if tc.name == "dispatch_to_op":
                        dispatch_tc = tc
                    else:
                        regular_calls.append(tc)
                
                # ── 先处理普通工具（search 等）──
                for tc in regular_calls:
                    await self._safe_callback(step_callback, "tool_start", {"name": tc.name, "args": tc.arguments})
                    self._tool_call_count += 1
                    t0 = time.time()
                    
                    if tc.name == "search_knowledge_nodes":
                        search_args = dict(tc.arguments or {})
                        if self.inferred_signature:
                            search_args["signature"] = self.vault.merge_metadata_signatures(
                                self.inferred_signature,
                                search_args.get("signature")
                            )
                        # Query Expansion: 自动注入对话上下文
                        if not search_args.get("conversation_context"):
                            recent = self.vault.get_recent_memory(limit=2)
                            if recent:
                                search_args["conversation_context"] = recent[:300]
                        try:
                            res = await asyncio.wait_for(
                                self.tools.execute(tc.name, search_args),
                                timeout=self.TOOL_EXEC_TIMEOUT
                            )
                        except asyncio.TimeoutError:
                            res = f"Error: 搜索超时（{self.TOOL_EXEC_TIMEOUT}秒），请缩小搜索范围后重试。"
                            logger.warning(f"G tool timeout: {tc.name} exceeded {self.TOOL_EXEC_TIMEOUT}s")
                        await self._safe_callback(step_callback, "search_result", {"name": tc.name, "result": res})
                    else:
                        res = f"G-Process has no permission to run tool {tc.name}"
                    
                    self.tracer.log_tool_call(
                        self.trace_id, parent=self._g_span, phase="G",
                        tool_name=tc.name, tool_args=tc.arguments,
                        tool_result=str(res), duration_ms=(time.time() - t0) * 1000
                    )
                    self.metrics.tools_used.append(tc.name)
                    self.g_messages.append(Message(role=MessageRole.TOOL, content=res, tool_call_id=tc.id, name=tc.name))
                
                # ── dispatch_to_op: 协议层派发（核心路径）──
                if dispatch_tc:
                    payload = {
                        "op_intent": (dispatch_tc.arguments or {}).get("op_intent", "未定义目标"),
                        "active_nodes": (dispatch_tc.arguments or {}).get("active_nodes") or [],
                        "instructions": (dispatch_tc.arguments or {}).get("instructions", "")
                    }
                    
                    # 派发审查
                    review_message = self._review_task_payload(payload)
                    if review_message and not self._has_dispatch_review_override(payload):
                        logger.info("Dispatch reviewer requested payload revision.")
                        self.g_messages.append(Message(
                            role=MessageRole.TOOL,
                            content=f"[Dispatch Review] {review_message}",
                            tool_call_id=dispatch_tc.id, name="dispatch_to_op"
                        ))
                        continue
                    
                    payload = self._strip_dispatch_review_override(payload)
                    self._merge_signature_from_texts(payload.get("op_intent", ""), payload.get("instructions", ""))
                    self._merge_signature_from_nodes(payload.get("active_nodes", []))
                    logger.info("G-Process dispatched via tool call. Invoking Op-Process...")
                    dispatched_nodes = [n for n in payload.get("active_nodes", []) if n and not n.startswith("MEM_CONV")]
                    self.execution_active_nodes.extend(dispatched_nodes)
                    
                    rendered = self.factory.render_dispatch_for_human(payload)
                    await self._safe_callback(step_callback, "blueprint", rendered)
                    
                    # 阻塞调用 Op-Process（_run_op_phase 内部已 append execution_reports）
                    op_result = await self._run_op_phase(payload, step_callback)
                    op_result_text = self.factory.render_op_result_for_g(op_result)
                    signature_text = self.vault.render_metadata_signature(self.inferred_signature)
                    signature_update_block = f"[任务签名更新]\n{signature_text}\n\n" if signature_text else ""
                    
                    # Op 结果作为 dispatch_to_op 的工具返回值回传给 G
                    self.g_messages.append(Message(
                        role=MessageRole.TOOL,
                        content=f"[Op-Process 执行完毕]\n返回结果如下：\n{op_result_text}\n\n{signature_update_block}请基于上述执行结果，继续思考，或向用户输出最终回答。",
                        tool_call_id=dispatch_tc.id, name="dispatch_to_op"
                    ))
                    
                    logger.info(">>> Resuming G-Process after Op completion")
                    await self._safe_callback(step_callback, "loop_start", {"phase": "G_PHASE"})
                
                continue
                
            # ── 纯文本回复路径 ──
            # 主路径: 无 tool_calls → G 的文本就是对用户的最终回复
            # 回退路径: 如果文本中仍包含 dispatch 块（LLM 没走 tool call），尝试解析
            payload = self._parse_dispatch_payload(response.content)
            if payload:
                logger.warning("G-Process used legacy text-based dispatch instead of tool call. Handling as fallback.")
                review_message = self._review_task_payload(payload)
                if review_message and not self._has_dispatch_review_override(payload):
                    logger.info("Dispatch reviewer requested payload revision before invoking Op.")
                    self.g_messages.append(Message(role=MessageRole.SYSTEM, content=review_message))
                    continue

                payload = self._strip_dispatch_review_override(payload)
                self._merge_signature_from_texts(payload.get("op_intent", ""), payload.get("instructions", ""))
                self._merge_signature_from_nodes(payload.get("active_nodes", []))
                logger.info("G-Process created Task Payload (fallback). Invoking Op-Process Subroutine...")
                dispatched_nodes = [n for n in payload.get("active_nodes", []) if n and not n.startswith("MEM_CONV")]
                self.execution_active_nodes.extend(dispatched_nodes)
                rendered = self.factory.render_dispatch_for_human(payload)
                await self._safe_callback(step_callback, "blueprint", rendered)
                
                op_result = await self._run_op_phase(payload, step_callback)
                op_result_text = self.factory.render_op_result_for_g(op_result)
                signature_text = self.vault.render_metadata_signature(self.inferred_signature)
                signature_update_block = f"[任务签名更新]\n{signature_text}\n\n" if signature_text else ""
                
                self.g_messages.append(Message(
                    role=MessageRole.SYSTEM,
                    content=f"[Op-Process 执行完毕]\n返回结果如下：\n{op_result_text}\n\n{signature_update_block}请基于上述执行结果，继续思考，或向用户输出最终回答。"
                ))
                
                logger.info(">>> Resuming Phase 1: G-Process (Thinker)")
                await self._safe_callback(step_callback, "loop_start", {"phase": "G_PHASE"})
                continue
            else:
                # G 输出了普通文本且没有 dispatch 意图 → 最终回复
                if response.content and response.content.strip():
                    logger.info(f"G-Process provided final response. length={len(response.content)}, preview={response.content[:80]!r}")
                    self.tracer.end_span(self._g_span)
                    return response.content
                else:
                    logger.warning(f"G-Process returned empty content (iter {i}). Retrying.")
                    if self.g_messages and self.g_messages[-1].role == MessageRole.ASSISTANT:
                        self.g_messages.pop()
                    continue
                
        logger.warning(f"G-Process reached max iterations ({self.max_iterations}) without finalizing.")
        self.tracer.end_span(self._g_span, status="timeout")
        # 尝试从 g_messages 找最后一条有内容的 assistant 消息
        for msg in reversed(self.g_messages):
            if msg.role == MessageRole.ASSISTANT and msg.content and msg.content.strip():
                logger.info("Recovered response from last G assistant message after timeout.")
                return msg.content
        return "思考达到最大迭代限制，未能生成回复。"

    def _parse_dispatch_payload(self, content: str) -> Optional[Dict[str, Any]]:
        """从 G 的输出中提取 dispatch 块并转换为字典"""
        # 1. 尝试标准代码块提取 (宽松匹配 newline)
        match = re.search(r"```dispatch\s*(.*?)```", content, re.DOTALL | re.IGNORECASE)
        
        block = ""
        if match:
            block = match.group(1).strip()
        else:
            # 2. 启发式回退：要求关键字在行首出现（防止 G 在解释性文本中误触发）
            if re.search(r"^OP_INTENT:", content, re.MULTILINE) and re.search(r"^INSTRUCTIONS:", content, re.MULTILINE):
                logger.warning("G-Process output dispatch keywords but missed code block. Applying heuristic parsing.")
                block = content.strip()
            else:
                return None
        
        op_intent = "未定义目标"
        active_nodes = []
        instructions_lines = []
        current_key = None
        
        for line in block.split('\n'):
            if line.startswith("OP_INTENT:"):
                op_intent = line[10:].strip()
            elif line.startswith("ACTIVE_NODES:"):
                nodes_str = line[13:].strip()
                if nodes_str and nodes_str.upper() != "NONE":
                    active_nodes = [n.strip() for n in nodes_str.split(',')]
            elif line.startswith("INSTRUCTIONS:"):
                current_key = "instructions"
            elif current_key == "instructions":
                instructions_lines.append(line)
        
        payload = DispatchPayload(
            op_intent=op_intent,
            active_nodes=active_nodes,
            instructions="\n".join(instructions_lines).strip()
        )
        return payload.model_dump()

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

        # C 自己写的签名优先；没写则从节点内容推断；不再强制合并全局签名（防止污染）
        c_signature = prepared.get("metadata_signature")
        if not c_signature:
            text_parts: List[str] = []
            for key in ["title", "state_description", "trigger_verb", "trigger_noun", "trigger_context", "because_reason", "resolves", "content", "tags"]:
                value = prepared.get(key)
                if value:
                    text_parts.append(str(value))
            action_steps = prepared.get("action_steps") or []
            if isinstance(action_steps, list):
                text_parts.extend([str(item) for item in action_steps if item])
            c_signature = self.vault.infer_metadata_signature("\n".join(text_parts))

        if c_signature:
            prepared["metadata_signature"] = c_signature

        if c_signature and not prepared.get("verification_source"):
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

        status = "UNKNOWN"
        changes_made: List[str] = []
        artifacts: List[str] = []
        open_questions: List[str] = []

        current_key = None
        summary_lines: List[str] = []
        findings_lines: List[str] = []
        section_map = {
            "CHANGES_MADE:": "changes_made",
            "ARTIFACTS:": "artifacts",
            "OPEN_QUESTIONS:": "open_questions"
        }
        list_buckets = {"changes_made": changes_made, "artifacts": artifacts, "open_questions": open_questions}

        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("STATUS:"):
                status = line.split(":", 1)[1].strip() or "UNKNOWN"
                current_key = None
                continue
            if line == "SUMMARY:":
                current_key = "summary"
                continue
            if line == "FINDINGS:":
                current_key = "findings"
                continue
            if line in section_map:
                current_key = section_map[line]
                continue

            if current_key == "summary":
                summary_lines.append(line)
                continue
            if current_key == "findings":
                findings_lines.append(line)
                continue

            if current_key in list_buckets:
                item = line[1:].strip() if line.startswith("-") else line
                if item and item.upper() != "NONE":
                    list_buckets[current_key].append(item)

        summary = "\n".join(summary_lines).strip()
        findings = "\n".join(findings_lines).strip()

        has_structured_signal = match is not None or any(marker in block for marker in ["STATUS:", "SUMMARY:", "FINDINGS:", "CHANGES_MADE:", "ARTIFACTS:", "OPEN_QUESTIONS:"])
        if not has_structured_signal:
            fallback_summary = block[:300] + ("..." if len(block) > 300 else "")
            status = "PARTIAL"
            summary = fallback_summary or "Op 返回了空白结果。"
            open_questions = ["Op 未按约定输出结构化执行报告，请 G 判断是否需要重新派发。"]
        elif not summary:
            summary = block[:300] + ("..." if len(block) > 300 else "")

        result = OpResult(
            status=status, summary=summary, findings=findings,
            changes_made=changes_made, artifacts=artifacts,
            open_questions=open_questions, raw_output=content.strip()
        )
        return result.model_dump()

    def _load_tool_nodes_from_active_nodes(self, active_nodes: List[str]) -> List[str]:
        """从 active_nodes 中加载 TOOL 节点并动态注册工具（带信任闸门）"""
        loaded_tools = []
        min_rank = TRUST_TIER_RANK.get(TOOL_EXEC_MIN_TIER, 3)
        # 批量获取 TOOL 节点的 trust_tier（通过公开 API，避免直接访问 _conn）
        tool_node_ids = [nid for nid in active_nodes if nid.startswith("TOOL_")]
        briefs = self.vault.get_node_briefs(tool_node_ids) if tool_node_ids else {}
        for node_id in tool_node_ids:
            brief = briefs.get(node_id, {})
            tier = brief.get("trust_tier") or "REFLECTION"
            tier_rank = TRUST_TIER_RANK.get(tier, 0)
            if tier_rank < min_rank:
                logger.warning(f"⛔ TOOL 节点 [{node_id}] 信任等级不足 (tier={tier}, 需要>={TOOL_EXEC_MIN_TIER})，跳过 exec")
                continue
            source_code = self.vault.get_node_content(node_id)
            if source_code:
                import re
                tool_name_match = re.search(r'def name\(self\) -> str:\s*return "([^"]+)"', source_code)
                if not tool_name_match:
                    tool_name_match = re.search(r"def name\(self\) -> str:\s*return '([^']+)'", source_code)
                if tool_name_match:
                    tool_name = tool_name_match.group(1)
                    if self.tools.register_from_source(tool_name, source_code, node_id=node_id, trust_tier=tier):
                        loaded_tools.append(tool_name)
                        logger.info(f"动态注册工具: {tool_name} from {node_id} (tier={tier})")
                    else:
                        logger.warning(f"动态注册工具失败: {node_id}")
                else:
                    logger.warning(f"无法从 TOOL 节点提取工具名称: {node_id}")
        return loaded_tools


    def _get_op_tools(self) -> List[Any]:
        op_tools = []
        for name in self.tools.list_tools():
            if name not in OP_BLOCKED_TOOLS:
                tool = self.tools.get(name)
                if tool:
                    op_tools.append(tool)
        return op_tools

    def _build_op_tools_info(self) -> str:
        tool_lines = []
        for tool in self._get_op_tools():
            tool_lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(tool_lines)

    def _determine_c_phase_mode(self) -> str:
        """信号质量 → C-Phase 模式: FULL / LIGHT / SKIP"""
        if not self.execution_reports:
            return "SKIP"

        # 信号质量评估
        high_value = False
        if len(self.execution_reports) > 1:
            high_value = True
        elif any(report.get("artifacts") for report in self.execution_reports):
            high_value = True
        elif any(report.get("open_questions") for report in self.execution_reports):
            high_value = True
        elif any((report.get("status", "UNKNOWN") or "UNKNOWN").upper() in ["FAILED", "PARTIAL", "UNKNOWN"] for report in self.execution_reports):
            high_value = True
        elif sum(len(report.get("changes_made", []) or []) for report in self.execution_reports) >= 3:
            high_value = True

        tool_steps = sum(1 for message in self.execution_messages if message.role == MessageRole.TOOL)
        if tool_steps >= 4:
            high_value = True

        if not high_value:
            return "SKIP"

        return "FULL"

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
        self._phase_count += 1
        op_span = self.tracer.start_span(
            self.trace_id, "OP_PHASE", span_type="phase", phase="Op",
            meta={"op_intent": task_payload.get("op_intent", "")}
        )
        
        # === 动态加载 TOOL_NODE ===
        active_nodes = task_payload.get("active_nodes", [])
        tool_nodes_loaded = self._load_tool_nodes_from_active_nodes(active_nodes)
        if tool_nodes_loaded:
            logger.info(f"动态加载了 {len(tool_nodes_loaded)} 个 TOOL 节点")
        # 记录本次 session 动态加载的工具名，Op 结束后注销
        session_dynamic_tools = list(tool_nodes_loaded)
        
        op_prompt = self.factory.build_op_prompt(task_payload)
        
        # Op 只有 system prompt，没有 user prompt (意图在 system 里了)
        self.op_messages = [Message(role=MessageRole.SYSTEM, content=op_prompt)]
        
        # 获取所有执行工具 (除了反思专属的)
        all_tools = self._get_op_tools()

        schema = [t.to_schema() for t in all_tools]
        
        for i in range(self.OP_MAX_ITERATIONS):
            # === 蒸发机制：在发送给 LLM 前，压缩旧的 TOOL 消息 ===
            # 原理：LLM 的 ASSISTANT 回复已隐式总结了上一轮 TOOL 输出的关键信息
            #       因此旧的 TOOL 原文可以安全地"蒸发"为存根，不丢失信息
            self._evaporate_op_messages()
            
            self._llm_call_count += 1
            response = await self.provider.chat(
                messages=[m.to_dict() for m in self.op_messages],
                tools=schema,
                stream=True,
                stream_callback=lambda ev, data: self._stream_proxy(step_callback, ev, data),
                _trace_id=self.trace_id, _trace_phase="Op", _trace_parent=op_span
            )
            
            self._update_metrics(response, phase="Op")
            
            self.op_messages.append(Message(
                role=MessageRole.ASSISTANT,
                content=response.content,
                tool_calls=[tc.__dict__ for tc in response.tool_calls] if response.tool_calls else None
            ))
            
            if response.tool_calls:
                for tc in response.tool_calls:
                    await self._safe_callback(step_callback, "tool_start", {"name": tc.name, "args": tc.arguments})
                    self._tool_call_count += 1
                    t0 = time.time()
                    
                    if tc.name in OP_BLOCKED_TOOLS:
                        res = f"Error: Op-Process 禁止使用工具 {tc.name}"
                    else:
                        try:
                            res = await asyncio.wait_for(
                                self.tools.execute(tc.name, tc.arguments),
                                timeout=self.TOOL_EXEC_TIMEOUT
                            )
                        except asyncio.TimeoutError:
                            res = f"Error: 工具 {tc.name} 执行超时（{self.TOOL_EXEC_TIMEOUT}秒），已强制终止。"
                            logger.warning(f"Op tool timeout: {tc.name} exceeded {self.TOOL_EXEC_TIMEOUT}s")
                    
                    self.tracer.log_tool_call(
                        self.trace_id, parent=op_span, phase="Op",
                        tool_name=tc.name, tool_args=tc.arguments,
                        tool_result=str(res), duration_ms=(time.time() - t0) * 1000
                    )
                    await self._safe_callback(step_callback, "tool_result", {"name": tc.name, "result": res})
                    
                    self.metrics.tools_used.append(tc.name)
                    
                    self.op_messages.append(Message(role=MessageRole.TOOL, content=res, tool_call_id=tc.id, name=tc.name))
                continue
                
            # 没有工具调用，Op 结束任务并给出最终结果
            if not response.content or not response.content.strip():
                logger.warning(f"Op-Process returned empty content at iter {i}. Treating as incomplete result.")
                # 不循环等待，直接当作不完整结果返回给 G 判断
                response = type(response)(
                    content="```op_result\nSTATUS: PARTIAL\nSUMMARY:\nOp 未能生成执行报告。\nOPEN_QUESTIONS:\n- Op 执行可能遇到问题，请 G 判断是否需要重新派发。\n```",
                    tool_calls=response.tool_calls,
                    finish_reason=response.finish_reason,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    total_tokens=response.total_tokens
                )

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
            self.tracer.end_span(op_span, status=op_result.get("status", "UNKNOWN"))
            # Session-scoped 注销：清理本次动态加载的工具
            for t_name in session_dynamic_tools:
                self.tools.unregister(t_name)
            if session_dynamic_tools:
                logger.info(f"Op结束: 注销 {len(session_dynamic_tools)} 个动态工具: {session_dynamic_tools}")
            return op_result
            
        logger.warning("Op-Process reached max iterations.")
        self.execution_messages.extend(self.op_messages)
        # 提取 Op 已完成的工具调用摘要，让 G 知道 Op 做到了哪里
        partial_work = []
        for m in self.op_messages:
            if m.role == MessageRole.TOOL:
                preview = str(m.content)[:150].replace("\n", " ")
                partial_work.append(f"- [{m.name}]: {preview}")
        partial_summary = "\n".join(partial_work[-6:]) if partial_work else "无已完成步骤"
        timeout_result = {
            "status": "PARTIAL",
            "summary": f"Op 达到迭代上限被截断，但已执行 {len(partial_work)} 步工具调用。\n已完成步骤：\n{partial_summary}",
            "changes_made": [],
            "artifacts": [],
            "open_questions": [],
            "raw_output": f"达到最大迭代次数限制，强制终止。已执行 {len(partial_work)} 步。"
        }
        self.execution_reports.append(timeout_result)
        self._merge_signature_from_texts(timeout_result.get("summary", ""), "\n".join(timeout_result.get("open_questions", []) or []))
        self.tracer.end_span(op_span, status="timeout")
        # Session-scoped 注销：清理本次动态加载的工具
        for t_name in session_dynamic_tools:
            self.tools.unregister(t_name)
        if session_dynamic_tools:
            logger.info(f"Op超时: 注销 {len(session_dynamic_tools)} 个动态工具: {session_dynamic_tools}")
        return timeout_result

    async def _run_c_phase(self, step_callback: Any, mode: str = "FULL"):
        """运行 C-Process 反思循环，基于 Op 的执行轨迹。mode: FULL/LIGHT"""
        max_iter = self.C_PHASE_MAX_ITER.get(mode, 30)
        logger.info(f">>> Entering Phase 3: C-Process (Reflector) mode={mode}, max_iter={max_iter}")
        
        report_summary = self._build_execution_report_summary()
        # Knowledge Arena 反馈闭环: 根据任务结果调整被使用节点的置信度
        # 去重：防止多次 dispatch 同一节点导致 N 倍 boost/decay
        unique_active_nodes = list(dict.fromkeys(self.execution_active_nodes))
        if unique_active_nodes:
            # 激活 usage_count：为 GC 防护提供信号（usage_count > 0 的节点免于 purge）
            self.vault.increment_usage(unique_active_nodes)
            has_success = any(
                (r.get("status", "") or "").upper() in ["SUCCESS", "PARTIAL"]
                for r in self.execution_reports
            )
            has_failure = any(
                (r.get("status", "") or "").upper() in ["FAILED"]
                for r in self.execution_reports
            )
            if has_success and not has_failure:
                self.vault.record_usage_outcome(unique_active_nodes, success=True)
                logger.info(f"Knowledge Arena: +boost for {len(unique_active_nodes)} nodes (task SUCCESS)")
            elif has_failure:
                self.vault.record_usage_outcome(unique_active_nodes, success=False)
                logger.info(f"Knowledge Arena: -decay for {len(unique_active_nodes)} nodes (task FAILED)")

        # 3. 整理执行总结
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
        
        reflection_system_prompt = f"""你是 Genesis 反思进程 (C-Process)。审查 Op 的执行轨迹，提炼高价值元信息。

{signature_block}
{report_summary}
{execution_summary}

[原则]
不写日记，不记流水账。先判断这轮有没有长期价值——如果 Op 只是读了个文件或搜了一下，没有状态修改，直接回复 NO_ACTION。

[沉淀优先级] ASSET > LESSON > CONTEXT > EPISODE > GRAPH(ENTITY/EVENT/ACTION+边)
选最小、最精准的表示。同一事实不要同时写多种类型。

[LESSON 核心]
不要总结步骤流水。问自己：哪个错误假设导致了这条轨迹？哪个证据推翻了它？下次遇到什么信号该先检查什么？
不可泛化的一次性过程不写 LESSON。LESSON 必须填 resolves 字段（解决什么问题），尽量填 prerequisites。

[metadata_signature]
为每个节点写精准的签名——只填该节点实际涉及的值，不要堆砌。
核心字段：os_family, runtime, language, framework, task_kind, error_kind, target_kind, environment_scope。
也可以发明自定义维度。validation_status 只有命令输出/日志明确证实时才填 validated，否则用 unverified。
"""
        c_messages = [Message(role=MessageRole.SYSTEM, content=reflection_system_prompt)]
        
        c_tool_names = ["search_knowledge_nodes", "record_context_node", "record_lesson_node", "create_meta_node", "create_graph_node", "create_node_edge", "delete_node", "record_tool_node"]
        c_tools = [self.tools.get(n) for n in c_tool_names if self.tools.get(n)]
        c_schema = [t.to_schema() for t in c_tools]
        
        for _ in range(max_iter):
            try:
                response = await self.provider.chat(
                    messages=[m.to_dict() for m in c_messages],
                    tools=c_schema,
                    stream=False
                )
                self._update_metrics(response, phase="C")
                
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
                logger.error(f"Reflection step failed (continuing): {e}")
                _c_consecutive_errors = getattr(self, '_c_consecutive_errors', 0) + 1
                if _c_consecutive_errors >= 3:
                    logger.warning("C-Phase: 3 consecutive errors, stopping.")
                    break
                self._c_consecutive_errors = _c_consecutive_errors
                continue
        
        logger.info(f"C-Process finished. c_tokens={self.metrics.c_tokens}, total={self.metrics.total_tokens}")
        await self._safe_callback(step_callback, "c_phase_done", {"mode": mode, "c_tokens": self.metrics.c_tokens})

    # ─── 蒸发机制 ─────────────────────────────────────────────────────
    
    def _evaporate_op_messages(self):
        """
        蒸发 Op-Process 中旧的 TOOL 消息。
        
        原理：
        - LLM 的 ASSISTANT 回复已隐式总结了上一轮 TOOL 输出的关键信息
        - 因此在 LLM 处理完 TOOL 结果后，原文可以安全地"蒸发"为存根
        - 这不是截断：信息已被 LLM 消化，存根只是标记"发生过什么"
        
        策略：
        - 保留最近 2 轮的完整 TOOL 消息（LLM 可能还在引用它们）
        - 更早的 TOOL 消息压缩为单行存根
        """
        if len(self.op_messages) <= 5:
            return  # 消息太少，无需蒸发
        
        # 找出所有 TOOL 消息的索引
        tool_indices = [i for i, m in enumerate(self.op_messages) if m.role == MessageRole.TOOL]
        
        if len(tool_indices) <= 2:
            return  # TOOL 消息太少，无需蒸发
        
        # 保留最后 2 条 TOOL 消息的完整内容
        keep_indices = set(tool_indices[-2:])
        
        for idx in tool_indices:
            if idx in keep_indices:
                continue
            
            msg = self.op_messages[idx]
            content_len = len(str(msg.content or ""))
            
            # 只有足够长的消息才值得蒸发
            if content_len < 500:
                continue
            
            # 创建存根：保留工具名和长度信息
            stub_content = f"[{msg.name}: 已处理, {content_len}字符]"
            
            # 原地替换为存根
            self.op_messages[idx] = Message(
                role=MessageRole.TOOL,
                content=stub_content,
                tool_call_id=msg.tool_call_id,
                name=msg.name
            )
        
        # 记录蒸发效果
        total_chars = sum(len(str(m.content or "")) for m in self.op_messages)
        logger.debug(f"Op蒸发: {len(tool_indices) - 2} 条TOOL消息已压缩, 剩余上下文约 {total_chars} 字符")

    def _evaporate_g_messages(self):
        """
        蒸发 G-Process 中旧的 TOOL 消息（搜索结果、Op 返回）。
        
        与 Op 蒸发对称：G 的 ASSISTANT 回复已隐式消化了旧 TOOL 输出，
        因此旧的大体积 TOOL 消息可以安全压缩为存根。
        """
        if len(self.g_messages) <= 6:
            return
        
        # 找出所有 TOOL 消息的索引（跳过 index 0=SYSTEM, 1=USER）
        tool_indices = [i for i, m in enumerate(self.g_messages) if m.role == MessageRole.TOOL and i >= 2]
        
        if len(tool_indices) <= 2:
            return
        
        # 保留最后 2 条 TOOL 消息的完整内容
        keep_indices = set(tool_indices[-2:])
        evaporated = 0
        
        for idx in tool_indices:
            if idx in keep_indices:
                continue
            
            msg = self.g_messages[idx]
            content_len = len(str(msg.content or ""))
            
            if content_len < 500:
                continue
            
            stub_content = f"[{msg.name or 'tool'}: 已处理, {content_len}字符]"
            self.g_messages[idx] = Message(
                role=MessageRole.TOOL,
                content=stub_content,
                tool_call_id=msg.tool_call_id,
                name=msg.name
            )
            evaporated += 1
        
        if evaporated:
            total_chars = sum(len(str(m.content or "")) for m in self.g_messages)
            logger.debug(f"G蒸发: {evaporated} 条TOOL消息已压缩, 剩余上下文约 {total_chars} 字符")

    def _save_memory(self, agent_response: str):
        """保存本次对话到短期记忆"""
        try:
            if not self.user_input:
                return
            mgmt = NodeManagementTools(self.vault)
            mgmt.store_conversation(self.user_input, agent_response)
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")

    def _update_metrics(self, response: Any, phase: str = "G"):
        tokens = response.input_tokens + response.output_tokens
        self.metrics.input_tokens += response.input_tokens
        self.metrics.output_tokens += response.output_tokens
        self.metrics.total_tokens += response.total_tokens
        self.metrics.iterations += 1
        if phase == "G":
            self.metrics.g_tokens += tokens
        elif phase == "Op":
            self.metrics.op_tokens += tokens
        elif phase == "C":
            self.metrics.c_tokens += tokens

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
