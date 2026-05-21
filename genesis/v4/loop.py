"""
Genesis V4 核心执行引擎 (State Machine)
实现 GP-Process (统一思考+执行) -> C-Process (Reflector) 管线
"""

import json
import os
import re
import time
import asyncio
import logging
import traceback
import hashlib
import inspect
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from genesis.core.base import Message, MessageRole, LLMProvider, PerformanceMetrics, ToolCall
from genesis.core.registry import ToolRegistry
from genesis.core.tracer import Tracer
from genesis.core.models import KnowledgeState
from genesis.v4.manager import FactoryManager, NodeVault, NodeManagementTools, TRUST_TIER_RANK, TOOL_EXEC_MIN_TIER, PERSONA_ACTIVATION_MAP
from genesis.v4.blackboard import Blackboard
from genesis.v4.diagnostics import PipelineDiagnostics
from genesis.v4.lens_phase import LensPhaseMixin
from genesis.v4.c_phase import CPhaseMixin
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

# GP 禁用工具名（仅 C-Phase Gardener 可用的节点管理工具）
GP_BLOCKED_TOOLS = frozenset([
    "record_context_node", "record_lesson_node", "create_meta_node",
    "delete_node", "create_graph_node", "create_node_edge",
    "record_tool_node", "record_discovery", "pls_query",
])

