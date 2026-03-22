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
from genesis.v4.manager import FactoryManager, NodeVault, NodeManagementTools, TRUST_TIER_RANK, TOOL_EXEC_MIN_TIER, PERSONA_ACTIVATION_MAP
from genesis.v4.blackboard import Blackboard

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

    OP_MAX_ITERATIONS = 12  # Op 单次派发上限：短 Op + 多次 dispatch，G 保持控制权
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
        self.blackboard: Optional[Blackboard] = None  # Multi-G 黑板
        
        # 启动时恢复 persona 学习数据（只在首次 V4Loop 实例化时加载一次）
        Blackboard.load_from_db()

    # ── Token 效率退化诊断：类级滑动窗口 ──
    _token_history: List[int] = []  # 最近 N 次请求的总 token 数
    _TOKEN_WINDOW = 10

    @classmethod
    def _record_token_usage(cls, total_tokens: int):
        """记录本次请求的 token 消耗，维护最近 _TOKEN_WINDOW 次的滑动窗口"""
        cls._token_history.append(total_tokens)
        if len(cls._token_history) > cls._TOKEN_WINDOW:
            cls._token_history = cls._token_history[-cls._TOKEN_WINDOW:]

    @classmethod
    def get_token_efficiency_stats(cls) -> Optional[Dict[str, Any]]:
        """供 heartbeat 获取 token 效率诊断数据"""
        if not cls._token_history:
            return None
        avg = sum(cls._token_history) / len(cls._token_history)
        return {
            "window_size": len(cls._token_history),
            "avg_tokens_per_request": round(avg),
            "last_tokens": cls._token_history[-1] if cls._token_history else 0,
            "max_tokens": max(cls._token_history),
            "min_tokens": min(cls._token_history),
        }

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
        self._signature_drift_events: List[Dict[str, Any]] = []  # 签名偏差检测事件
        # 每次请求重置 fusion_score 缓存，防止上次请求的分数污染当前归因
        from genesis.tools.node_tools import SearchKnowledgeNodesTool
        SearchKnowledgeNodesTool.reset_fusion_cache()
        # 签名推断只用用户实际请求，排除频道历史等上下文噪音
        _sig_input = user_input
        if "[GENESIS_USER_REQUEST_START]" in user_input:
            _sig_input = user_input.split("[GENESIS_USER_REQUEST_START]", 1)[1]
        self.inferred_signature = self.vault.infer_metadata_signature(_sig_input)
        self.blackboard = None  # 每次请求重置
        
        # === Multi-G 透镜预激活 ===
        if self._should_activate_multi_g(user_input):
            try:
                self.blackboard = await self._run_lens_phase(user_input, step_callback)
                logger.info(f"Multi-G lens phase completed: {self.blackboard.entry_count} entries, {len(self.blackboard.search_voids)} voids")
            except Exception as e:
                logger.error(f"Multi-G lens phase failed (falling back to single-G): {e}", exc_info=True)
                self.blackboard = None
        
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
        # Token budget 守卫：G+Op 消耗过多时降级 C，防止上下文溢出或注意力退化
        if c_mode == "FULL" and self.metrics.total_tokens > 0:
            TOKEN_BUDGET_THRESHOLD = 80000  # ~60% of 128k context
            if self.metrics.total_tokens > TOKEN_BUDGET_THRESHOLD:
                logger.warning(
                    f"Token budget guard: G+Op consumed {self.metrics.total_tokens} tokens "
                    f"(>{TOKEN_BUDGET_THRESHOLD}), downgrading C-Phase FULL→LIGHT"
                )
                c_mode = "LIGHT"
        if c_mode != "SKIP":
            if self.c_phase_blocking:
                await self._run_c_phase_safe(step_callback, c_mode)
                logger.info(f"C-Process completed (blocking mode={c_mode}, G={self.metrics.g_tokens}t, Op={self.metrics.op_tokens}t).")
            else:
                asyncio.create_task(self._run_c_phase_safe(step_callback, c_mode))
                logger.info(f"C-Process launched in background (mode={c_mode}, G={self.metrics.g_tokens}t, Op={self.metrics.op_tokens}t).")
        elif len(self.execution_messages) > 0:
            logger.info(f"Skipping C-Process: mode=SKIP (G={self.metrics.g_tokens}t, Op={self.metrics.op_tokens}t).")
        
        # Multi-G 空洞自动入库（放在 C 之后，避免改变 digest 导致 G 缓存失效）
        if self.blackboard:
            self._auto_record_voids(self.blackboard)
        
        # 搜索仪表盘 + 签名偏差数据写入 heartbeat，供外部监控和自诊断
        from genesis.tools.node_tools import SearchKnowledgeNodesTool
        search_stats = SearchKnowledgeNodesTool.get_search_stats()
        # 签名偏差摘要：统计盲区/误报/冲突的出现频次
        sig_drift_summary = None
        if self._signature_drift_events:
            blind_all, fp_all, conflict_all = [], [], []
            for ev in self._signature_drift_events:
                blind_all.extend(ev.get("blind_spots", []))
                fp_all.extend(ev.get("false_positives", []))
                conflict_all.extend(ev.get("value_conflicts", []))
            sig_drift_summary = {
                "events": len(self._signature_drift_events),
                "top_blind_spots": sorted(set(blind_all), key=blind_all.count, reverse=True)[:5],
                "top_false_positives": sorted(set(fp_all), key=fp_all.count, reverse=True)[:5],
                "top_value_conflicts": sorted(set(conflict_all), key=conflict_all.count, reverse=True)[:5],
            }
            logger.info(f"[签名偏差摘要] {sig_drift_summary}")
        persona_stats = Blackboard.get_persona_stats() if Blackboard._persona_stats else None
        # Provider 质量漂移
        from genesis.core.provider import NativeHTTPProvider
        provider_stats = NativeHTTPProvider.get_provider_stats()
        # Token 效率退化：记录本次并获取滑动窗口
        self._record_token_usage(self.metrics.total_tokens or 0)
        token_efficiency = self.get_token_efficiency_stats()
        # 知识库熵增：低 confidence 节点占比
        kb_entropy = self.vault.get_kb_entropy()
        # 缓存命中率
        cache_stats = None
        if self.metrics.input_tokens > 0:
            cache_stats = {
                "input_tokens": self.metrics.input_tokens,
                "cache_hit_tokens": self.metrics.prompt_cache_hit_tokens,
                "cache_hit_rate": round(self.metrics.prompt_cache_hit_tokens / self.metrics.input_tokens, 3),
            }
        self.vault.heartbeat("main_loop", "idle",
            f"done G={self.metrics.g_tokens}t Op={self.metrics.op_tokens}t cache={cache_stats['cache_hit_rate']*100:.1f}%" if cache_stats else f"done G={self.metrics.g_tokens}t Op={self.metrics.op_tokens}t",
            extra={
                "search_stats": search_stats,
                "signature_drift": sig_drift_summary,
                "persona_stats": persona_stats,
                "provider_stats": provider_stats,
                "token_efficiency": token_efficiency,
                "kb_entropy": kb_entropy,
                "cache_stats": cache_stats,
            }
        )
        
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
        
        # === Multi-G 黑板注入：如果透镜阶段已完成，将结果注入 G 的上下文 ===
        if self.blackboard and self.blackboard.entry_count > 0:
            collapse_results = self.blackboard.collapse(self.vault)
            board_text = self.blackboard.render_for_g(collapse_results=collapse_results)
            collapse_summary_lines = ["[坍缩排名]"]
            for rank, item in enumerate(collapse_results[:5], 1):
                e = item["entry"]
                collapse_summary_lines.append(f"  {rank}. [{e.persona}] score={item['score']:.3f} — {e.framework}")
            collapse_text = "\n".join(collapse_summary_lines)
            
            # 提取 top entry 的 verification_action，如果具体则建议 G 优先执行
            verification_hint = ""
            if collapse_results:
                top_entry = collapse_results[0]["entry"]
                if hasattr(top_entry, "verification_action") and top_entry.verification_action:
                    va = top_entry.verification_action.strip()
                    if len(va) > 10:  # 足够具体的验证动作
                        verification_hint = f"\n\n[建议优先验证]\n透镜 {top_entry.persona} 建议的最小验证动作：{va}\n如果此动作可行，建议在你的第一次 dispatch 中优先执行它，以快速确认或否定假设。"
            
            self.g_messages.append(Message(
                role=MessageRole.SYSTEM,
                content=f"[Multi-G 透镜侦察完毕]\n你的透镜子程序已从不同认知视角检索了知识库，以下是汇总。你可以参考但不必盲从——你是主脑，保留最终判断权。\n\n{board_text}\n\n{collapse_text}{verification_hint}"
            ))
            logger.info(f"Multi-G blackboard injected into G context: {self.blackboard.entry_count} entries, top={collapse_results[0]['entry'].persona if collapse_results else 'N/A'}")
        
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
        c_explicit_signature = prepared.get("metadata_signature")
        # 始终从节点内容推断一份签名（用于偏差对比）
        text_parts: List[str] = []
        for key in ["title", "state_description", "trigger_verb", "trigger_noun", "trigger_context", "because_reason", "resolves", "content", "tags"]:
            value = prepared.get(key)
            if value:
                text_parts.append(str(value))
        action_steps = prepared.get("action_steps") or []
        if isinstance(action_steps, list):
            text_parts.extend([str(item) for item in action_steps if item])
        inferred_signature = self.vault.infer_metadata_signature("\n".join(text_parts))

        c_signature = c_explicit_signature or inferred_signature

        if c_signature:
            prepared["metadata_signature"] = c_signature

        # ── 签名推断偏差检测（反馈环 Ⅳ）──
        # 当 C 显式写入签名时，对比 C 的签名与推断引擎的签名，记录维度偏差
        if c_explicit_signature and inferred_signature:
            c_dims = set(c_explicit_signature.keys())
            inferred_dims = set(inferred_signature.keys())
            # C 写了但推断引擎没推出来的维度 = 推断引擎的盲区
            blind_spots = c_dims - inferred_dims
            # 推断引擎推出来但 C 没写的维度 = C 认为不重要或推断误报
            false_positives = inferred_dims - c_dims
            # 同维度值不同 = 判断分歧
            value_conflicts = {
                k for k in c_dims & inferred_dims
                if str(c_explicit_signature[k]).lower() != str(inferred_signature[k]).lower()
            }
            # ── 自动学习：将 C 的盲区维度作为新 marker 持久化 ──
            content_text = "\n".join(text_parts).lower()
            for dim_key in blind_spots:
                c_val = c_explicit_signature.get(dim_key)
                if not c_val:
                    continue
                vals = c_val if isinstance(c_val, list) else [c_val]
                for v in vals:
                    v_str = str(v).strip().lower()
                    # 只学习在节点内容中确实出现的值（确认是合理的 marker）
                    if v_str and v_str in content_text:
                        self.vault.learn_signature_marker(dim_key, v_str, source="c_phase")
            if blind_spots or false_positives or value_conflicts:
                self._signature_drift_events.append({
                    "tool": tool_name,
                    "blind_spots": list(blind_spots),
                    "false_positives": list(false_positives),
                    "value_conflicts": list(value_conflicts),
                })
                logger.debug(
                    f"[签名偏差] tool={tool_name} blind={blind_spots} fp={false_positives} conflict={value_conflicts}"
                )

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

        # 上游信号补充（避免 C-Phase 信号盲区 FRAGILITY_acc4）
        # Multi-G 搜索空洞多 = 知识库有明显缺口，值得 C 记录 LESSON/VOID
        if self.blackboard and len(self.blackboard.search_voids) >= 2:
            high_value = True
        # 多节点 dispatch = 复杂任务，反思价值更高
        if len(self.execution_active_nodes) >= 3:
            high_value = True
        # 签名维度多 = 专业领域，C 的精准签名写入更关键
        if len(self.inferred_signature) >= 4:
            high_value = True

        if not high_value:
            return "SKIP"

        # LIGHT vs FULL 梯度：信号量少的 high_value 任务用 LIGHT，避免白烧 30 轮
        # FULL 条件：多报告 / 失败 / 大量变更 / 知识空洞 / 复杂签名
        full_signals = 0
        if len(self.execution_reports) > 1:
            full_signals += 1
        if any((r.get("status", "UNKNOWN") or "UNKNOWN").upper() in ["FAILED", "PARTIAL", "UNKNOWN"] for r in self.execution_reports):
            full_signals += 1
        if sum(len(r.get("changes_made", []) or []) for r in self.execution_reports) >= 3:
            full_signals += 1
        if self.blackboard and len(self.blackboard.search_voids) >= 2:
            full_signals += 1
        if len(self.execution_active_nodes) >= 3:
            full_signals += 1
        if any(r.get("open_questions") for r in self.execution_reports):
            full_signals += 1

        if full_signals >= 2:
            return "FULL"
        return "LIGHT"

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
            # ⚠️ Op 内部不蒸发：Op 的 ReAct 循环需要完整记忆自己做过什么。
            # 蒸发只发生在 G（跨 dispatch）和 Lens（跨搜索轮次）中。
            
            # ── 优雅终止：倒数第 2 轮提醒 Op 收尾 ──
            if i == self.OP_MAX_ITERATIONS - 2:
                self.op_messages.append(Message(
                    role=MessageRole.SYSTEM,
                    content=(
                        f"[系统提醒] 你还剩 2 轮迭代就会被强制终止。"
                        f"请立即停止新的工具调用，输出 op_result 执行报告总结你已完成的工作和未完成的部分。"
                        f"G 会根据你的报告决定是否需要继续派发。"
                    )
                ))
            
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
        partial_summary = "\n".join(partial_work[-8:]) if partial_work else "无已完成步骤"
        # 提取 Op 最后一条 assistant 消息作为 findings（Op 可能已有阶段性结论）
        last_assistant = ""
        for m in reversed(self.op_messages):
            if m.role == MessageRole.ASSISTANT and m.content and m.content.strip():
                last_assistant = m.content.strip()[:800]
                break
        timeout_result = {
            "status": "PARTIAL",
            "summary": f"Op 达到迭代上限（{self.OP_MAX_ITERATIONS}轮），已执行 {len(partial_work)} 步。",
            "findings": last_assistant or "Op 未输出阶段性结论",
            "changes_made": [],
            "artifacts": [],
            "open_questions": [f"Op 在 {len(partial_work)} 步后被截断，G 应根据已完成步骤判断是否需要继续派发。"],
            "raw_output": f"已完成步骤：\n{partial_summary}"
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
        
        # 跨进程向量同步：拉取 Daemon/Scavenger 在 G/Op 期间新增的节点向量，
        # 确保 C 的 search_knowledge_nodes 能看到最新节点（LESSON 去重依赖此）
        self.vault.sync_vector_matrix_incremental()
        
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
            # 节点级信用归因：用 fusion_score 加权 boost/decay
            from genesis.tools.node_tools import SearchKnowledgeNodesTool
            fusion_weights = SearchKnowledgeNodesTool.get_fusion_scores(unique_active_nodes)
            if has_success and not has_failure:
                self.vault.record_usage_outcome(unique_active_nodes, success=True, weights=fusion_weights)
                logger.info(f"Knowledge Arena: +boost for {len(unique_active_nodes)} nodes (task SUCCESS, weighted)")
            elif has_failure:
                self.vault.record_usage_outcome(unique_active_nodes, success=False, weights=fusion_weights)
                logger.info(f"Knowledge Arena: -decay for {len(unique_active_nodes)} nodes (task FAILED, weighted)")

        # Persona 在线学习：将任务结果反馈给 Blackboard 的 persona 表现统计
        # 注意：独立于 unique_active_nodes，即使 Op 没引用知识节点也要记录 persona 表现
        if self.blackboard and self.blackboard.entries:
            has_success_p = any(
                (r.get("status", "") or "").upper() in ["SUCCESS", "PARTIAL"]
                for r in self.execution_reports
            )
            has_failure_p = any(
                (r.get("status", "") or "").upper() in ["FAILED"]
                for r in self.execution_reports
            )
            contributing_personas = list({e.persona for e in self.blackboard.entries})
            task_success = has_success_p and not has_failure_p
            raw_atk = self.inferred_signature.get("task_kind") or ""
            arena_task_kind = (raw_atk[0] if isinstance(raw_atk, list) and raw_atk else str(raw_atk)).lower()
            Blackboard.record_persona_outcome(contributing_personas, success=task_success, task_kind=arena_task_kind)
            logger.info(f"Persona Arena: {'WIN' if task_success else 'LOSS'} for {contributing_personas} (task_kind={arena_task_kind})")

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
        
        # Multi-G 信息空洞（仅供 C 参考，不需要 C 处理——已由基础设施自动入库）
        void_block = ""
        if self.blackboard:
            void_count = len(self.blackboard.search_voids)
            if void_count > 0:
                void_block = f"\n[Multi-G 信息空洞] 本次透镜阶段有 {void_count} 个搜索未命中，已自动记录为 VOID 节点供后台拾荒。你无需处理它们。\n"

        # ⚠️ 前缀缓存优化：稳定指令放前面，每次请求不同的变量内容放后面
        reflection_system_prompt = f"""你是 Genesis 反思进程 (C-Process)。审查 Op 的执行轨迹，提炼高价值元信息。

[原则]
不写日记，不记流水账。先判断这轮有没有长期价值——如果 Op 只是读了个文件或搜了一下，没有状态修改，直接回复 NO_ACTION。

[沉淀优先级] ASSET > LESSON > CONTEXT > EPISODE > GRAPH(ENTITY/EVENT/ACTION+边)
选最小、最精准的表示。同一事实不要同时写多种类型。

[LESSON 核心]
不要总结步骤流水。问自己：哪个错误假设导致了这条轨迹？哪个证据推翻了它？下次遇到什么信号该先检查什么？
不可泛化的一次性过程不写 LESSON。LESSON 必须填 resolves 字段（解决什么问题），尽量填 prerequisites。

[metadata_signature]
为每个节点写精准的签名——只填该节点实际涉及的值。
核心字段：os_family, runtime, language, framework, task_kind, error_kind, target_kind, environment_scope。
反堆砌规则：每个字段最多 2 个值。task_kind 只填最核心的 1 个（debug/configure/deploy 等），不要把所有沾边的都塞进去。
自定义维度鼓励：知识分类型（如 severity, scope, maturity, pattern_type, failure_mode），这些能帮助未来搜索定位。
自定义维度禁止：运营流水型（timestamp, port, version, daily_count, followup_needed 等），这些对搜索无价值。
validation_status 只有命令输出/日志明确证实时才填 validated，否则用 unverified。

{signature_block}
{report_summary}
{execution_summary}
{void_block}
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

    # ─── Multi-G 透镜编排 ──────────────────────────────────────────────

    def _auto_record_voids(self, blackboard: Blackboard):
        """
        基础设施层自动记录搜索空洞到 NodeVault。
        
        不依赖 C-Process 判断——所有透镜搜索未命中 + 假设型条目的建议搜索方向
        都直接写成轻量级 VOID 节点，供 Scavenger/Fermentor 定向拾荒。
        
        去重逻辑：对 query 做向量相似度检查，相似度 > 0.80 的 VOID 合并。
        """
        all_voids = list(blackboard.search_voids)
        for entry in blackboard.entries:
            if hasattr(entry, 'suggested_search_directions'):
                for d in (entry.suggested_search_directions or []):
                    all_voids.append({
                        "persona": entry.persona,
                        "query": d,
                        "source": "hypothesis_suggestion"
                    })
        
        if not all_voids:
            return
        
        # 去重：按 query 文本粗去重
        seen_queries = set()
        unique_voids = []
        for v in all_voids:
            q = v.get("query", "").strip()
            if not q or len(q) < 5:
                continue
            q_key = q[:80].lower()
            if q_key not in seen_queries:
                seen_queries.add(q_key)
                unique_voids.append(v)
        
        if not unique_voids:
            return
        
        # 向量去重：检查是否已有相似的 VOID 节点
        recorded = 0
        for v in unique_voids[:10]:  # 每次最多记录 10 个，避免膨胀
            query = v["query"]
            persona = v.get("persona", "unknown")
            
            # 检查是否已有相似的 VOID
            if self.vault.vector_engine.is_ready:
                existing = self.vault.vector_engine.search(query, top_k=3, threshold=0.80)
                # 检查命中的是否为 VOID 节点
                if existing:
                    existing_ids = [r[0] for r in existing]
                    briefs = self.vault.get_node_briefs(existing_ids)
                    has_similar_void = any(
                        "VOID" in (b.get("tags") or "")
                        for b in briefs.values()
                    )
                    if has_similar_void:
                        continue  # 已有相似 VOID，跳过
            
            # 生成简洁的 node_id
            import hashlib
            q_hash = hashlib.md5(query.encode()).hexdigest()[:8].upper()
            node_id = f"VOID_{q_hash}"
            
            try:
                self.vault.create_node(
                    node_id=node_id,
                    ntype="CONTEXT",
                    title=f"[信息空洞] {query[:60]}",
                    human_translation=query,
                    tags="VOID",
                    full_content=f"Multi-G 透镜 {persona} 搜索未命中。\n查询: {query}\n来源: {v.get('source', 'search_miss')}\n任务签名: {json.dumps(self.inferred_signature, ensure_ascii=False)}",
                    source="multi_g_void",
                    metadata_signature=self.inferred_signature,
                    confidence_score=0.3,
                    trust_tier="SCAVENGED"
                )
                recorded += 1
            except Exception as e:
                logger.debug(f"Auto-record void failed for '{query[:40]}': {e}")
        
        if recorded:
            logger.info(f"Multi-G: auto-recorded {recorded}/{len(unique_voids)} voids to NodeVault")

    # 需要 Multi-G 的复杂 task_kind 集合
    MULTI_G_TASK_KINDS = frozenset(["debug", "refactor", "build", "optimize", "design", "test", "deploy", "configure"])
    LENS_MAX_ITERATIONS = 2   # 每个透镜子程序最多 2 轮搜索（+ 1 次强制输出）
    LENS_TIMEOUT_SECS = 60    # 单个透镜超时

    def _should_activate_multi_g(self, user_input: str) -> bool:
        """判断是否应启用 Multi-G 透镜阶段
        
        策略：默认开启，仅在以下情况跳过：
        - 用户 /quick 强制跳过
        - 输入太短（闲聊/打招呼，< 10 个有效字符）
        """
        # 提取实际用户请求（跳过频道历史噪音）—— 必须先做，否则 /deep /quick 被频道历史淹没
        actual_input = user_input
        if "[GENESIS_USER_REQUEST_START]" in user_input:
            actual_input = user_input.split("[GENESIS_USER_REQUEST_START]", 1)[1]
        actual_input = actual_input.strip()
        
        # 用户强制开关（在提取后的实际请求中检查）
        if "/quick" in actual_input[:20]:
            logger.info("Multi-G skipped by /quick prefix")
            return False
        if "/deep" in actual_input[:20]:
            logger.info("Multi-G activated by /deep prefix (force 7 lenses)")
            return True
        
        # 太短的输入不值得激活透镜
        if len(actual_input) < 10:
            logger.info(f"Multi-G skipped: input too short ({len(actual_input)} chars)")
            return False
        
        logger.info(f"Multi-G activated (default-on, input={len(actual_input)} chars)")
        return True

    # 从 PERSONA_ACTIVATION_MAP 的 3 个基础人格扩展到 5/7 时的补充池
    # 按认知维度互补排列，确保新增人格带来差异化视角
    PERSONA_EXTENSION_POOL = ["ISTP", "ENTJ", "ISFJ", "ENFP", "ESTJ", "INFJ", "ISTJ", "INTP", "INTJ"]

    # 全 16 型 MBTI 池（供动态淘汰/递补选择）
    ALL_PERSONAS = [
        "ISTJ", "ISFJ", "INFJ", "INTJ", "ISTP", "ISFP", "INFP", "INTP",
        "ESTP", "ESFP", "ENFP", "ENTP", "ESTJ", "ESFJ", "ENFJ", "ENTJ",
    ]

    def _select_personas(self, target_count: int = 3) -> List[str]:
        """根据签名映射选择激活的人格透镜，支持自适应数量 + 动态淘汰/递补"""
        raw_tk = self.inferred_signature.get("task_kind") or ""
        task_kind = (raw_tk[0] if isinstance(raw_tk, list) and raw_tk else str(raw_tk)).lower()
        base = list(PERSONA_ACTIVATION_MAP.get(task_kind, PERSONA_ACTIVATION_MAP["_default"]))
        # 动态淘汰/递补：基于 task_kind 历史胜率替换表现差的 persona
        base = Blackboard.suggest_persona_swap(base, task_kind, self.ALL_PERSONAS)
        if target_count <= len(base):
            return base[:target_count]
        # 从扩展池中补充，跳过已在 base 中的人格
        for p in self.PERSONA_EXTENSION_POOL:
            if len(base) >= target_count:
                break
            if p not in base:
                base.append(p)
        return base

    async def _probe_knowledge_density(self, user_input: str) -> int:
        """G 的'第一搜'：快速探测知识库对当前任务的覆盖密度，返回命中节点数"""
        try:
            # 清理前缀
            text = user_input
            for prefix in ["/deep ", "/quick "]:
                if text.startswith(prefix):
                    text = text[len(prefix):]
            # 提取关键词（中文+英文 token，取前 5 个有意义的）
            tokens = re.findall(r'[\w\u4e00-\u9fff]{2,}', text)
            keywords = tokens[:5] if tokens else []
            if not keywords:
                return 0
            query_str = " ".join(keywords)
            # 向量搜索
            hits = 0
            if self.vault.vector_engine.is_ready:
                results = self.vault.vector_engine.search(query_str, top_k=10, threshold=0.55)
                hits = len(results)
            logger.info(f"Multi-G probe: query='{query_str}' → {hits} vector hits")
            return hits
        except Exception as e:
            logger.warning(f"Multi-G probe failed: {e}")
            return 0

    async def _build_lens_task_brief(self, clean_input: str, knowledge_digest: str) -> str:
        """G 为透镜布置作业：解读用户意图，生成结构化搜索任务简报。
        
        避免透镜对用户原话做词级同义词发散（"不完整"→搜"不完整,未完成,部分完成..."）。
        取而代之，先理解用户到底在问什么，再给出具体的搜索方向。
        """
        digest_hint = ""
        if knowledge_digest:
            digest_hint = f"\n知识库概况（前500字）：\n{knowledge_digest[:500]}\n"
        
        prompt = f"""你是任务解读器。用一句话总结用户的底层意图，然后给出 3-5 个具体搜索方向。
搜索方向必须是【知识库中可能存在的主题/实体】，不是用户原话的同义词改写。

用户原话：{clean_input}
{digest_hint}
严格按以下格式输出（不要多余文字）：
意图：（用户真正想知道/想做什么）
搜索方向：
- （具体主题词或短语1）
- （具体主题词或短语2）
- （具体主题词或短语3）"""
        
        try:
            resp = await asyncio.wait_for(
                self.provider.chat(
                    messages=[{"role": "user", "content": prompt}],
                    stream=False
                ),
                timeout=15
            )
            brief = (resp.content or "").strip()
            if brief and "意图" in brief:
                logger.info(f"Lens task brief: {brief[:120]}...")
                return brief
        except Exception as e:
            logger.warning(f"Task brief generation failed: {e}")
        
        # 兜底：直接返回原文
        return f"意图：{clean_input}\n搜索方向：\n- （自行判断最相关的知识领域）"

    async def _run_lens_phase(self, user_input: str, step_callback: Any) -> Blackboard:
        """
        运行 Multi-G 透镜阶段：
        1. 探针搜索（G 的"第一搜"）→ 根据命中密度自适应选择透镜数量
        2. 并行 spawn 多个透镜子程序，各自搜索 NodeVault
        3. 将结果写入共享黑板
        
        返回填充完毕的 Blackboard。
        """
        blackboard = Blackboard()
        
        # ── 探针搜索：用 G 的视角做一次快速搜索，测量知识密度 ──
        # 提取实际用户请求后再检查 /deep（Discord 会在前面加频道历史）
        _actual = user_input
        if "[GENESIS_USER_REQUEST_START]" in user_input:
            _actual = user_input.split("[GENESIS_USER_REQUEST_START]", 1)[1]
        force_deep = "/deep" in _actual.strip()[:20]
        probe_hits = 0
        if not force_deep:
            probe_hits = await self._probe_knowledge_density(user_input)
            if probe_hits <= 2:
                target_count = 3   # 稀疏：保守
            elif probe_hits <= 6:
                target_count = 5   # 中等
            else:
                target_count = 7   # 密集：全力
            logger.info(f"Multi-G probe: {probe_hits} hits → {target_count} lenses")
        else:
            target_count = 7  # /deep 强制满配
            logger.info(f"Multi-G /deep: forcing {target_count} lenses")
        
        personas = self._select_personas(target_count)
        
        logger.info(f">>> Multi-G Lens Phase: spawning {len(personas)} lenses: {personas}")
        
        # 预获取共享的 digest 和签名（避免每个透镜重复计算）
        knowledge_digest = self.vault.get_digest()
        signature_text = self.vault.render_metadata_signature(self.inferred_signature)
        
        # 去掉频道历史和 /deep /quick 前缀后的干净任务文本
        clean_input = _actual.strip()
        for prefix in ["/deep ", "/quick "]:
            if clean_input.startswith(prefix):
                clean_input = clean_input[len(prefix):]
        clean_input = clean_input.strip()
        
        # ── G 布置作业：解读用户意图，生成结构化搜索任务简报 ──
        task_brief = await self._build_lens_task_brief(clean_input, knowledge_digest)
        
        await self._safe_callback(step_callback, "lens_start", {
            "personas": personas, "probe_hits": probe_hits,
            "task_brief": task_brief
        })
        
        # 并行运行所有透镜
        tasks = [
            self._run_single_lens(
                persona=p,
                task_context=task_brief,
                blackboard=blackboard,
                knowledge_digest=knowledge_digest,
                signature_text=signature_text,
                step_callback=step_callback
            )
            for p in personas
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for persona, result in zip(personas, results):
            if isinstance(result, Exception):
                logger.error(f"Lens-{persona} failed: {result}")
        
        await self._safe_callback(step_callback, "lens_done", {
            "entries": blackboard.entry_count,
            "voids": len(blackboard.search_voids)
        })
        
        return blackboard

    async def _run_single_lens(
        self,
        persona: str,
        task_context: str,
        blackboard: Blackboard,
        knowledge_digest: str,
        signature_text: str,
        step_callback: Any
    ):
        """运行单个透镜子程序：搜索 + 输出三元组 + 写黑板"""
        lens_prompt = self.factory.build_lens_prompt(
            persona=persona,
            task_context=task_context,
            blackboard_state=blackboard.render_for_g() if blackboard.entry_count > 0 else "",
            knowledge_digest=knowledge_digest,
            inferred_signature=signature_text
        )
        
        messages = [
            Message(role=MessageRole.SYSTEM, content=lens_prompt),
            Message(role=MessageRole.USER, content="请根据任务简报中的搜索方向开始搜索。")
        ]
        
        search_tool = self.tools.get("search_knowledge_nodes")
        schema = [search_tool.to_schema()] if search_tool else []
        parsed = False
        
        for iteration in range(self.LENS_MAX_ITERATIONS):
            # 透镜内蒸发：压缩非最近一轮的 TOOL 消息，防止 token 二次增长
            tool_indices = [i for i, m in enumerate(messages) if m.role == MessageRole.TOOL and i >= 2]
            if len(tool_indices) > 1:
                for idx in tool_indices[:-1]:
                    msg = messages[idx]
                    if len(str(msg.content or "")) > 300:
                        messages[idx] = Message(
                            role=MessageRole.TOOL,
                            content=f"[搜索结果已消化, {len(str(msg.content))}字符]",
                            tool_call_id=msg.tool_call_id, name=msg.name
                        )
            try:
                response = await asyncio.wait_for(
                    self.provider.chat(
                        messages=[m.to_dict() for m in messages],
                        tools=schema,
                        stream=False
                    ),
                    timeout=self.LENS_TIMEOUT_SECS
                )
            except asyncio.TimeoutError:
                logger.warning(f"Lens-{persona} timeout at iteration {iteration}")
                break
            except Exception as e:
                logger.error(f"Lens-{persona} LLM call failed: {e}")
                break
            
            self._update_metrics(response, phase="G")  # 透镜 token 计入 G 阶段
            
            messages.append(Message(
                role=MessageRole.ASSISTANT,
                content=response.content,
                tool_calls=[tc.__dict__ for tc in response.tool_calls] if response.tool_calls else None
            ))
            
            if response.tool_calls:
                # 执行搜索工具调用
                for tc in response.tool_calls:
                    if tc.name != "search_knowledge_nodes":
                        messages.append(Message(
                            role=MessageRole.TOOL,
                            content=f"Lens 只允许使用 search_knowledge_nodes",
                            tool_call_id=tc.id, name=tc.name
                        ))
                        continue
                    
                    search_args = dict(tc.arguments or {})
                    if self.inferred_signature:
                        search_args["signature"] = self.vault.merge_metadata_signatures(
                            self.inferred_signature,
                            search_args.get("signature")
                        )
                    
                    try:
                        res = await asyncio.wait_for(
                            self.tools.execute(tc.name, search_args),
                            timeout=self.TOOL_EXEC_TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        res = f"搜索超时（{self.TOOL_EXEC_TIMEOUT}秒）"
                    
                    # 检测搜索空洞
                    if res and ("未找到" in str(res) or "0 个匹配" in str(res) or "没有找到" in str(res)):
                        blackboard.record_search_void(
                            persona=persona,
                            query=str(search_args.get("keywords", "")),
                            signature=search_args.get("signature")
                        )
                    
                    messages.append(Message(
                        role=MessageRole.TOOL, content=res,
                        tool_call_id=tc.id, name=tc.name
                    ))
                    
                    await self._safe_callback(step_callback, "lens_search", {
                        "persona": persona, "tool": tc.name,
                        "query": search_args.get("keywords", [])
                    })
                
                continue  # 搜索完继续循环让 LLM 输出最终 JSON
            
            # 无 tool_calls → LLM 输出了最终文本，解析 JSON 三元组
            if response.content:
                self._parse_lens_output(persona, response.content, blackboard)
                parsed = True
            break
        
        # 兜底：如果搜索用完了迭代但从未输出 JSON，做一次无工具的强制输出
        if not parsed:
            logger.info(f"Lens-{persona}: forcing final JSON output (no-tools call)")
            messages.append(Message(
                role=MessageRole.USER,
                content="搜索阶段已结束。禁止调用任何工具。禁止输出 function_calls/DSML 标记。\n请直接输出一个纯 JSON 对象，格式二选一：\n{\"type\": \"evidence\", \"framework\": \"你的诊断框架\", \"evidence_node_ids\": [\"搜索到的节点ID\"], \"verification_action\": \"建议的验证命令\"}\n{\"type\": \"hypothesis\", \"framework\": \"你的假设\", \"reasoning_chain\": \"推理过程\", \"suggested_search_directions\": [\"建议搜索方向\"]}"
            ))
            try:
                response = await asyncio.wait_for(
                    self.provider.chat(
                        messages=[m.to_dict() for m in messages],
                        tools=[],  # 不提供任何工具，强制文本输出
                        stream=False
                    ),
                    timeout=self.LENS_TIMEOUT_SECS
                )
                self._update_metrics(response, phase="G")
                if response.content:
                    self._parse_lens_output(persona, response.content, blackboard)
                    parsed = True
            except Exception as e:
                logger.error(f"Lens-{persona} forced output failed: {e}")
        
        logger.info(f"Lens-{persona} finished (parsed={parsed})")

    def _parse_lens_output(self, persona: str, content: str, blackboard: Blackboard):
        """解析透镜 LLM 输出的 JSON 三元组，写入黑板"""
        # 尝试从文本中提取 JSON
        text = content.strip()
        
        # 剥离可能的 markdown 代码块包裹
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        
        # 防御性清洗：provider 层已做一级 DSML 剥离，此处为二级兜底
        if "DSML" in text or "tool_call" in text.lower():
            text = re.sub(r'<[｜|](?:DSML|tool_call|function_call)[｜|][^>]*>', '', text, flags=re.IGNORECASE)
            text = re.sub(r'</[｜|](?:DSML|tool_call|function_call)[｜|][^>]*>', '', text, flags=re.IGNORECASE)
            text = re.sub(r'[｜|](?:DSML|tool_call|function_call)[｜|]', '', text, flags=re.IGNORECASE)
            text = text.strip()
            if not text:
                logger.warning(f"Lens-{persona}: control markers stripped, no content remaining")
                text = ""
        
        # 多层 JSON 解析容错
        parsed = None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # 尝试找到第一个 { 和最后一个 }
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end > start:
                try:
                    parsed = json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
        
        if not parsed or not isinstance(parsed, dict):
            logger.warning(f"Lens-{persona} output not valid JSON, treating as hypothesis: {text[:100]}")
            # 回退：把整个输出当做一个假设
            blackboard.add_hypothesis(
                persona=persona,
                framework=text[:200] if text else "无法解析的输出",
                reasoning_chain=text,
                suggested_search_directions=[]
            )
            return
        
        entry_type = parsed.get("type", "hypothesis")
        
        if entry_type == "evidence":
            blackboard.add_evidence(
                persona=persona,
                framework=parsed.get("framework", "未指定框架"),
                evidence_node_ids=parsed.get("evidence_node_ids", []),
                verification_action=parsed.get("verification_action", "")
            )
        else:
            blackboard.add_hypothesis(
                persona=persona,
                framework=parsed.get("framework", "未指定框架"),
                reasoning_chain=parsed.get("reasoning_chain", ""),
                suggested_search_directions=parsed.get("suggested_search_directions", [])
            )

    # ─── 蒸发机制 ─────────────────────────────────────────────────────
    # 注意：Op 不蒸发（ReAct 循环需要完整记忆），仅 G 蒸发旧 TOOL 消息。

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
        self.metrics.prompt_cache_hit_tokens += getattr(response, 'prompt_cache_hit_tokens', 0)
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
