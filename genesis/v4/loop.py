"""
Genesis V4 核心执行引擎 (State Machine)
实现 G-Process (Thinker) -> Op-Process (Executor) -> C-Process (Reflector) 的解耦管线
"""

import json
import os
import re
import time
import asyncio
import logging
import traceback
import hashlib
from typing import List, Dict, Any, Tuple, Optional

from genesis.core.base import Message, MessageRole, LLMProvider, PerformanceMetrics, ToolCall
from genesis.core.registry import ToolRegistry
from genesis.core.tracer import Tracer
from genesis.core.models import DispatchPayload, OpResult, KnowledgeState
from genesis.v4.manager import FactoryManager, NodeVault, NodeManagementTools, TRUST_TIER_RANK, TOOL_EXEC_MIN_TIER, PERSONA_ACTIVATION_MAP
from genesis.v4.blackboard import Blackboard
from genesis.v4.diagnostics import PipelineDiagnostics
from genesis.v4.lens_phase import LensPhaseMixin
from genesis.v4.pipeline_config import PIPELINE_CONFIG

logger = logging.getLogger(__name__)

def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning(f"Invalid {name}={raw!r}; fallback to {default}")
        return default
    return max(minimum, value)

# Op 禁用工具名（G 和 C 可用，但 Op 不能调用）
OP_BLOCKED_TOOLS = frozenset([
    "record_context_node", "record_lesson_node", "create_meta_node",
    "delete_node", "search_knowledge_nodes", "create_graph_node", "create_node_edge",
    "record_tool_node"
])

# ── dispatch_to_op ──────────────────────────────────
# 现在由 genesis.tools.dispatch_tool.DispatchTool 注册在 ToolRegistry 中。
# V4Loop 在工具调度前拦截该调用并路由到 Op-Process。