class V4Loop(LensPhaseMixin, CPhaseMixin):
    """
    V4 核心管线 (GP 统一模式)

    Phases:
    1. GP_PHASE (思考+执行): 拥有完整上下文和所有工具，搜索→思考→执行→回复。
    2. C_PHASE (反思): (Post-loop) 仅允许节点管理工具，沉淀知识。
    """

    C_PHASE_MAX_ITER = PIPELINE_CONFIG.c_phase_max_iter
    TOOL_EXEC_TIMEOUT = PIPELINE_CONFIG.tool_exec_timeout
    CONSUMED_TOOL_RECEIPT_LIMITS = {
        "search_knowledge_nodes": 5000,
        "get_knowledge_node_content": 4500,
        "read_file": 4000,
        "shell": 3500,
        "web_search": 2500,
    }
    DEFAULT_CONSUMED_TOOL_RECEIPT_LIMIT = 1800
    PHASE_TRACE_SIGNATURE_BUDGET = 6000

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
        self.c_messages: List[Message] = []  # C-Phase 对话轨迹，每轮覆写
        self.inferred_signature: Dict[str, Any] = {}
        self.blackboard: Optional[Blackboard] = None  # Multi-G 黑板
        self._llm_call_seq = 0
        self._surface_potential_sample_count = 0
        self._reported_potential_sample_count = 0
        self.potential_baseline: Dict[str, int] = {}
        self.current_state_preview: Dict[str, Any] = {}
        self._current_state_surfaces: Dict[str, Any] = {}
        self._knowledge_routing_preview: Dict[str, Any] = {}
        self._lens_preview: Dict[str, Any] = {}

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

    async def run(self, user_input: str, step_callback: Any = None, image_paths: Optional[List[str]] = None, loop_config: Optional[Dict[str, Any]] = None, initial_knowledge_state: Optional[Dict[str, Any]] = None, knowledge_cursor: Optional[Dict[str, Any]] = None, session_id: str = None) -> Tuple[str, PerformanceMetrics]:
        """执行主管线 GP -> C (Unified Mode)"""
        self.metrics.start_time = time.time()
        self.user_input = user_input
        self.session_id = session_id
        self.image_paths = image_paths or []
        self.loop_config = dict(loop_config or {})
        self.g_messages = []
        self.execution_active_nodes: List[str] = []  # Knowledge Arena: 追踪被使用的节点
        self.execution_active_node_roles: Dict[str, set] = {}
        self._gp_reached_max_iterations = False
        self._knowledge_cursor_in = knowledge_cursor  # 上轮知识游标
        self._op_tool_outcomes: List[Dict[str, Any]] = []  # 环境信号：工具调用客观结果
        self._signature_drift_events: List[Dict[str, Any]] = []  # 签名偏差检测事件
        # 签名推断只用用户实际请求，排除频道历史等上下文噪音
        _sig_input = user_input
        if "[GENESIS_USER_REQUEST_START]" in user_input:
            _sig_input = user_input.split("[GENESIS_USER_REQUEST_START]", 1)[1]
        self.inferred_signature = self.vault.signature.infer(_sig_input)
        self.blackboard = None  # 每次请求重置
        self._llm_call_seq = 0
        self._surface_potential_sample_count = 0
        self._reported_potential_sample_count = 0
        self.potential_baseline = {}
        self.current_state_preview = {}
        self._current_state_surfaces = {}
        self._knowledge_routing_preview = {}
        self._lens_preview = {}
        self.knowledge_state = self._normalize_knowledge_state(initial_knowledge_state)
        seed_lines = [line.strip() for line in _sig_input.splitlines() if line.strip()]
        if not self.knowledge_state.get("issue") and seed_lines:
            self.knowledge_state["issue"] = self._clean_knowledge_state_text(seed_lines[0])

        # === Multi-G 透镜预激活 ===
        disable_multi_g = self.loop_config.get("disable_multi_g")
        if disable_multi_g is None:
            disable_multi_g = _env_bool("GENESIS_DISABLE_MULTI_G", False)
        if disable_multi_g:
            reason = "runtime_disabled" if "disable_multi_g" in self.loop_config else "env_disabled"
            self._lens_preview = {"status": "skipped", "reason": reason}
            await self._safe_callback(step_callback, "lens_skipped", {"phase": "LENS_PHASE", "reason": reason})
        elif self._should_activate_multi_g(user_input):
            try:
                self.blackboard = await self._run_lens_phase(user_input, step_callback)
                self._lens_preview = {
                    "status": "active",
                    "entries": self.blackboard.entry_count,
                    "voids": len(self.blackboard.search_voids),
                }
                logger.info(f"Multi-G lens phase completed: {self.blackboard.entry_count} entries, {len(self.blackboard.search_voids)} voids")
            except Exception as e:
                logger.error(f"Multi-G lens phase failed (falling back to single-G): {e}", exc_info=True)
                self.blackboard = None
                self._lens_preview = {"status": "failed", "reason": str(e)[:160]}
        else:
            self._lens_preview = {"status": "skipped", "reason": "gate_closed"}
            await self._safe_callback(step_callback, "lens_skipped", {"phase": "LENS_PHASE", "reason": "gate_closed"})

        # === Tracing ===
        self.tracer = Tracer.get_instance()
        self.trace_id = self.tracer.start_trace(user_input)

        # === V6 Signature Shadow Prediction (Silent Shadow Mode) ===
        try:
            from genesis.v6.signature_shadow import SignatureShadowPredictor, append_jsonl, DEFAULT_LOG_PATH
            
            def _run_shadow_prediction(text: str, trace_id: str, db_path: Path):
                try:
                    predictor = SignatureShadowPredictor(
                        fields=["error_kind", "framework", "task_kind", "runtime", "target_kind"],
                        min_label_count=3,
                        max_tokens=160,
                        alpha=1.0
                    )
                    predictor.fit(db_path)
                    result = predictor.predict(text, top_k=3)
                    record = {
                        "mode": "shadow_only",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "trace_id": trace_id,
                        "user_input_preview": text[:300],
                        "nodevault_db": str(db_path),
                        **result,
                    }
                    append_jsonl(DEFAULT_LOG_PATH, record)
                    logger.info(f"V6 Shadow Prediction logged for trace_id={trace_id}")
                except Exception as shadow_err:
                    logger.warning(f"V6 Shadow Prediction internal error: {shadow_err}")

            asyncio.create_task(
                asyncio.to_thread(
                    _run_shadow_prediction,
                    user_input,
                    self.trace_id,
                    self.vault.db_path
                )
            )
        except Exception as shadow_outer_err:
            logger.warning(f"V6 Shadow Prediction failed to schedule: {shadow_outer_err}")

        self._phase_count = 0
        self._llm_call_count = 0
        self._tool_call_count = 0
        self._recent_tool_calls: Dict[str, int] = {}  # "tool_name|args_hash" → count

        final_response = ""

        try:
            # === GP-Process: Unified Thinker+Executor ===
            final_response = await self._run_main_loop(user_input, step_callback)

        except Exception as e:
            logger.error(f"Pipeline execution error: {traceback.format_exc()}")
            self.metrics.success = False
            raise

        # 兜底防护：确保 final_response 永不为空
        if not final_response or not str(final_response).strip():
            logger.error(f"CRITICAL: final_response is empty after pipeline. g_messages count: {len(self.g_messages)}, llm_calls: {self._llm_call_count}, tool_calls: {self._tool_call_count}")
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
        # Token budget 守卫：GP 消耗过多时降级 C，防止上下文溢出或注意力退化
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
                logger.info(f"C-Process completed (blocking mode={c_mode}, GP={self.metrics.g_tokens}t).")
            else:
                task = asyncio.create_task(self._run_c_phase_safe(step_callback, c_mode, g_final_response=final_response))
                task.add_done_callback(lambda t: t.exception() and logger.error(f"C-Process background task failed: {t.exception()}") if not t.cancelled() else None)
                logger.info(f"C-Process launched in background (mode={c_mode}, GP={self.metrics.g_tokens}t).")
        else:
            logger.info(f"Skipping C-Process: mode=SKIP (GP={self.metrics.g_tokens}t).")

        # Multi-G 空洞自动入库（放在 C 之后，避免改变 digest 导致 G 缓存失效）
        if self.blackboard:
            self._auto_record_voids(self.blackboard)

        # 签名偏差数据写入 heartbeat，供外部监控和自诊断
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
        potential_sample_count = self.vault.count_potential_samples(self.trace_id) if hasattr(self.vault, "count_potential_samples") else self._surface_potential_sample_count
        current_state_preview = self.get_current_state_preview()
        self.vault.heartbeat("main_loop", "idle",
            f"done GP={self.metrics.g_tokens}t cache={cache_stats['cache_hit_rate']*100:.1f}%" if cache_stats else f"done GP={self.metrics.g_tokens}t",
            extra={
                "signature_drift": sig_drift_summary,
                "persona_stats": persona_stats,
                "provider_stats": provider_stats,
                "token_efficiency": token_efficiency,
                "kb_entropy": kb_entropy,
                "cache_stats": cache_stats,
                "diagnostics": diagnostics_summary,
                "potential_samples": {
                    "trace_count": potential_sample_count,
                    "routing_count": self._surface_potential_sample_count,
                },
                "current_state_preview": current_state_preview,
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


    def get_phase_trace(self) -> Dict[str, Any]:
        """序列化 GP/C 两阶段完整对话轨迹，供经历复盘使用。
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
            "gp": _ser(self.g_messages, "GP"),
            "c": _ser(self.c_messages, "C"),
            "c_phase_mode": getattr(self, "_last_c_phase_mode", None),
            "inferred_signature": self._compact_signature_for_trace(self.inferred_signature),
            "knowledge_state": self.get_knowledge_state(),
            "current_state_preview": self.get_current_state_preview(),
        }

    def get_knowledge_state(self) -> Dict[str, Any]:
        return self._normalize_knowledge_state(getattr(self, "knowledge_state", {}))

    def get_current_state_preview(self) -> Dict[str, Any]:
        active_ids = list(dict.fromkeys(getattr(self, "execution_active_nodes", []) or []))[:12]
        roles_by_node = getattr(self, "execution_active_node_roles", {}) or {}
        titles = {}
        if active_ids:
            try:
                titles = self.vault.batch_get_titles(active_ids) if hasattr(self.vault, "batch_get_titles") else {}
            except Exception:
                titles = {}
        active_nodes = []
        for node_id in active_ids:
            active_nodes.append({
                "node_id": node_id,
                "title": titles.get(node_id, ""),
                "roles": sorted(str(role) for role in roles_by_node.get(node_id, set())),
            })
        outcomes = getattr(self, "_op_tool_outcomes", []) or []
        tool_outcome_summary = {
            "total": len(outcomes),
            "success": sum(1 for item in outcomes if item.get("success") is True),
            "failed": sum(1 for item in outcomes if item.get("success") is False),
            "neutral": sum(1 for item in outcomes if item.get("success") is None),
        }
        issue = self._trim_context_text((self.get_knowledge_state() or {}).get("issue", ""), 240)
        signature = self._compact_signature_for_trace(getattr(self, "inferred_signature", {}))
        prompt_surfaces = dict(getattr(self, "_current_state_surfaces", {}) or {})
        routing_state = dict(getattr(self, "_knowledge_routing_preview", {}) or {})
        execution_state = {
            "active_nodes": active_nodes,
            "tool_outcomes": tool_outcome_summary,
        }
        preview = {
            "schema": "genesis.current_state_preview.v1",
            "time_slices": {
                "input_state": {
                    "issue": issue,
                    "signature": signature,
                    "prompt_surfaces": prompt_surfaces,
                },
                "routing_state": routing_state,
                "execution_state": execution_state,
                "post_round_state_ref": {
                    "available_in_auto_report": "knowledge_state",
                    "phase": "after_round",
                },
            },
            "issue": issue,
            "signature": signature,
            "prompt_surfaces": prompt_surfaces,
            "lens": dict(getattr(self, "_lens_preview", {}) or {}),
            "routing": routing_state,
            "active_nodes": active_nodes,
            "tool_outcomes": tool_outcome_summary,
        }
        self.current_state_preview = preview
        return preview

    def _trim_context_text(self, text: Any, limit: int) -> str:
        compact = str(text or "")
        if len(compact) <= limit:
            return compact
        head_len = max(0, int(limit * 0.65))
        tail_len = max(0, limit - head_len - 90)
        omitted = len(compact) - head_len - tail_len
        tail = compact[-tail_len:].lstrip() if tail_len else ""
        suffix = f"\n\n...[已省略 {omitted} 字符，完整结果已记录在 trace/report]..."
        return compact[:head_len].rstrip() + (suffix + "\n\n" + tail if tail else suffix)

    def _summarize_consumed_tool_result(self, tool_name: str, result: str) -> str:
        text = str(result or "")
        limit = self.CONSUMED_TOOL_RECEIPT_LIMITS.get(tool_name, self.DEFAULT_CONSUMED_TOOL_RECEIPT_LIMIT)
        summary = self._trim_context_text(text, limit)
        priority_lines = []
        if tool_name == "search_knowledge_nodes":
            for line in text.splitlines():
                stripped = line.strip()
                if "[建议挂载]" in stripped or stripped.startswith("[PLS") or stripped.startswith("POINT ["):
                    if stripped not in priority_lines:
                        priority_lines.append(stripped[:500])
                if len(priority_lines) >= 8:
                    break
        if priority_lines:
            prefix = "\n".join(priority_lines)
            if prefix not in summary:
                summary = prefix + "\n\n" + summary
        if summary != text:
            return f"[已消费工具结果收据：{tool_name}]\n{summary}"
        return summary

    def _messages_for_provider(self) -> List[Dict[str, Any]]:
        last_assistant_idx = -1
        for idx, msg in enumerate(self.g_messages):
            if msg.role == MessageRole.ASSISTANT:
                last_assistant_idx = idx
        out = []
        for idx, msg in enumerate(self.g_messages):
            if msg.role == MessageRole.TOOL and idx < last_assistant_idx:
                out.append(Message(
                    role=MessageRole.TOOL,
                    content=self._summarize_consumed_tool_result(msg.name or "tool", msg.content or ""),
                    tool_call_id=msg.tool_call_id,
                    name=msg.name,
                ).to_dict())
            else:
                out.append(msg.to_dict())
        return out

    def _compact_signature_for_trace(self, signature: Any) -> Dict[str, Any]:
        try:
            normalized = self.vault.signature.normalize(signature)
        except Exception:
            normalized = signature if isinstance(signature, dict) else {}
        compact: Dict[str, Any] = {}
        for key in sorted((normalized or {}).keys()):
            value = normalized.get(key)
            if not value:
                continue
            if key == "evidence_refs":
                continue
            if isinstance(value, list):
                item = [self._trim_context_text(str(v), 120) for v in value[:3] if v]
            else:
                item = self._trim_context_text(str(value), 120)
            candidate = dict(compact)
            candidate[key] = item
            if len(json.dumps(candidate, ensure_ascii=False, default=str)) > self.PHASE_TRACE_SIGNATURE_BUDGET:
                compact["_truncated"] = True
                break
            compact[key] = item
        return compact

    @staticmethod
    def _clean_knowledge_state_text(text: Any) -> str:
        return " ".join(str(text or "").split())

    def _normalize_knowledge_state(self, knowledge_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        raw = knowledge_state if isinstance(knowledge_state, dict) else {}
        normalized = KnowledgeState(
            issue=self._clean_knowledge_state_text(raw.get("issue", "")),
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
                cleaned = self._clean_knowledge_state_text(value)
                if not cleaned or cleaned.upper() == "NONE" or cleaned in cleaned_values:
                    continue
                cleaned_values.append(cleaned)
            normalized[key] = cleaned_values
        return normalized

    async def _run_main_loop(self, user_input: str, step_callback: Any) -> str:
        """运行 GP 统一进程：思考 + 执行在同一上下文"""
        logger.info(">>> Entering GP-Process (Unified Thinker+Executor)")
        await self._safe_callback(step_callback, "loop_start", {"phase": "GP_PHASE"})
        self._phase_count += 1
        self._g_span = self.tracer.start_span(self.trace_id, "GP_PHASE", span_type="phase", phase="GP")

        self.vault.heartbeat("main_loop", "running", f"GP start: {user_input[:60]}")
        # 生成执行经验摘要（程序性记忆层）
        trace_exp = ""
        try:
            from genesis.v4.trace_pipeline.runner import generate_experience_summary
            trace_exp = generate_experience_summary()
        except Exception as e:
            logger.debug(f"Trace experience summary skipped: {e}")

        # GP 工具列表提前计算，同时传入 prompt 生成（消除 prompt-registry 脱节）
        gp_tools = self._get_gp_tools()
        gp_tool_names = [t.name for t in gp_tools]

        recent_memory = self.vault.get_recent_memory()
        inferred_signature_text = self.vault.signature.render(self.inferred_signature)
        daemon_status = self.vault.get_daemon_status_summary()
        knowledge_state_text = self.factory.render_knowledge_state(self.knowledge_state)
        knowledge_map = self.vault.generate_l1_digest()
        self._current_state_surfaces = {
            "recent_memory": "present" if recent_memory else "absent",
            "inferred_signature": "present" if inferred_signature_text else "absent",
            "daemon_status": "present" if daemon_status else "absent",
            "knowledge_state": "present" if knowledge_state_text else "absent",
            "knowledge_map": "present" if knowledge_map else "absent",
            "trace_experience": "present" if trace_exp else "absent",
            "gp_tool_count": len(gp_tool_names),
        }

        gp_prompt = self.factory.build_gp_prompt(
            recent_memory=recent_memory,
            inferred_signature=inferred_signature_text,
            daemon_status=daemon_status,
            knowledge_state=knowledge_state_text,
            knowledge_map=knowledge_map,
            trace_experience=trace_exp,
            gp_tool_names=gp_tool_names,
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
            Message(role=MessageRole.SYSTEM, content=gp_prompt),
            Message(role=MessageRole.USER, content=user_content)
        ]

        # === Multi-G 黑板注入：如果透镜阶段已完成，将结果注入 GP 的上下文 ===
        if self.blackboard and self.blackboard.entry_count > 0:
            collapse_results = self.blackboard.collapse(self.vault)
            board_text = self.blackboard.render_for_g(collapse_results=collapse_results)
            collapse_summary_lines = ["[坍缩排名]"]
            for rank, item in enumerate(collapse_results[:5], 1):
                e = item["entry"]
                collapse_summary_lines.append(f"  {rank}. [{e.persona}] score={item['score']:.3f} — {e.framework}")
            collapse_text = "\n".join(collapse_summary_lines)

            # 提取 top entry 的 verification_action，如果具体则建议 GP 优先执行
            verification_hint = ""
            if collapse_results:
                top_entry = collapse_results[0]["entry"]
                if hasattr(top_entry, "verification_action") and top_entry.verification_action:
                    va = top_entry.verification_action.strip()
                    if len(va) > 10:
                        verification_hint = f"\n\n[建议优先验证]\n透镜 {top_entry.persona} 建议的最小验证动作：{va}\n如果此动作可行，建议优先执行它，以快速确认或否定假设。"

            self.g_messages.append(Message(
                role=MessageRole.SYSTEM,
                content=f"[Multi-G 透镜侦察完毕]\n你的透镜子程序已从不同认知视角检索了知识库，以下是汇总。你可以参考但不必盲从——你是主脑，保留最终判断权。\n\n{board_text}\n\n{collapse_text}{verification_hint}"
            ))
            logger.info(f"Multi-G blackboard injected into GP context: {self.blackboard.entry_count} entries, top={collapse_results[0]['entry'].persona if collapse_results else 'N/A'}")

        # === 知识路由层：预加载上轮活跃节点，避免每次全量搜索 ===
        routing_text = self._apply_knowledge_routing()
        if routing_text:
            self.g_messages.append(Message(
                role=MessageRole.SYSTEM,
                content=routing_text,
            ))
            if self._surface_potential_sample_count:
                await self._safe_callback(step_callback, "surface_potential_samples", {
                    "phase": "GP_PHASE",
                    "source": "knowledge_routing",
                    "count": self._surface_potential_sample_count,
                })
                self._reported_potential_sample_count = self._surface_potential_sample_count

        schema = [t.to_schema() for t in gp_tools]

        _consecutive_errors = 0
        _MAX_CONSECUTIVE_ERRORS = 3
        gp_max_iterations = _env_int("GENESIS_GP_MAX_ITERATIONS_OVERRIDE", self.max_iterations, minimum=1)
        for i in range(gp_max_iterations):
            # === 跨进程向量同步：拉取后台进程新增的节点向量 ===
            self.vault.sync_vector_matrix_incremental()

            # ── 优雅提醒：倒数第 5 轮提醒 GP 收尾 ──
            if i == gp_max_iterations - 5:
                self.g_messages.append(Message(
                    role=MessageRole.SYSTEM,
                    content="[系统提醒] 你还剩约 5 轮迭代。请开始收尾，向用户输出最终回复。"
                ))

            # ── 知识路径持续提醒（仅 auto 模式，对抗 Instruction Attenuation）──
            _unblocked = set(self.loop_config.get("gp_unblock_tools") or [])
            if "record_context_node" in _unblocked and "record_point" in self.tools and i >= 8 and i % 5 == 3:
                self.g_messages.append(Message(
                    role=MessageRole.SYSTEM,
                    content="[知识路径] 回顾到目前为止是否形成了以后还会用到的新理解；如果只是复述或临时细节，不需要记录。若确实值得保存，用 record_point 写点，再用 record_line 连到依据节点；每条线的 reasoning 回答不同的因果问题。"
                ))

            self._llm_call_count += 1
            jailbreak = {"role": "system", "content": "[Reminder] 你有知识库和执行工具。能动手就动手，能查就查，别空谈。"}
            messages_to_send = self._messages_for_provider() + [jailbreak]
            llm_call_started = time.time()
            llm_call_id = await self._emit_llm_call_start(step_callback, "GP_PHASE", i, stream=True)
            try:
                response = await self.provider.chat(
                    messages=messages_to_send,
                    tools=schema,
                    stream=True,
                    stream_callback=lambda ev, data: self._stream_proxy(step_callback, ev, data, phase="GP_PHASE", llm_call_id=llm_call_id),
                    _trace_id=self.trace_id, _trace_phase="GP", _trace_parent=self._g_span
                )
                await self._emit_llm_call_end(step_callback, "GP_PHASE", llm_call_id, i, llm_call_started, stream=True, response=response)
                _consecutive_errors = 0
            except Exception as provider_err:
                await self._emit_llm_call_end(step_callback, "GP_PHASE", llm_call_id, i, llm_call_started, stream=True, error=provider_err)
                _consecutive_errors += 1
                PipelineDiagnostics.provider_consecutive_failure.record(True)
                logger.warning(f"GP LLM call failed (iter {i}, consecutive={_consecutive_errors}): {provider_err}")
                if _consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                    logger.error(f"GP circuit breaker: {_consecutive_errors} consecutive failures, aborting.")
                    raise RuntimeError(f"LLM provider 连续 {_consecutive_errors} 次失败，API 可能已下线: {provider_err}") from provider_err
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
                tool_calls=[tc.__dict__ for tc in response.tool_calls] if response.tool_calls else None,
                reasoning_content=getattr(response, 'reasoning_content', None)
            ))

            if response.tool_calls:
                # ═══════════════════════════════════════════════════════
                # 三阶段并行工具执行
                # Phase 1: 预检查（串行）— 断路器 + 权限 + 并发安全分类
                # Phase 2: 执行（safe 并行, unsafe 串行）— 纯 IO，无副作用
                # Phase 3: 后处理（串行）— 按原始顺序处理所有副作用
                # ═══════════════════════════════════════════════════════
                _unblock = set(self.loop_config.get("gp_unblock_tools") or [])

                # Phase 1: 预检查
                exec_plan = []  # [(tc, should_execute, skip_reason, is_safe)]
                for tc in response.tool_calls:
                    await self._safe_callback(step_callback, "tool_start", {"phase": "GP_PHASE", "name": tc.name, "args": tc.arguments, "iteration": i})
                    self._tool_call_count += 1

                    # 断路器检查
                    _call_key = f"{tc.name}|{json.dumps(tc.arguments, sort_keys=True, ensure_ascii=False)[:200]}"
                    self._recent_tool_calls[_call_key] = self._recent_tool_calls.get(_call_key, 0) + 1
                    if self._recent_tool_calls[_call_key] >= 3:
                        logger.warning(f"Circuit breaker: {tc.name} called {self._recent_tool_calls[_call_key]}x with same args")
                        exec_plan.append((tc, False, "breaker", False))
                        continue

                    # GP 权限检查
                    if tc.name in GP_BLOCKED_TOOLS and tc.name not in _unblock:
                        exec_plan.append((tc, False, "blocked", False))
                        continue

                    # 并发安全分类
                    is_safe = self.tools.is_concurrency_safe(tc.name, tc.arguments)
                    exec_plan.append((tc, True, None, is_safe))

                # Phase 2: 执行
                tool_results = {}  # tc.id → (res_text, duration_ms)

                async def _exec_single(tc):
                    """执行单个工具，返回 (tc, res_text, duration_ms)"""
                    t0 = time.time()
                    try:
                        tool_args = dict(tc.arguments or {})
                        if tc.name in {"record_lesson_node", "record_point", "record_line", "search_knowledge_nodes"}:
                            tool = self.tools.get(tc.name)
                            try:
                                params = inspect.signature(getattr(tool, "execute")).parameters if tool else {}
                            except Exception:
                                params = {}
                            accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
                            if accepts_kwargs or "_trace_id" in params:
                                tool_args.setdefault("_trace_id", self.trace_id)
                            if accepts_kwargs or "_round_seq" in params:
                                tool_args.setdefault("_round_seq", i)
                        if tc.name == "search_knowledge_nodes" and hasattr(self.vault, "count_potential_samples"):
                            self.potential_baseline[tc.id] = self.vault.count_potential_samples(self.trace_id)
                        res = await asyncio.wait_for(
                            self.tools.execute(tc.name, tool_args),
                            timeout=self.TOOL_EXEC_TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        res = f"Error: 工具 {tc.name} 执行超时（{self.TOOL_EXEC_TIMEOUT}秒），已强制终止。"
                        logger.warning(f"GP tool timeout: {tc.name} exceeded {self.TOOL_EXEC_TIMEOUT}s")
                        PipelineDiagnostics.op_timeout.record(True)
                    except Exception as e:
                        # API 不稳定容错：单个工具失败不影响其他工具
                        res = f"Error: 工具 {tc.name} 执行异常: {str(e)[:500]}"
                        logger.error(f"GP tool error: {tc.name} — {e}")
                    duration_ms = (time.time() - t0) * 1000
                    return tc, str(res), duration_ms

                # 并行执行 safe 工具
                safe_tasks = [tc for tc, should_exec, _, is_safe in exec_plan
                              if should_exec and is_safe]
                if safe_tasks:
                    gathered = await asyncio.gather(
                        *[_exec_single(tc) for tc in safe_tasks],
                        return_exceptions=True
                    )
                    for item in gathered:
                        if isinstance(item, Exception):
                            logger.error(f"Parallel tool execution failed: {item}")
                            continue
                        tc, res_text, dur = item
                        tool_results[tc.id] = (res_text, dur)
                    if len(safe_tasks) > 1:
                        logger.info(f"GP parallel: {len(safe_tasks)} safe tools executed concurrently")

                # 串行执行 unsafe 工具
                unsafe_tasks = [tc for tc, should_exec, _, is_safe in exec_plan
                                if should_exec and not is_safe]
                for tc in unsafe_tasks:
                    _, res_text, dur = await _exec_single(tc)
                    tool_results[tc.id] = (res_text, dur)

                # Phase 3: 后处理（按原始 tool_call 顺序，保证副作用一致性）
                for tc, should_exec, skip_reason, is_safe in exec_plan:
                    if not should_exec:
                        if skip_reason == "breaker":
                            res_text = f"[断路器] 你已经用相同参数调用 {tc.name} 达 {self._recent_tool_calls[f'{tc.name}|{json.dumps(tc.arguments, sort_keys=True, ensure_ascii=False)[:200]}']} 次。请换一种方法或不同参数。"
                        elif skip_reason == "blocked":
                            res_text = f"Error: GP 禁止使用工具 {tc.name}（该工具仅限反思进程使用）"
                        duration_ms = 0
                    else:
                        res_text, duration_ms = tool_results.get(tc.id, ("Error: 工具执行结果丢失", 0))
                        # 环境信号采集
                        self._op_tool_outcomes.append({
                            "tool": tc.name,
                            "success": self._classify_tool_result(tc.name, res_text),
                        })
                        # 签名学习
                        self._merge_signature_from_texts(res_text[:500])
                        if tc.name == "search_knowledge_nodes" and hasattr(self.vault, "count_potential_samples"):
                            current_potential_count = self.vault.count_potential_samples(self.trace_id)
                            baseline_count = self.potential_baseline.get(tc.id, 0) or 0
                            new_potential_count = max(0, current_potential_count - baseline_count)
                            if new_potential_count:
                                await self._safe_callback(step_callback, "surface_potential_samples", {
                                    "phase": "GP_PHASE",
                                    "source": "search_knowledge_nodes",
                                    "count": new_potential_count,
                                    "iteration": i,
                                })

                    await self._safe_callback(step_callback, "tool_result", {
                        "phase": "GP_PHASE",
                        "name": tc.name,
                        "args": tc.arguments,
                        "result": res_text,
                        "iteration": i,
                        "duration_ms": round(duration_ms, 1),
                    })
                    is_success = self._classify_tool_result(tc.name, res_text)
                    self.tracer.log_tool_call(
                        self.trace_id, parent=self._g_span, phase="GP",
                        tool_name=tc.name, tool_args=tc.arguments,
                        tool_result=res_text, duration_ms=duration_ms,
                        error=None if is_success else res_text[:200]
                    )
                    self.metrics.tools_used.append(tc.name)
                    if tc.name == "search_knowledge_nodes":
                        self._track_active_nodes_from_search(res_text)
                    elif tc.name == "get_knowledge_node_content":
                        node_id = str((tc.arguments or {}).get("node_id") or "").strip()
                        if node_id:
                            self._mark_active_nodes([node_id], "tool_opened")
                    self.g_messages.append(Message(role=MessageRole.TOOL, content=res_text, tool_call_id=tc.id, name=tc.name))

                continue

            # ── 纯文本回复路径 ──
            # 无 tool_calls → GP 的文本就是对用户的最终回复
            if response.content and response.content.strip():
                logger.info(f"GP provided final response. length={len(response.content)}, preview={response.content[:80]!r}")
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
                logger.warning(f"GP returned empty content (iter {i}). Retrying.")
                if self.g_messages and self.g_messages[-1].role == MessageRole.ASSISTANT:
                    self.g_messages.pop()
                continue

        logger.warning(f"GP reached max iterations ({gp_max_iterations}) without finalizing.")
        self._gp_reached_max_iterations = True
        self.tracer.end_span(self._g_span, status="timeout")
        for msg in reversed(self.g_messages):
            if msg.role == MessageRole.ASSISTANT and msg.content and msg.content.strip():
                logger.info("Recovered response from last GP assistant message after timeout.")
                return msg.content
        return "思考达到最大迭代限制，未能生成回复。"

    def _merge_signature_from_texts(self, *texts: str):
        inferred_parts = [self.vault.signature.infer(text) for text in texts if text and str(text).strip()]
        self.inferred_signature = self.vault.signature.merge(self.inferred_signature, *inferred_parts)

    def _merge_signature_from_artifacts(self, artifacts: List[str]):
        if not artifacts:
            return
        artifact_signature = self.vault.signature.infer_from_artifacts(artifacts)
        self.inferred_signature = self.vault.signature.merge(self.inferred_signature, artifact_signature)

    def _merge_signature_from_nodes(self, node_ids: List[str]):
        if not node_ids:
            return
        expanded_signature = self.vault.signature.expand_from_node_ids(node_ids)
        self.inferred_signature = self.vault.signature.merge(self.inferred_signature, expanded_signature)

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

    def _get_gp_tools(self) -> List[Any]:
        """获取 GP 可用的所有工具（排除 C-Phase 专属工具）

        loop_config.gp_unblock_tools: 允许选择性解禁部分 GP_BLOCKED_TOOLS，
        例如 auto 模式下解禁 record_context_node 让 GP 创建结构锚点。
        """
        unblock = set(self.loop_config.get("gp_unblock_tools") or [])
        blocked = GP_BLOCKED_TOOLS - unblock
        gp_tools = []
        for name in self.tools.list_tools():
            if name in blocked:
                continue
            tool = self.tools.get(name)
            if tool:
                gp_tools.append(tool)
        if unblock:
            logger.info(f"GP tools: unblocked {unblock & GP_BLOCKED_TOOLS} via loop_config")
        return gp_tools

    def _mark_active_nodes(self, node_ids: List[str], role: str):
        for nid in node_ids or []:
            node_id = str(nid or "").strip()
            if not node_id or node_id.startswith("MEM_CONV"):
                continue
            if node_id not in self.execution_active_nodes:
                self.execution_active_nodes.append(node_id)
            self.execution_active_node_roles.setdefault(node_id, set()).add(role)

    def _track_active_nodes_from_search(self, search_result: str):
        """从搜索结果中提取建议挂载的节点 ID 并追踪"""
        match = re.search(r"\[建议挂载\]\s*(.+)", search_result)
        if match:
            node_line = match.group(1).strip()
            if node_line == "无强推荐":
                return
            node_ids = [nid.strip() for nid in node_line.split(",") if nid.strip()]
            self._mark_active_nodes(node_ids, "tool_suggested")


    def _apply_knowledge_routing(self) -> Optional[str]:
        """
        知识路由层：每轮自动预加载相关知识到 GP 上下文。

        策略：
        1. 有游标且话题未漂移 → 确定性路由（沿游标节点 + 1-hop 导航）
        2. 无游标或话题漂移 → 向量搜索预加载（基于用户输入自动检索 + graph walk）

        GP 拿到的是预加载的精准知识图谱片段，不需要自己猜关键词搜索。
        """
        _sig_input = self.user_input
        if "[GENESIS_USER_REQUEST_START]" in _sig_input:
            _sig_input = _sig_input.split("[GENESIS_USER_REQUEST_START]", 1)[1]

        cursor = self._knowledge_cursor_in
        use_cursor = False
        self._knowledge_routing_preview = {
            "strategy": "none",
            "injected": False,
            "cursor_available": bool(cursor and cursor.get("active_node_ids")),
        }

        if cursor and cursor.get("active_node_ids"):
            # 话题漂移检测
            input_lower = _sig_input.lower()
            cursor_keywords = cursor.get("search_keywords", [])
            if cursor_keywords:
                hit = sum(1 for kw in cursor_keywords if kw.lower() in input_lower)
                overlap = hit / len(cursor_keywords)
            else:
                overlap = 0.0
            use_cursor = overlap >= 0.3
            self._knowledge_routing_preview.update({
                "cursor_overlap": round(overlap, 3),
                "used_cursor": use_cursor,
                "cursor_active_count": len(cursor.get("active_node_ids") or []),
                "cursor_keyword_count": len(cursor_keywords),
            })
            logger.info(f"Knowledge routing: cursor overlap={overlap:.2f}, use_cursor={use_cursor}")

        if use_cursor:
            self._knowledge_routing_preview["strategy"] = "cursor"
            return self._route_from_cursor(cursor)
        else:
            self._knowledge_routing_preview["strategy"] = "vector"
            return self._route_from_vector_search(_sig_input)

    def _route_from_cursor(self, cursor: Dict[str, Any]) -> Optional[str]:
        """确定性路由：沿游标节点 + 1-hop 邻居预加载"""
        node_ids = cursor["active_node_ids"][:8]
        routed_ids, surface_roles, surface_result = self._expand_route_surface(node_ids, context_budget=24)
        if not routed_ids:
            self._knowledge_routing_preview.update({"injected": False, "reason": "empty_cursor_surface"})
            return None
        self._knowledge_routing_preview.update({
            "injected": True,
            "seed_count": len(node_ids),
            "routed_count": len(routed_ids),
            "surface": self._summarize_surface_result(surface_result),
        })
        rendered = self._render_preloaded_nodes(
            routed_ids, header="[知识游标] 上轮活跃节点组装的当轮面（连续任务，沿边导航）：",
            surface_roles=surface_roles,
            surface_result=surface_result,
        )
        if rendered:
            self._mark_active_nodes([nid for nid in node_ids if nid in routed_ids], "routing_seed")
        return rendered

    def _route_from_vector_search(self, query_text: str) -> Optional[str]:
        """向量搜索路由：基于用户输入自动检索最相关的节点 + graph walk"""
        if not self.vault.vector_engine.is_ready:
            logger.debug("Knowledge routing: vector engine not ready, skip")
            self._knowledge_routing_preview.update({"injected": False, "reason": "vector_engine_not_ready"})
            return None

        # 向量粗排
        results = self.vault.vector_engine.search(query_text, top_k=10, threshold=0.45)
        if not results:
            logger.info("Knowledge routing: vector search returned 0 hits")
            self._knowledge_routing_preview.update({"injected": False, "reason": "vector_no_hits", "vector_hits": 0})
            return None

        node_ids = [r[0] for r in results]
        scores = {r[0]: r[1] for r in results}
        self._knowledge_routing_preview.update({"vector_hits": len(node_ids)})
        logger.info(f"Knowledge routing: vector search hit {len(node_ids)} nodes, top={scores.get(node_ids[0], 0):.3f}")
        routed_ids, surface_roles, surface_result = self._expand_route_surface(node_ids, context_budget=24)
        if not routed_ids:
            self._knowledge_routing_preview.update({"injected": False, "reason": "empty_vector_surface"})
            return None
        self._knowledge_routing_preview.update({
            "injected": True,
            "seed_count": len(node_ids),
            "routed_count": len(routed_ids),
            "surface": self._summarize_surface_result(surface_result),
        })
        rendered = self._render_preloaded_nodes(
            routed_ids, header="[知识预加载] 向量检索已命中相关节点并组装当轮面（无需为形式手动搜索）：",
            similarity_scores=scores,
            surface_roles=surface_roles,
            surface_result=surface_result,
        )
        if rendered:
            self._mark_active_nodes([nid for nid in node_ids if nid in routed_ids], "routing_seed")
        return rendered

    def _expand_route_surface(self, seed_ids: List[str], context_budget: int = 24) -> Tuple[List[str], Dict[str, str], Dict[str, Any]]:
        try:
            from genesis.v4.surface import SurfaceExpander
            excluded_ids = self.vault.get_excluded_ids(seed_ids) if hasattr(self.vault, "get_excluded_ids") else set()
            visible_seed_ids = [nid for nid in seed_ids if nid not in excluded_ids]
            if not visible_seed_ids:
                return [], {}, {}
            surface_result = SurfaceExpander(self.vault).expand_surface(visible_seed_ids, context_budget=context_budget)
            self._record_surface_potential_samples(surface_result, source="knowledge_routing")
            surface_nodes = surface_result.get("surface_nodes", []) if surface_result else []
            if not surface_nodes:
                return visible_seed_ids, {}, {}
            surface_ids = [nid for nid, _ in surface_nodes]
            routed_ids = list(dict.fromkeys(visible_seed_ids + surface_ids))
            surface_roles = {nid: role for nid, role in surface_nodes}
            logger.info(f"Knowledge routing: SurfaceExpander assembled {len(routed_ids)} nodes from {len(visible_seed_ids)} visible seeds")
            return routed_ids, surface_roles, surface_result
        except Exception as e:
            logger.debug(f"Knowledge routing surface expansion skipped: {e}")
            try:
                excluded_ids = self.vault.get_excluded_ids(seed_ids) if hasattr(self.vault, "get_excluded_ids") else set()
                return [nid for nid in seed_ids if nid not in excluded_ids], {}, {}
            except Exception:
                return [], {}, {}

    def _summarize_surface_result(self, surface_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not surface_result:
            return {}
        role_counts: Dict[str, int] = {}
        for _, role in surface_result.get("surface_nodes", []) or []:
            role_counts[str(role)] = role_counts.get(str(role), 0) + 1
        return {
            "fill": surface_result.get("fill_count", 0),
            "push": surface_result.get("push_count", 0),
            "co_presence": surface_result.get("co_presence_count", 0),
            "roles": role_counts,
            "potential_samples": len(surface_result.get("potential_samples", []) or []),
            "virtual_saturation": len(surface_result.get("virtual_saturation", []) or []),
        }

    def _active_role_for_surface_role(self, role: Any) -> Optional[str]:
        role_text = str(role or "").strip()
        if role_text == "基础":
            return "surface_basis"
        if role_text == "探索":
            return "surface_frontier"
        if role_text == "游离":
            return "surface_co_presence"
        return None

    def _record_surface_potential_samples(self, surface_result: Optional[Dict[str, Any]], source: str = "surface") -> int:
        try:
            samples = (surface_result or {}).get("potential_samples", [])
            if not samples or not hasattr(self.vault, "record_potential_samples"):
                return 0
            count = self.vault.record_potential_samples(
                samples,
                trace_id=getattr(self, "trace_id", None),
                round_seq=None,
                source=source,
            )
            self._surface_potential_sample_count += count
            return count
        except Exception as e:
            logger.debug(f"record surface potential samples skipped: {e}")
            return 0

    def _render_preloaded_nodes(self, node_ids: List[str], header: str,
                                 similarity_scores: Optional[Dict[str, float]] = None,
                                 surface_roles: Optional[Dict[str, str]] = None,
                                 surface_result: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """渲染预加载节点 + 1-hop 邻居为 GP 可读文本"""
        briefs = self.vault.get_node_briefs(node_ids)
        if not briefs:
            return None

        lines = [header]
        loaded_ids = []
        DEEP_EDGES = {"REQUIRES", "TRIGGERS", "RESOLVES"}

        # PLS: 用入线数判定拓扑角色，不泄露数字评分
        incoming_counts = self.vault.get_incoming_line_counts_batch(node_ids) if hasattr(self.vault, 'get_incoming_line_counts_batch') else {}
        try:
            basis_threshold = max(
                self.vault.get_incoming_count_percentile(75) if hasattr(self.vault, 'get_incoming_count_percentile') else 2,
                2,
            )
        except Exception:
            basis_threshold = 2

        for nid in node_ids:
            brief = briefs.get(nid)
            if not brief:
                continue
            title = brief.get("title", nid)
            ntype = brief.get("type", "?")
            inc = incoming_counts.get(nid, 0)
            role = (surface_roles or {}).get(nid) or ("基础" if inc >= basis_threshold else "探索")
            has_arena = (brief.get("usage_success_count", 0) or 0) or (brief.get("usage_fail_count", 0) or 0)
            arena_tag = " | 有实战" if has_arena else ""
            lines.append(f"  ● <{ntype}> {title} [{nid}] ({role}{arena_tag})")
            loaded_ids.append(nid)

            # 1-hop 邻居 + 强边 2-hop
            hop1_deep = []
            for direction in ["out", "in"]:
                neighbors = self.vault.get_related_nodes(nid, direction=direction)
                for nb in neighbors[:4]:
                    arrow = "→" if direction == "out" else "←"
                    lines.append(f"    {arrow} [{nb['relation']}] <{nb['type']}> {nb['title']} ({nb['node_id']})")
                    if nb['relation'] in DEEP_EDGES:
                        hop1_deep.append(nb['node_id'])
            # 强边 2-hop（限制 3 条）
            hop2_count = 0
            for h1id in hop1_deep:
                if hop2_count >= 3:
                    break
                for direction in ["out", "in"]:
                    for h2 in self.vault.get_related_nodes(h1id, direction=direction)[:2]:
                        if h2['node_id'] == nid or h2['relation'] not in DEEP_EDGES:
                            continue
                        lines.append(f"      (2-hop via {h1id}) → [{h2['relation']}] <{h2['type']}> {h2['title']} ({h2['node_id']})")
                        hop2_count += 1
                        if hop2_count >= 3:
                            break

        if not loaded_ids:
            return None

        for nid in loaded_ids:
            active_role = self._active_role_for_surface_role((surface_roles or {}).get(nid))
            if active_role:
                self._mark_active_nodes([nid], active_role)
        if surface_result:
            fill_count = surface_result.get("fill_count", 0)
            push_count = surface_result.get("push_count", 0)
            co_presence_count = surface_result.get("co_presence_count", 0)
            state_parts = []
            if fill_count:
                state_parts.append("有基础候选")
            if push_count:
                state_parts.append("有探索前沿")
            if co_presence_count:
                state_parts.append("存在共场游离点")
            lines.append(f"\n[面状态] 已经完成填充→推进→共场组装：{' | '.join(state_parts) if state_parts else '未形成稳定面'}。")
            if co_presence_count:
                lines.append("[共场] 游离点只是受控走神材料，用于触发“或许？”，不是必须处理的任务。")
            potential_samples = surface_result.get("potential_samples", [])
            if potential_samples:
                lines.append("[势] 以下只是当轮“或许？”样本，不是事实或任务：")
                for sample in potential_samples[:3]:
                    lines.append(f"  - {sample.get('title', '未命名势')}：{sample.get('detail', '')}")
            for area_hint, _ in surface_result.get("virtual_saturation", [])[:3]:
                lines.append(f"[饱和] {area_hint}：该区域路径重叠频繁，优先转向不饱和邻域。")
        lines.append(f"\n如需深入某个节点，用 get_knowledge_node_content 读取完整内容。")
        logger.info(f"Knowledge routing: pre-loaded {len(loaded_ids)} nodes + neighbors")
        return "\n".join(lines)

    def export_knowledge_cursor(self) -> Dict[str, Any]:
        """导出当前知识游标供下一轮使用"""
        if getattr(self, "_gp_reached_max_iterations", False):
            return {"active_node_ids": [], "search_keywords": [], "timestamp": time.time(), "cursor_suppressed": True}
        # 从搜索结果和工具调用中收集搜索关键词
        search_keywords = set()
        # 从用户输入中提取关键词
        _sig_input = self.user_input
        if "[GENESIS_USER_REQUEST_START]" in _sig_input:
            _sig_input = _sig_input.split("[GENESIS_USER_REQUEST_START]", 1)[1]
        for token in re.findall(r'[\w\u4e00-\u9fff]{2,}', _sig_input):
            search_keywords.add(token.lower())

        allowed_roles = {"tool_suggested", "tool_opened", "search_suggested", "opened", "basis_used"}
        eligible_ids = [
            nid for nid in self.execution_active_nodes
            if self.execution_active_node_roles.get(nid, set()) & allowed_roles
        ]
        return {
            "active_node_ids": list(dict.fromkeys(eligible_ids))[:12],
            "search_keywords": list(search_keywords)[:20],
            "timestamp": time.time(),
        }






    # ─── Lens methods provided by LensPhaseMixin ──────────────────────

    # ─── 蒸发机制已移除 ─────────────────────────────────────────────────
    # GP 需要完整的工具结果记忆来避免重复调用。
    # 上下文长度由 provider 的 context window 自然约束。

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