class V4Loop(LensPhaseMixin):
    """
    V4 核心管线
    
    Phases:
    1. G_PHASE (大脑): 拥有历史上下文，只能搜索和派发。循环直至输出最终回复。
    2. OP_PHASE (手脚): 纯净上下文，接收 Payload，拥有执行工具，执行完退出。
    3. C_PHASE (反思): (Post-loop) 仅允许节点管理工具，沉淀知识。
    """

    OP_MAX_ITERATIONS = PIPELINE_CONFIG.op_max_iterations
    C_PHASE_MAX_ITER = PIPELINE_CONFIG.c_phase_max_iter
    TOOL_EXEC_TIMEOUT = PIPELINE_CONFIG.tool_exec_timeout

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
        self.c_messages: List[Message] = []  # C-Phase 对话轨迹，每轮覆写
        self.execution_reports: List[Dict[str, Any]] = []
        self.inferred_signature: Dict[str, Any] = {}
        self.blackboard: Optional[Blackboard] = None  # Multi-G 黑板
        self._llm_call_seq = 0
        
        # 启动时恢复 persona 学习数据（只在首次 V4Loop 实例化时加载一次）
        Blackboard.load_from_db()

    # ── Token 效率退化诊断：类级滑动窗口 ──
    _token_history: List[int] = []  # 最近 N 次请求的总 token 数
    _TOKEN_WINDOW = PIPELINE_CONFIG.token_window_size

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

    async def run(self, user_input: str, step_callback: Any = None, image_paths: Optional[List[str]] = None, loop_config: Optional[Dict[str, Any]] = None, initial_knowledge_state: Optional[Dict[str, Any]] = None) -> Tuple[str, PerformanceMetrics]:
        """执行主管线 G -> Op -> G -> C (Subroutine Mode)"""
        self.metrics.start_time = time.time()
        self.user_input = user_input
        self.image_paths = image_paths or []
        self.loop_config = dict(loop_config or {})
        self.g_messages = []
        self.op_messages = []
        self.execution_messages = []
        self.execution_reports = []
        self.execution_active_nodes: List[str] = []  # Knowledge Arena: 追踪被使用的节点
        self._op_tool_outcomes: List[Dict[str, Any]] = []  # 环境信号：Op 工具调用客观结果
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
        self._llm_call_seq = 0
        self.knowledge_state = self._normalize_knowledge_state(initial_knowledge_state)
        seed_lines = [line.strip() for line in _sig_input.splitlines() if line.strip()]
        if not self.knowledge_state.get("issue") and seed_lines:
            self.knowledge_state["issue"] = self._truncate_knowledge_state_text(seed_lines[0], 240)
        
        # === Multi-G 透镜预激活 ===
        disable_multi_g = self.loop_config.get("disable_multi_g")
        if disable_multi_g is None:
            disable_multi_g = _env_bool("GENESIS_DISABLE_MULTI_G", False)
        if disable_multi_g:
            reason = "runtime_disabled" if "disable_multi_g" in self.loop_config else "env_disabled"
            await self._safe_callback(step_callback, "lens_skipped", {"phase": "LENS_PHASE", "reason": reason})
        elif self._should_activate_multi_g(user_input):
            try:
                self.blackboard = await self._run_lens_phase(user_input, step_callback)
                logger.info(f"Multi-G lens phase completed: {self.blackboard.entry_count} entries, {len(self.blackboard.search_voids)} voids")
            except Exception as e:
                logger.error(f"Multi-G lens phase failed (falling back to single-G): {e}", exc_info=True)
                self.blackboard = None
        else:
            await self._safe_callback(step_callback, "lens_skipped", {"phase": "LENS_PHASE", "reason": "gate_closed"})
        
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
            self.metrics.success = False
            raise
            
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
                await self._run_c_phase_safe(step_callback, c_mode, g_final_response=final_response)
                logger.info(f"C-Process completed (blocking mode={c_mode}, G={self.metrics.g_tokens}t, Op={self.metrics.op_tokens}t).")
            else:
                asyncio.create_task(self._run_c_phase_safe(step_callback, c_mode, g_final_response=final_response))
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
        if token_efficiency and token_efficiency["avg_tokens_per_request"] > 0:
            PipelineDiagnostics.token_efficiency_degradation.record(
                (self.metrics.total_tokens or 0) > token_efficiency["avg_tokens_per_request"] * 2
            )
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
        diagnostics_summary = PipelineDiagnostics.summary()
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
                "diagnostics": diagnostics_summary,
            }
        )
        if diagnostics_summary["firing_count"] > 0:
            logger.warning(f"🚨 Pipeline diagnostics: {diagnostics_summary['firing_count']}/{diagnostics_summary['total_signals']} signals firing")
        
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

    async def _run_c_phase_safe(self, step_callback: Any, mode: str = "FULL", g_final_response: str = ""):
        """后台安全包装器：捕获 C-Process 异常，防止后台任务静默崩溃"""
        try:
            await self._run_c_phase(step_callback, mode, g_final_response=g_final_response)
        except Exception as e:
            logger.error(f"C-Process background task failed: {e}", exc_info=True)

    def get_phase_trace(self) -> Dict[str, Any]:
        """序列化 G/Op/C 三阶段完整对话轨迹，供经历复盘使用。
        跳过 system prompt（每轮相同且冗长）；保留 assistant 推理和 tool 结果。
        """
        def _ser(messages: List[Message], phase: str) -> List[Dict]:
            out = []
            for m in messages:
                if m.role == MessageRole.SYSTEM:
                    continue
                entry: Dict[str, Any] = {"role": str(m.role), "phase": phase}
                if m.role == MessageRole.TOOL:
                    entry["tool_name"] = m.name or "?"
                    entry["result"] = (m.content or "")[:600]
                else:
                    if m.content:
                        entry["content"] = m.content[:1500]
                    if m.tool_calls:
                        entry["tool_calls"] = [
                            {
                                "name": (tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "?")) or "?",
                                "args": str(
                                    tc.get("arguments", "") if isinstance(tc, dict) else getattr(tc, "arguments", "")
                                )[:400],
                            }
                            for tc in (m.tool_calls or [])
                        ]
                out.append(entry)
            return out

        return {
            "g": _ser(self.g_messages, "G"),
            "op": _ser(self.op_messages, "Op"),
            "c": _ser(self.c_messages, "C"),
            "c_phase_mode": getattr(self, "_last_c_phase_mode", None),
            "inferred_signature": self.inferred_signature,
            "knowledge_state": self.get_knowledge_state(),
        }

    def get_knowledge_state(self) -> Dict[str, Any]:
        return self._normalize_knowledge_state(getattr(self, "knowledge_state", {}))

    @staticmethod
    def _truncate_knowledge_state_text(text: Any, limit: int = 220) -> str:
        compact = " ".join(str(text or "").split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."

    def _normalize_knowledge_state(self, knowledge_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        raw = knowledge_state if isinstance(knowledge_state, dict) else {}
        normalized = KnowledgeState(
            issue=self._truncate_knowledge_state_text(raw.get("issue", ""), 240),
            verified_facts=[],
            failed_attempts=[],
            next_checks=[],
        ).model_dump()
        for key in ["verified_facts", "failed_attempts", "next_checks"]:
            values = raw.get(key) or []
            if isinstance(values, str):
                values = [values]
            cleaned_values = []
            for value in values:
                cleaned = self._truncate_knowledge_state_text(value, 220)
                if not cleaned or cleaned.upper() == "NONE" or cleaned in cleaned_values:
                    continue
                cleaned_values.append(cleaned)
                if len(cleaned_values) >= 5:
                    break
            normalized[key] = cleaned_values
        return normalized

    def _merge_knowledge_state(self, base_state: Optional[Dict[str, Any]], update_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        base = self._normalize_knowledge_state(base_state)
        update = self._normalize_knowledge_state(update_state)
        if update.get("issue"):
            base["issue"] = update["issue"]
        for key in ["verified_facts", "failed_attempts", "next_checks"]:
            merged = []
            for item in (update.get(key) or []) + (base.get(key) or []):
                if item and item not in merged:
                    merged.append(item)
                if len(merged) >= 5:
                    break
            base[key] = merged
        return base

    def _finalize_dispatch_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        state_update = payload.get("knowledge_state") if isinstance(payload.get("knowledge_state"), dict) else {}
        if not state_update.get("issue"):
            state_update = {**state_update, "issue": payload.get("op_intent") or self.knowledge_state.get("issue", "")}
        dispatch = DispatchPayload(
            op_intent=payload.get("op_intent", "未定义目标"),
            active_nodes=payload.get("active_nodes") or [],
            instructions=payload.get("instructions", ""),
            knowledge_state=self._merge_knowledge_state(self.knowledge_state, state_update),
        ).model_dump()
        self.knowledge_state = self._merge_knowledge_state(self.knowledge_state, dispatch.get("knowledge_state"))
        return dispatch

    def _update_knowledge_state_from_op_result(self, op_result: Dict[str, Any]):
        if not isinstance(op_result, dict):
            return
        next_checks = op_result.get("next_checks") or []
        if not next_checks and (op_result.get("status") or "").upper() in {"PARTIAL", "FAILED"}:
            next_checks = op_result.get("open_questions") or []
        issue = self.knowledge_state.get("issue", "") or op_result.get("summary", "")
        self.knowledge_state = self._merge_knowledge_state(
            self.knowledge_state,
            {
                "issue": issue,
                "verified_facts": op_result.get("verified_facts") or [],
                "failed_attempts": op_result.get("failed_attempts") or [],
                "next_checks": next_checks,
            },
        )

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
            daemon_status=self.vault.get_daemon_status_summary(),
            knowledge_state=self.factory.render_knowledge_state(self.knowledge_state)
        )
        
        # Build User Content (Multimodal if images exist)
        if hasattr(self, 'image_paths') and self.image_paths:
            import base64
            from pathlib import Path as _Path
            _ALLOWED_IMG_DIRS = ("/tmp", str(_Path.home() / "Genesis" / "Genesis" / "runtime"))
            _ALLOWED_IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".tiff"}
            user_content = [{"type": "text", "text": user_input}]
            for path in self.image_paths:
                try:
                    resolved = str(_Path(path).resolve())
                    if not any(resolved.startswith(d) for d in _ALLOWED_IMG_DIRS):
                        logger.warning(f"image_paths blocked (dir): {path}")
                        continue
                    if _Path(path).suffix.lower() not in _ALLOWED_IMG_EXTS:
                        logger.warning(f"image_paths blocked (ext): {path}")
                        continue
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
        dispatch_tool = self.tools.get("dispatch_to_op")
        g_tools = search_tools + ([dispatch_tool] if dispatch_tool else [])
        schema = [t.to_schema() for t in g_tools]
        
        _g_consecutive_errors = 0
        _G_MAX_CONSECUTIVE_ERRORS = 3
        for i in range(self.max_iterations):
            # === 跨进程向量同步：拉取 Scavenger/Fermentor 新增的节点向量 ===
            self.vault.sync_vector_matrix_incremental()
            # === G 蒸发机制：压缩旧的搜索结果和 Op 返回 ===
            self._evaporate_g_messages()
            
            self._llm_call_count += 1
            # Jailbreak 位置：在消息末尾注入钢印提醒（不污染 g_messages 本身）
            jailbreak = {"role": "system", "content": "[Reminder] 你有 Op 和知识库。能动手就动手，能查就查，别空谈。"}
            messages_to_send = [m.to_dict() for m in self.g_messages] + [jailbreak]
            llm_call_started = time.time()
            llm_call_id = await self._emit_llm_call_start(step_callback, "G_PHASE", i, stream=True)
            try:
                response = await self.provider.chat(
                    messages=messages_to_send,
                    tools=schema,
                    stream=True,
                    stream_callback=lambda ev, data: self._stream_proxy(step_callback, ev, data, phase="G_PHASE", llm_call_id=llm_call_id),
                    _trace_id=self.trace_id, _trace_phase="G", _trace_parent=self._g_span
                )
                await self._emit_llm_call_end(step_callback, "G_PHASE", llm_call_id, i, llm_call_started, stream=True, response=response)
                _g_consecutive_errors = 0  # 成功则重置计数器
            except Exception as provider_err:
                await self._emit_llm_call_end(step_callback, "G_PHASE", llm_call_id, i, llm_call_started, stream=True, error=provider_err)
                _g_consecutive_errors += 1
                PipelineDiagnostics.provider_consecutive_failure.record(True)
                logger.warning(f"G-Process LLM call failed (iter {i}, consecutive={_g_consecutive_errors}): {provider_err}")
                if _g_consecutive_errors >= _G_MAX_CONSECUTIVE_ERRORS:
                    logger.error(f"G-Process circuit breaker: {_g_consecutive_errors} consecutive failures, aborting loop.")
                    raise RuntimeError(f"LLM provider 连续 {_g_consecutive_errors} 次失败，API 可能已下线: {provider_err}") from provider_err
                await asyncio.sleep(5)
                self.g_messages.append(Message(
                    role=MessageRole.SYSTEM,
                    content=f"[系统提示] 上次 LLM 调用因网络错误失败（{provider_err}），已自动重试。请继续未完成的任务。"
                ))
                continue
            
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
                    await self._safe_callback(step_callback, "tool_start", {"phase": "G_PHASE", "name": tc.name, "args": tc.arguments, "iteration": i})
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
                        await self._safe_callback(step_callback, "search_result", {"phase": "G_PHASE", "name": tc.name, "result": res, "iteration": i})
                        PipelineDiagnostics.search_zero_hit.record("未命中" in str(res) or "0 results" in str(res).lower())
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
                    payload = self._finalize_dispatch_payload(payload)
                    self._merge_signature_from_texts(payload.get("op_intent", ""), payload.get("instructions", ""))
                    self._merge_signature_from_nodes(payload.get("active_nodes", []))
                    logger.info("G-Process dispatched via tool call. Invoking Op-Process...")
                    dispatched_nodes = [n for n in payload.get("active_nodes", []) if n and not n.startswith("MEM_CONV")]
                    self.execution_active_nodes.extend(dispatched_nodes)
                    
                    # Multi-G 采纳率检测（dispatch 时机）
                    if self.blackboard and self.blackboard.entry_count > 0:
                        adoption = self._check_lens_adoption(
                            g_text=payload.get("op_intent", "") + " " + payload.get("instructions", ""),
                            g_active_nodes=dispatched_nodes,
                            event="dispatch"
                        )
                        await self._safe_callback(step_callback, "lens_adoption", {**adoption, "phase": "G_PHASE"})
                    
                    rendered = self.factory.render_dispatch_for_human(payload)
                    await self._safe_callback(step_callback, "blueprint", {"phase": "G_PHASE", "content": rendered, "op_intent": payload.get("op_intent", ""), "active_nodes": dispatched_nodes})
                    
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
                payload = self._finalize_dispatch_payload(payload)
                self._merge_signature_from_texts(payload.get("op_intent", ""), payload.get("instructions", ""))
                self._merge_signature_from_nodes(payload.get("active_nodes", []))
                logger.info("G-Process created Task Payload (fallback). Invoking Op-Process Subroutine...")
                dispatched_nodes = [n for n in payload.get("active_nodes", []) if n and not n.startswith("MEM_CONV")]
                self.execution_active_nodes.extend(dispatched_nodes)
                rendered = self.factory.render_dispatch_for_human(payload)
                await self._safe_callback(step_callback, "blueprint", {"phase": "G_PHASE", "content": rendered, "op_intent": payload.get("op_intent", ""), "active_nodes": dispatched_nodes})
                
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
                    # Multi-G 采纳率检测（final response 时机）
                    if self.blackboard and self.blackboard.entry_count > 0:
                        self._check_lens_adoption(
                            g_text=response.content,
                            g_active_nodes=list(self.execution_active_nodes),
                            event="final_response"
                        )
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

        signature_write_tools = {"record_context_node", "record_lesson_node", "create_meta_node"}
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
        verified_facts: List[str] = []
        failed_attempts: List[str] = []
        changes_made: List[str] = []
        artifacts: List[str] = []
        next_checks: List[str] = []
        open_questions: List[str] = []

        current_key = None
        summary_lines: List[str] = []
        findings_lines: List[str] = []
        section_map = {
            "VERIFIED_FACTS:": "verified_facts",
            "FAILED_ATTEMPTS:": "failed_attempts",
            "CHANGES_MADE:": "changes_made",
            "ARTIFACTS:": "artifacts",
            "NEXT_CHECKS:": "next_checks",
            "OPEN_QUESTIONS:": "open_questions"
        }
        list_buckets = {
            "verified_facts": verified_facts,
            "failed_attempts": failed_attempts,
            "changes_made": changes_made,
            "artifacts": artifacts,
            "next_checks": next_checks,
            "open_questions": open_questions,
        }

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

        has_structured_signal = match is not None or any(marker in block for marker in ["STATUS:", "SUMMARY:", "FINDINGS:", "VERIFIED_FACTS:", "FAILED_ATTEMPTS:", "CHANGES_MADE:", "ARTIFACTS:", "NEXT_CHECKS:", "OPEN_QUESTIONS:"])
        if not has_structured_signal:
            fallback_summary = block[:300] + ("..." if len(block) > 300 else "")
            status = "PARTIAL"
            summary = fallback_summary or "Op 返回了空白结果。"
            open_questions = ["Op 未按约定输出结构化执行报告，请 G 判断是否需要重新派发。"]
        elif not summary:
            summary = block[:300] + ("..." if len(block) > 300 else "")

        result = OpResult(
            status=status, summary=summary, findings=findings,
            verified_facts=verified_facts, failed_attempts=failed_attempts,
            changes_made=changes_made, artifacts=artifacts,
            next_checks=next_checks,
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

        if self.blackboard and len(self.blackboard.search_voids) >= 2:
            high_value = True
        if len(self.execution_active_nodes) >= 3:
            high_value = True
        if len(self.inferred_signature) >= 4:
            high_value = True

        if not high_value:
            return "SKIP"

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

    @staticmethod
    def _classify_tool_result(tool_name: str, result: str) -> bool:
        """从工具返回值提取客观成功/失败信号（环境信号，非 LLM 自报）。
        Returns True = 环境确认成功, False = 环境确认失败。"""
        if not result:
            return False
        r = result.strip()
        if r.startswith("Error:") or r.startswith("Error "):
            return False
        if "[TIMEOUT]" in r:
            return False
        if tool_name == "shell":
            m = re.search(r"退出码:\s*(\d+)", r)
            if m and int(m.group(1)) != 0:
                return False
        return True

    def _compute_env_success(self) -> Optional[float]:
        """计算 Op 工具调用的客观成功率。None = 无工具调用（无信号）。"""
        if not self._op_tool_outcomes:
            return None
        success_count = sum(1 for o in self._op_tool_outcomes if o["success"])
        return success_count / len(self._op_tool_outcomes)

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
        
        # Op system prompt 包含完整意图；追加最小 user 消息以兼容要求 user 角色的 API
        self.op_messages = [
            Message(role=MessageRole.SYSTEM, content=op_prompt),
            Message(role=MessageRole.USER, content="Execute.")
        ]
        
        # 获取所有执行工具 (除了反思专属的)
        all_tools = self._get_op_tools()

        schema = [t.to_schema() for t in all_tools]
        
        _op_consecutive_errors = 0
        _OP_MAX_CONSECUTIVE_ERRORS = 3
        op_max_iterations = _env_int("GENESIS_OP_MAX_ITERATIONS_OVERRIDE", self.OP_MAX_ITERATIONS, minimum=1)
        for i in range(op_max_iterations):
            # ⚠️ Op 内部不蒸发：Op 的 ReAct 循环需要完整记忆自己做过什么。
            # 蒸发只发生在 G（跨 dispatch）和 Lens（跨搜索轮次）中。
            
            # ── 优雅终止：倒数第 2 轮提醒 Op 收尾 ──
            if i == op_max_iterations - 2:
                self.op_messages.append(Message(
                    role=MessageRole.SYSTEM,
                    content=(
                        f"[系统提醒] 你还剩 2 轮迭代就会被强制终止。"
                        f"请立即停止新的工具调用，输出 op_result 执行报告总结你已完成的工作和未完成的部分。"
                        f"G 会根据你的报告决定是否需要继续派发。"
                    )
                ))
            
            self._llm_call_count += 1
            llm_call_started = time.time()
            llm_call_id = await self._emit_llm_call_start(step_callback, "OP_PHASE", i, stream=True)
            try:
                response = await self.provider.chat(
                    messages=[m.to_dict() for m in self.op_messages],
                    tools=schema,
                    stream=True,
                    stream_callback=lambda ev, data: self._stream_proxy(step_callback, ev, data, phase="OP_PHASE", llm_call_id=llm_call_id),
                    _trace_id=self.trace_id, _trace_phase="Op", _trace_parent=op_span
                )
                await self._emit_llm_call_end(step_callback, "OP_PHASE", llm_call_id, i, llm_call_started, stream=True, response=response)
                _op_consecutive_errors = 0  # 成功则重置计数器
            except Exception as provider_err:
                await self._emit_llm_call_end(step_callback, "OP_PHASE", llm_call_id, i, llm_call_started, stream=True, error=provider_err)
                _op_consecutive_errors += 1
                PipelineDiagnostics.provider_consecutive_failure.record(True)
                logger.warning(f"Op-Process LLM call failed (iter {i}, consecutive={_op_consecutive_errors}): {provider_err}")
                if _op_consecutive_errors >= _OP_MAX_CONSECUTIVE_ERRORS:
                    logger.error(f"Op-Process circuit breaker: {_op_consecutive_errors} consecutive failures, aborting.")
                    raise RuntimeError(f"LLM provider 连续 {_op_consecutive_errors} 次失败，API 可能已下线: {provider_err}") from provider_err
                await asyncio.sleep(5)
                self.op_messages.append(Message(
                    role=MessageRole.SYSTEM,
                    content=f"[系统提示] 上次 LLM 调用因网络错误失败（{provider_err}），已自动重试。请继续未完成的工具调用序列。"
                ))
                continue
            
            self._update_metrics(response, phase="Op")
            
            self.op_messages.append(Message(
                role=MessageRole.ASSISTANT,
                content=response.content,
                tool_calls=[tc.__dict__ for tc in response.tool_calls] if response.tool_calls else None
            ))
            
            if response.tool_calls:
                for tc in response.tool_calls:
                    await self._safe_callback(step_callback, "tool_start", {"phase": "OP_PHASE", "name": tc.name, "args": tc.arguments, "iteration": i})
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
                            PipelineDiagnostics.op_timeout.record(True)
                    
                    self.tracer.log_tool_call(
                        self.trace_id, parent=op_span, phase="Op",
                        tool_name=tc.name, tool_args=tc.arguments,
                        tool_result=str(res), duration_ms=(time.time() - t0) * 1000
                    )
                    await self._safe_callback(step_callback, "tool_result", {"phase": "OP_PHASE", "name": tc.name, "result": res, "iteration": i})
                    
                    self.metrics.tools_used.append(tc.name)
                    # 环境信号采集：记录工具调用的客观成功/失败
                    self._op_tool_outcomes.append({
                        "tool": tc.name,
                        "success": self._classify_tool_result(tc.name, str(res)),
                    })
                    
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
            self._update_knowledge_state_from_op_result(op_result)
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
            "summary": f"Op 达到迭代上限（{op_max_iterations}轮），已执行 {len(partial_work)} 步。",
            "findings": last_assistant or "Op 未输出阶段性结论",
            "verified_facts": [],
            "failed_attempts": [],
            "changes_made": [],
            "artifacts": [],
            "next_checks": ["让 G 基于已完成步骤和外部观测决定是否需要重新派发。"],
            "open_questions": [f"Op 在 {len(partial_work)} 步后被截断，G 应根据已完成步骤判断是否需要继续派发。"],
            "raw_output": f"已完成步骤：\n{partial_summary}"
        }
        self._update_knowledge_state_from_op_result(timeout_result)
        self.execution_reports.append(timeout_result)
        self._merge_signature_from_texts(timeout_result.get("summary", ""), "\n".join(timeout_result.get("open_questions", []) or []))
        self.tracer.end_span(op_span, status="timeout")
        # Session-scoped 注销：清理本次动态加载的工具
        for t_name in session_dynamic_tools:
            self.tools.unregister(t_name)
        if session_dynamic_tools:
            logger.info(f"Op超时: 注销 {len(session_dynamic_tools)} 个动态工具: {session_dynamic_tools}")
        return timeout_result

    async def _run_c_phase(self, step_callback: Any, mode: str = "FULL", g_final_response: str = ""):
        """运行 C-Process 反思循环，基于 Op 的执行轨迹。mode: FULL/LIGHT"""
        self._last_c_phase_mode = mode  # 供 get_phase_trace() 读取
        max_iter = self.C_PHASE_MAX_ITER.get(mode, 30)
        self._c_consecutive_errors = 0  # 每次 C-Phase 开始时重置，防止跨请求累积
        logger.info(f">>> Entering Phase 3: C-Process (Reflector) mode={mode}, max_iter={max_iter}")
        
        # 跨进程向量同步：拉取 Daemon/Scavenger 在 G/Op 期间新增的节点向量，
        # 确保 C 的 search_knowledge_nodes 能看到最新节点（LESSON 去重依赖此）
        self.vault.sync_vector_matrix_incremental()
        
        report_summary = self._build_execution_report_summary()
        # Knowledge Arena 反馈闭环（环境信号驱动）
        # 信号来源：Op 工具调用的客观结果（exit code / Error 前缀），非 Op 自报 STATUS
        # 阈值：>= 0.7 = 成功, <= 0.3 = 失败, 中间 / 无信号 = 中性（只记 usage_count）
        unique_active_nodes = list(dict.fromkeys(self.execution_active_nodes))
        env_ratio = self._compute_env_success()
        if unique_active_nodes:
            self.vault.increment_usage(unique_active_nodes)
            from genesis.tools.node_tools import SearchKnowledgeNodesTool
            fusion_weights = SearchKnowledgeNodesTool.get_fusion_scores(unique_active_nodes)
            if env_ratio is not None and env_ratio >= 0.7:
                self.vault.record_usage_outcome(unique_active_nodes, success=True, weights=fusion_weights)
                logger.info(f"Knowledge Arena: +boost for {len(unique_active_nodes)} nodes (env_ratio={env_ratio:.2f}, tools={len(self._op_tool_outcomes)})")
            elif env_ratio is not None and env_ratio <= 0.3:
                self.vault.record_usage_outcome(unique_active_nodes, success=False, weights=fusion_weights)
                logger.info(f"Knowledge Arena: -decay for {len(unique_active_nodes)} nodes (env_ratio={env_ratio:.2f}, tools={len(self._op_tool_outcomes)})")
            else:
                logger.info(f"Knowledge Arena: NEUTRAL for {len(unique_active_nodes)} nodes (env_ratio={env_ratio}, tools={len(self._op_tool_outcomes)})")

        # Persona 在线学习（同样使用环境信号）
        if self.blackboard and self.blackboard.entries:
            contributing_personas = list({e.persona for e in self.blackboard.entries})
            task_success = env_ratio is not None and env_ratio >= 0.7
            raw_atk = self.inferred_signature.get("task_kind") or ""
            arena_task_kind = (raw_atk[0] if isinstance(raw_atk, list) and raw_atk else str(raw_atk)).lower()
            Blackboard.record_persona_outcome(contributing_personas, success=task_success, task_kind=arena_task_kind)
            logger.info(f"Persona Arena: {'WIN' if task_success else 'LOSS/NEUTRAL'} for {contributing_personas} (env_ratio={env_ratio}, task_kind={arena_task_kind})")

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
        
        # G 综合判断：让 C 看到 G 的分析结论，而不仅仅是 Op 的工具日志
        g_analysis_block = ""
        if g_final_response and str(g_final_response).strip():
            g_analysis_block = f"\n[G 综合判断]\n{g_final_response}\n"

        # 自改进任务：Doctor 沙箱运行结果即为有效 Op 实证
        self_improvement_block = """
[自改进任务规则 — 覆盖默认 NO_ACTION 启发式]
本轮 Op 属于 Genesis 自改进内省任务（Doctor 沙箱诊断/修复）。
- shell 命令结果（diff 输出、测试通过/失败、py_compile 结果）= 有效 Op 实证
- G 的架构分析和系统诊断 = “结构性发现”，无需 search_knowledge_nodes 才能提炼
- 不适用“Op 只读了几个文件 → NO_ACTION”规则
- 诊断结论、架构缺陷 → CONTEXT 节点（target_kind: genesis_internals）
- 修复方案、因果规律 → 原子 LESSON 节点
"""

        # Multi-G 信息空洞：已记录到 void_tasks 队列，C 只需专注提炼 LESSON
        void_block = ""
        if self.blackboard:
            void_count = len(self.blackboard.search_voids)
            if void_count > 0:
                void_summaries = [v.get('query', '')[:60] for v in list(self.blackboard.search_voids)[:5]]
                void_list = '\n'.join(f'  - {q}' for q in void_summaries if q)
                void_block = f"\n[Multi-G 信息空洞] 本轮有 {void_count} 个搜索未命中（已记录到任务队列）：\n{void_list}\n如果本轮 Op 的执行结果恰好能回答其中某个空洞，将结论写成 LESSON 即可，VOID 解决会自动处理。\n"

        # ⚠️ 前缀缓存优化：稳定指令放前面，每次请求不同的变量内容放后面
        reflection_system_prompt = f"""你是 Genesis 反思进程 (C-Process)。审查 Op 的执行轨迹，提炼可复用的原子知识积木。

[核心原则：积木，不是预制件]
IF/THEN/BECAUSE 是好的模板——保留它。但每个 LESSON 必须是原子的：
- action_steps 只写 1 个核心步骤（不是 8 个焊在一起）
- 一个 LESSON = 一个触发信号 → 一个动作 → 一个原因
- 复杂流程 → 拆成多个原子 LESSON，用 create_node_edge(TRIGGERS) 串联

500 块积木的组合多样性远超 50 个预制件。你的工作是生产积木，不是浇筑预制件。
模板是组装说明书——描述积木之间的关系（边），不是把多件事焊死在一个节点里。
G 通过边"连根拔起"整个知识邻域，所以边比节点更重要。

[反面案例]
❌ action_steps 塞 5+ 个步骤（预制件，无法拆开复用）
❌ 创建节点后不建边（孤立积木无法被连根拔起）

[正面案例]
✅ LESSON "tag 不匹配时 v2ray 走默认路由" (action_steps=["检查 inbounds[].tag 与 routing 规则是否一致"])
   + 边 TRIGGERS → LESSON "v2ray tag 修改后需重启服务生效"
   + 边 REQUIRES → CTX "v2ray routing 靠 inbound tag 精确匹配"
✅ 一个洞察拆 2-3 个原子 LESSON + CTX，每对之间建一条边

{self_improvement_block}[判断：写还是不写]
不写日记，不记流水账。先判断这轮有没有长期价值。
Op 只读了几个文件且 G 无结构性发现 → NO_ACTION。
G 的综合判断含可复用认知（架构缺陷、因果关系、设计模式）→ 即使 Op 只读也提炼。

[VOID 升格]
Op 结果回答了已知知识缺口 → 写成原子 LESSON。VOID 状态由基础设施自动处理。
只在有 Op 实证时才提炼，不要凭空推测。
{void_block}
[节点类型] LESSON（因果规律）> ASSET（可复用规则/模板）> CONTEXT（环境事实）
不要创建 ENTITY/EVENT/ACTION/TOOL 节点。

[LESSON 原子性检验]
写完一个 LESSON 后问自己：action_steps 里的步骤能否独立复用于其他场景？
如果能 → 它应该是独立的 LESSON，不该塞在这个节点里。
resolves 必填。不可泛化的一次性流程不写。

[边的使用——每个新节点至少建一条边]
REQUIRES: A 成立的前提是 B
RESOLVES: A 解决了 B 描述的问题
RELATED_TO: A 和 B 在同一领域下互补
TRIGGERS: A 出现时应检查 B

[负向确认 — 防返鬼]
如果这轮 G 调查了某个信号，最终结论是"这是历史遗留/已修复/不复现"，你必须写一个 LESSON 记录这个结论：
- title: "信号 [XXX] 已确认为历史问题，无需再次调查"
- because_reason: 调查过程和结论证据
- metadata_signature 中加 resolution_status: "historical"
这条 LESSON 的作用是：下一个 session 的 G 搜到它时，直接跳过该信号，不重复调查。
不写这条 LESSON = 下轮 G 会从零重来，浪费整轮 token。

[认知策略]
用户嫌保守/激进/浅 → 写原子 LESSON，签名含 cognitive_approach + domain。
示例：LESSON "消费类调研应直接给深度分析"
签名：{{task_kind: "research", domain: "consumer_service", cognitive_approach: "aggressive"}}

[metadata_signature]
精准签名，只填实际涉及的值。核心字段：os_family, runtime, language, framework, task_kind, error_kind, target_kind, environment_scope。
反堆砌：每字段最多 2 值，task_kind 只填 1 个。
鼓励分类维度（severity, scope, pattern_type），禁止运营维度（timestamp, port, version）。
validation_status 只有明确证实时才填 validated。

{signature_block}
{report_summary}
{execution_summary}
{g_analysis_block}
"""
        c_messages = [
            Message(role=MessageRole.SYSTEM, content=reflection_system_prompt),
            Message(role=MessageRole.USER, content="Reflect.")
        ]
        
        c_tool_names = ["search_knowledge_nodes", "record_context_node", "record_lesson_node", "create_meta_node", "create_node_edge", "delete_node"]
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
                    
                c_tool_fail_fingerprints = getattr(self, "_c_tool_fail_fingerprints", {})
                for tc in tool_calls:
                    if tc.name not in c_tool_names:
                        res = f"Error: C-Process 禁止使用工具 {tc.name}"
                        c_messages.append(Message(role=MessageRole.TOOL, content=res, tool_call_id=tc.id, name=tc.name))
                        continue

                    prepared_args = self._prepare_c_tool_args(tc.name, tc.arguments)
                    try:
                        arg_repr = json.dumps(prepared_args, ensure_ascii=False, sort_keys=True, default=str)
                    except Exception:
                        arg_repr = repr(prepared_args)

                    # 去重：防止 C 反复调同一个失败工具（死循环）
                    cached_error = None
                    for known_fp, meta in c_tool_fail_fingerprints.items():
                        if meta.get("tool") == tc.name and meta.get("args_repr") == arg_repr:
                            cached_error = meta.get("error")
                            meta["count"] += 1
                            logger.warning(f"[C_TOOL_REPLAY] suppressed duplicate failed tool={tc.name} count={meta['count']}")
                            break

                    if cached_error is not None:
                        res = cached_error
                        c_messages.append(Message(role=MessageRole.TOOL, content=res, tool_call_id=tc.id, name=tc.name))
                        continue

                    res = await self.tools.execute(tc.name, prepared_args)
                    await self._safe_callback(step_callback, "tool_result", {"name": f"C-Process::{tc.name}", "result": res})

                    if isinstance(res, str) and res.startswith("Error:"):
                        fp_src = f"{tc.name}|{arg_repr}|{res}"
                        fp = hashlib.sha1(fp_src.encode("utf-8", errors="replace")).hexdigest()[:12]
                        c_tool_fail_fingerprints[fp] = {"count": 1, "tool": tc.name, "args_repr": arg_repr, "error": res}
                        self._c_tool_fail_fingerprints = c_tool_fail_fingerprints
                        logger.warning(f"[C_TOOL_REPLAY] first failure recorded tool={tc.name} fp={fp}")

                    c_messages.append(Message(role=MessageRole.TOOL, content=res, tool_call_id=tc.id, name=tc.name))
            except Exception as e:
                logger.error(f"Reflection step failed (continuing): {e}")
                _c_consecutive_errors = getattr(self, '_c_consecutive_errors', 0) + 1
                if _c_consecutive_errors >= 3:
                    logger.warning("C-Phase: 3 consecutive errors, stopping.")
                    break
                self._c_consecutive_errors = _c_consecutive_errors
                continue
        
        self.c_messages = list(c_messages)  # 落盘 C-Phase 对话轨迹
        c_node_created = any(
            m.role == MessageRole.TOOL and m.name in ("record_context_node", "record_lesson_node", "create_meta_node")
            and not str(m.content).startswith("Error")
            for m in c_messages
        )
        PipelineDiagnostics.c_phase_zero_output.record(not c_node_created)
        logger.info(f"C-Process finished. c_tokens={self.metrics.c_tokens}, total={self.metrics.total_tokens}, nodes_created={c_node_created}")
        await self._safe_callback(step_callback, "c_phase_done", {"mode": mode, "c_tokens": self.metrics.c_tokens})

    # ─── Lens methods provided by LensPhaseMixin ──────────────────────

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

    async def _stream_proxy(self, callback, event, data, phase: Optional[str] = None, llm_call_id: Optional[str] = None):
        """LLM 流式回调代理"""
        if not callback:
            return
        payload = dict(data) if isinstance(data, dict) else {"result": str(data)}
        if phase and not payload.get("phase"):
            payload["phase"] = phase
        if llm_call_id:
            payload["llm_call_id"] = llm_call_id
        if event in ("content", "reasoning"):
            payload["chunk_chars"] = len(payload.get("result", "") or "")
        await self._safe_callback(callback, event, payload)

    async def _emit_llm_call_start(self, step_callback: Any, phase: str, iteration: int, stream: bool, label: Optional[str] = None) -> str:
        self._llm_call_seq += 1
        llm_call_id = f"{phase.lower()}_{self._llm_call_seq}"
        payload = {
            "phase": phase,
            "llm_call_id": llm_call_id,
            "iteration": iteration,
            "stream": stream,
        }
        if label:
            payload["label"] = label
        await self._safe_callback(step_callback, "llm_call_start", payload)
        return llm_call_id

    async def _emit_llm_call_end(self, step_callback: Any, phase: str, llm_call_id: str, iteration: int, started_at: float, stream: bool, response: Any = None, error: Any = None, label: Optional[str] = None):
        payload = {
            "phase": phase,
            "llm_call_id": llm_call_id,
            "iteration": iteration,
            "stream": stream,
            "duration_ms": round((time.time() - started_at) * 1000, 1),
        }
        if label:
            payload["label"] = label
        if response is not None:
            payload.update({
                "finish_reason": getattr(response, "finish_reason", None),
                "tool_call_count": len(getattr(response, "tool_calls", []) or []),
                "content_chars": len(getattr(response, "content", "") or ""),
                "reasoning_chars": len(getattr(response, "reasoning_content", "") or ""),
                "input_tokens": getattr(response, "input_tokens", 0),
                "output_tokens": getattr(response, "output_tokens", 0),
                "total_tokens": getattr(response, "total_tokens", 0),
            })
        if error is not None:
            payload["error"] = str(error)[:300]
        await self._safe_callback(step_callback, "llm_call_end", payload)
