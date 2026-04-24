"""
Genesis V4 - C-Phase Mixin (Gardener)

点线面架构下，C 是知识图谱的园丁：
- GP 面向现在：执行 + 记录（种树）
- C 面向过去：回顾 + 修图（园丁，只修图不种树）

确定性组件（零 LLM）：
- Knowledge Arena 反馈（W/L 互补信号）
- Persona 在线学习
- Trace Analysis Pipeline
- 消融触发（入线数≥5 → 隐藏节点）

LLM 组件（园丁模式）：
- Gardener: 审视 GP 工作，只修图不加节点
  矛盾 → CONTRADICTS 边（GP搜索可见）
  关联 → RELATED_TO 边（面BFS跨锥体连接）
  不创建 LESSON_C_ 节点（拓扑死点：入线数永远=0）

V4Loop 通过 Mixin 继承获得这些方法，无需改变调用方式。
"""

import re
import json

import asyncio
import logging
from typing import Any, Dict, Optional

from genesis.core.base import MessageRole

logger = logging.getLogger(__name__)


class CPhaseMixin:
    """C-Phase 方法集合。通过 Mixin 注入 V4Loop。

    依赖 V4Loop 的属性：
    - self.vault, self.provider, self.blackboard
    - self.g_messages, self.c_messages
    - self.execution_active_nodes, self.inferred_signature
    - self._op_tool_outcomes, self.metrics
    - self.user_input, self.trace_id
    - self._safe_callback, self._update_metrics
    - self._c_consecutive_errors, self._last_c_phase_mode
    - self.C_PHASE_MAX_ITER
    """

    def _determine_c_phase_mode(self) -> str:
        """信号质量 → C-Phase 模式: FULL / LIGHT / SKIP
        GP 模式下基于工具调用数量和活跃节点判断。"""
        # 统计 GP 执行的工具调用
        exec_tool_count = sum(
            1 for m in self.g_messages
            if m.role == MessageRole.TOOL and m.name
        )
        
        if exec_tool_count == 0:
            return "SKIP"

        high_value = False
        if exec_tool_count >= 3:
            high_value = True
        if len(self._op_tool_outcomes) >= 2:
            high_value = True
        if any(not o["success"] for o in self._op_tool_outcomes):
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
        if exec_tool_count >= 5:
            full_signals += 1
        if any(not o["success"] for o in self._op_tool_outcomes):
            full_signals += 1
        if self.blackboard and len(self.blackboard.search_voids) >= 2:
            full_signals += 1
        if len(self.execution_active_nodes) >= 3:
            full_signals += 1
        if full_signals >= 2:
            return "FULL"
        return "LIGHT"

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

    async def _run_c_phase_safe(self, step_callback: Any, mode: str = "FULL", g_final_response: str = ""):
        """后台安全包装器：捕获 C-Process 异常，防止后台任务静默崩溃"""
        try:
            await self._run_c_phase(step_callback, mode, g_final_response=g_final_response)
        except Exception as e:
            logger.error(f"C-Process background task failed: {e}", exc_info=True)

    async def _run_c_phase(self, step_callback: Any, mode: str = "FULL", g_final_response: str = ""):
        """运行 C-Process 反思循环，基于 Op 的执行轨迹。mode: FULL/LIGHT"""
        self._last_c_phase_mode = mode  # 供 get_phase_trace() 读取
        max_iter = self.C_PHASE_MAX_ITER.get(mode, 30)
        self._c_consecutive_errors = 0  # 每次 C-Phase 开始时重置，防止跨请求累积
        logger.info(f">>> Entering Phase 3: C-Process (Reflector) mode={mode}, max_iter={max_iter}")
        
        # 跨进程向量同步：拉取 Daemon/Scavenger 在 G/Op 期间新增的节点向量，
        # 确保 C 的 LESSON 去重能看到最新节点
        self.vault.sync_vector_matrix_incremental()
        
        # ── Knowledge Arena 反馈闭环（确定性，零 LLM）──────────────────
        # 信号来源：Op 工具调用的客观结果（exit code / Error 前缀），非 Op 自报 STATUS
        # 阈值：>= 0.7 = 成功, <= 0.3 = 失败, 中间 / 无信号 = 中性（只记 usage_count）
        unique_active_nodes = list(dict.fromkeys(self.execution_active_nodes))
        env_ratio = self._compute_env_success()
        if unique_active_nodes:
            self.vault.increment_usage(unique_active_nodes)
            if env_ratio is not None and env_ratio >= 0.7:
                self.vault.record_usage_outcome(unique_active_nodes, success=True)
                logger.info(f"Knowledge Arena: +boost for {len(unique_active_nodes)} nodes (env_ratio={env_ratio:.2f}, tools={len(self._op_tool_outcomes)})")
            elif env_ratio is not None and env_ratio <= 0.3:
                self.vault.record_usage_outcome(unique_active_nodes, success=False)
                logger.info(f"Knowledge Arena: -decay for {len(unique_active_nodes)} nodes (env_ratio={env_ratio:.2f}, tools={len(self._op_tool_outcomes)})")
            else:
                logger.info(f"Knowledge Arena: NEUTRAL for {len(unique_active_nodes)} nodes (env_ratio={env_ratio}, tools={len(self._op_tool_outcomes)})")

        # ── Persona 在线学习（同样使用环境信号）────────────────────────
        if self.blackboard and self.blackboard.entries:
            from genesis.v4.blackboard import Blackboard
            contributing_personas = list({e.persona for e in self.blackboard.entries})
            task_success = env_ratio is not None and env_ratio >= 0.7
            raw_atk = self.inferred_signature.get("task_kind") or ""
            arena_task_kind = (raw_atk[0] if isinstance(raw_atk, list) and raw_atk else str(raw_atk)).lower()
            Blackboard.record_persona_outcome(contributing_personas, success=task_success, task_kind=arena_task_kind)
            logger.info(f"Persona Arena: {'WIN' if task_success else 'LOSS/NEUTRAL'} for {contributing_personas} (env_ratio={env_ratio}, task_kind={arena_task_kind})")

        # ── Trace Analysis Pipeline（确定性，零 LLM）─────────────────
        # 替代 LLM 反思循环：从 spans 表确定性提取结构化实体
        trace_pipeline_result = None
        if getattr(self, 'trace_id', None):
            try:
                from genesis.v4.trace_pipeline.runner import process_current_trace
                trace_pipeline_result = process_current_trace(self.trace_id)
                if trace_pipeline_result.get("status") == "ok":
                    logger.info(
                        f"Trace Pipeline: {trace_pipeline_result['entity_count']} entities "
                        f"({trace_pipeline_result['new_canonical']} new), "
                        f"types={trace_pipeline_result.get('by_type', {})}"
                    )
            except Exception as e:
                logger.warning(f"Trace pipeline failed (non-fatal): {e}")

        # ── 真理区分消融触发（确定性，零 LLM）──────────────────────
        # 检查是否有节点满足消融条件（入线数≥5），自动标记为消融观察
        try:
            ablation_candidates = self.vault.check_ablation_candidates(min_incoming=5)
            if ablation_candidates:
                for cid, incoming, title in ablation_candidates[:3]:
                    self.vault.activate_ablation(cid, baseline_env_ratio=env_ratio)
                    logger.info(f"Ablation triggered: [{cid}] '{title}' (incoming={incoming}, baseline_env={env_ratio})")
        except Exception as e:
            logger.debug(f"Ablation check skipped (non-fatal): {e}")

        # ── 真理区分消融评估（确定性，零 LLM）──────────────────────
        # 检查已处于消融观察的节点，比较当前 env_ratio 与 baseline
        try:
            ablation_observing = self.vault.get_ablation_observing_nodes(min_duration_seconds=300)
            for nid, title, baseline in ablation_observing[:5]:
                result = self.vault.deactivate_ablation(nid, current_env_ratio=env_ratio)
                logger.info(f"Ablation evaluated: [{nid}] '{title}' → {result} (baseline={baseline}, current={env_ratio})")
        except Exception as e:
            logger.debug(f"Ablation evaluation skipped (non-fatal): {e}")

        # ── Gardener: 园丁模式（单次 LLM 调用）─────────────────────
        # C 只修图不种树：矛盾→CONTRADICTS边，关联→RELATED_TO边
        # 不创建 LESSON_C_ 节点（入线数永远=0 = 拓扑死点）
        reflection_result = {"edges_added": 0, "metadata_expanded": 0, "c_tokens": 0}
        if mode != "SKIP":
            try:
                reflection_result = await self._run_reflection(g_final_response)
            except Exception as e:
                logger.warning(f"Reflection failed (non-fatal): {e}", exc_info=True)

            r_edges = reflection_result.get("edges_added", 0)
            r_tokens = reflection_result.get("c_tokens", 0)
            if r_edges > 0:
                logger.info(f"Reflection: {r_edges} edges added (c_tokens={r_tokens})")
                for edge in reflection_result.get("edges", []):
                    logger.info(f"  → {edge.get('source_id','?')} --[{edge.get('relation','?')}]--> {edge.get('target_id','?')}")
            else:
                logger.info(f"Reflection: PASS (c_tokens={r_tokens}, reason={reflection_result.get('reason', 'none')})")

        c_tokens_total = reflection_result.get("c_tokens", 0)
        self.c_messages = []
        logger.info(f"C-Process finished (Arena + Trace + Gardener). c_tokens={c_tokens_total}, edges={reflection_result.get('edges_added', 0)}, total={self.metrics.total_tokens}")
        await self._safe_callback(step_callback, "c_phase_done", {
            "mode": mode, "c_tokens": c_tokens_total,
            "trace_pipeline": trace_pipeline_result,
            "reflection": reflection_result,
        })

    # ─── Reflector: 内容级反思 ───────────────────────────────────────

    def _build_reflection_input(self, g_final_response: str) -> str:
        """构建 C-Gardener 的输入：GP 的完整执行上下文。

        设计原则：C 应该能看到 GP 看到的一切核心内容 + 活跃节点ID，
        以便加边（CONTRADICTS/RELATED_TO）时能引用正确的 source_id/target_id。
        """
        parts = []

        # 1. 任务
        parts.append(f"[任务]\n{self.user_input}")

        # 2. GP 的最终回复（完整——这是核心）
        if g_final_response:
            parts.append(f"[GP 最终回复]\n{g_final_response}")

        # 3. GP 的推理过程——提取有实质内容的 assistant 消息
        reasoning_steps = []
        for msg in self.g_messages:
            if msg.role == MessageRole.ASSISTANT and msg.content:
                text = msg.content.strip()
                if len(text) > 100:  # 跳过空转或纯 tool_calls 的短回复
                    reasoning_steps.append(text[:600])
        if reasoning_steps:
            # 取最后 2 个关键推理步骤（更早的已被最终回复覆盖）
            recent = reasoning_steps[-2:]
            parts.append("[GP 推理过程（最近 2 步）]\n" + "\n---\n".join(recent))

        # 4. GP 本轮写入的知识——从 tool_calls 提取 arguments（比 result 更有信息量）
        gp_knowledge_writes = []
        for msg in self.g_messages:
            if msg.role == MessageRole.ASSISTANT and hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in (msg.tool_calls or []):
                    tc_dict = tc if isinstance(tc, dict) else getattr(tc, '__dict__', {})
                    tc_name = tc_dict.get('name', '')
                    tc_args = tc_dict.get('arguments', {})
                    if isinstance(tc_args, str):
                        try:
                            tc_args = json.loads(tc_args)
                        except (json.JSONDecodeError, TypeError):
                            tc_args = {}
                    if tc_name in ('record_lesson_node', 'record_context_node'):
                        nid = tc_args.get('node_id', '')
                        title = tc_args.get('title', '')
                        reason = tc_args.get('because_reason', '')
                        resolves = tc_args.get('resolves', '')
                        gp_knowledge_writes.append(
                            f"  [{tc_name}] {nid}: {title}"
                            + (f" | 因为: {reason[:150]}" if reason else "")
                            + (f" | 解决: {resolves[:80]}" if resolves else "")
                        )
        if gp_knowledge_writes:
            parts.append("[GP 本轮写入的知识]\n" + "\n".join(gp_knowledge_writes))

        # 5. 关键工具交互（内容摘要，非成功/失败计数）
        tool_interactions = []
        for msg in self.g_messages:
            if msg.role == MessageRole.TOOL and msg.content:
                content_str = str(msg.content)
                # 跳过知识工具的结果（已在上面单独提取）
                if msg.name in ('record_lesson_node', 'record_context_node', 'record_discovery'):
                    continue
                if msg.name == "shell":
                    tool_interactions.append(f"  [shell] {content_str[:250]}")
                elif msg.name == "read_file":
                    tool_interactions.append(f"  [read_file] {content_str[:200]}")
                elif msg.name == "search_knowledge_nodes":
                    tool_interactions.append(f"  [search_kb] {content_str[:250]}")
                elif msg.name in ("grep_files", "web_search"):
                    tool_interactions.append(f"  [{msg.name}] {content_str[:200]}")
        if tool_interactions:
            # 最多取 8 条关键交互
            parts.append("[关键工具交互]\n" + "\n".join(tool_interactions[-8:]))

        # 6. Vault 中相关的已有知识（含内容，用于矛盾/扩展检测）
        vault_related = self._query_vault_related_knowledge(g_final_response)
        if vault_related:
            parts.append(f"[Vault 已有相关知识]\n{vault_related}")

        # 7. GP 本轮活跃节点（C-Gardener 加边需要 node_id）
        if self.execution_active_nodes:
            unique_active = list(dict.fromkeys(self.execution_active_nodes))[:12]
            active_briefs = self.vault.batch_get_titles(unique_active) if hasattr(self.vault, 'batch_get_titles') else {}
            active_lines = []
            for nid in unique_active:
                title = active_briefs.get(nid, '?')
                active_lines.append(f"  {nid}: {title}")
            parts.append("[GP 本轮引用的活跃节点 — 可作为 create_node_edge 的 source_id/target_id]\n" + "\n".join(active_lines))

        # 8. Multi-G 发现的知识空洞（已知的未知）
        if self.blackboard and self.blackboard.search_voids:
            void_lines = [f"  - {v}" for v in self.blackboard.search_voids[:5]]
            parts.append("[知识空洞 — Multi-G 搜索未命中的方向]\n" + "\n".join(void_lines))

        # 9. 任务签名（领域上下文）
        if self.inferred_signature:
            sig_text = self.vault.signature.render(self.inferred_signature)
            if sig_text:
                parts.append(f"[任务签名]\n{sig_text}")

        # 10. 跨轮行为观测（GP 自身无法察觉的行为模式）
        cross_obs = self._build_cross_round_observations()
        if cross_obs:
            parts.append(f"[跨轮行为观测 — GP 自身无法察觉的模式]\n{cross_obs}")

        return "\n\n".join(parts)

    def _query_vault_related_knowledge(self, g_final_response: str) -> str:
        """查询 vault 中与 GP 本轮工作相关的已有知识（含内容），供矛盾/扩展检测。

        与 Lens 的 _prefetch_shared_knowledge 对称：
        不只给标题，还给内容，C 才能判断矛盾/扩展/重复。
        """
        if not g_final_response or not self.vault.vector_engine.is_ready:
            return ""

        try:
            query = g_final_response[:500]
            results = self.vault.vector_engine.search(query, top_k=5, threshold=0.5)
            if not results:
                return ""

            node_ids = [nid for nid, _ in results]
            briefs = self.vault.get_node_briefs(node_ids) if hasattr(self.vault, 'get_node_briefs') else {}
            contents = self.vault.get_multiple_contents(node_ids) if node_ids else {}

            lines = []
            for nid, score in results[:5]:
                brief = briefs.get(nid, {})
                ntype = brief.get('type', '?')
                title = brief.get('title', '?')[:80]
                lines.append(f"  [{ntype}] {nid}: {title} (sim={score:.2f})")
                # 附加内容摘要（C 需要看到内容才能判断矛盾）
                content = contents.get(nid, "")
                if content:
                    lines.append(f"    内容: {str(content)[:300]}")

            return "\n".join(lines)
        except Exception as e:
            logger.debug(f"Vault related query failed (non-fatal): {e}")
            return ""

    def _build_cross_round_observations(self) -> str:
        """Format cross-round behavioral observations from loop_config.
        These are objective patterns GP cannot see about its own behavior.
        Only uses OUTCOME signals — activity signals like progress_class
        are inflated by probe writing and mislead C.
        """
        obs = getattr(self, 'loop_config', {}).get("cross_round_observations")
        if not obs:
            return ""

        lines = []
        total = obs.get("total_rounds", 0)
        if total:
            lines.append(f"  总轮次: {total}")

        # Write target distribution + source write ratio (outcome signal)
        wt = obs.get("write_targets")
        total_writes = sum(wt.values()) if wt else 0
        if wt:
            parts = [f"{k}={v}" for k, v in sorted(wt.items(), key=lambda x: -x[1])]
            lines.append(f"  GP 写入目标分布 ({total_writes}个文件): {', '.join(parts)}")
        sr = obs.get("source_write_ratio", 0)
        if sr is not None:
            lines.append(f"  源文件写入占比: {sr:.0%}")
            if sr < 0.2 and total_writes > 5:
                lines.append(f"  ⚠ GP 几乎不修改 genesis/ 源文件，只写 tests/ 和 scratch/")

        # Auto-apply outcome (now records both success and failure)
        attempts = obs.get("auto_apply_attempts", 0)
        successes = obs.get("auto_apply_successes", 0)
        blocked = obs.get("auto_apply_blocked_reasons", [])
        if attempts > 0:
            lines.append(f"  auto-apply 历史: {successes}/{attempts} 成功")
            if blocked:
                lines.append(f"  ⚠ auto-apply 失败原因: {'; '.join(blocked[-3:])}")
        elif total >= 5:
            lines.append(f"  auto-apply: 尚未触发（冷却未满）")

        # KB change rate (outcome signal — actual vault mutations)
        kcr = obs.get("kb_change_rate")
        if kcr:
            lines.append(f"  知识库变更率 (近{obs.get('window_size', '?')}轮): {kcr}")

        # LESSON count (NOT titles — titles create echo chamber)
        lt = obs.get("lesson_total_in_window", 0)
        lr = obs.get("lesson_rounds_in_window", 0)
        ws = obs.get("window_size", 0)
        if ws > 0:
            lines.append(f"  LESSON 产出: {lt}条 / {lr}轮有产出 / {ws}轮窗口")

        # Sandbox file stability (outcome signal — are GP's changes converging?)
        ss = obs.get("sandbox_stability")
        if ss:
            total_files = sum(ss.values())
            if total_files > 0:
                stable_pct = (ss.get("stable_3_plus", 0)) / total_files
                lines.append(f"  沙箱文件稳定性: stable_0={ss.get('stable_0',0)} | stable_1-2={ss.get('stable_1_2',0)} | stable_3+={ss.get('stable_3_plus',0)} / {total_files}文件")
                if stable_pct < 0.05 and total_files > 10:
                    lines.append(f"  ⚠ 沙箱文件几乎无稳定（stable_3+≈0%），GP 每轮都在改文件")

        # Error rounds
        er = obs.get("error_rounds_in_window", 0)
        if er > 0:
            lines.append(f"  错误轮次: {er}/{obs.get('window_size', '?')}")

        return "\n".join(lines) if lines else ""

    async def _run_reflection(self, g_final_response: str) -> Dict[str, Any]:
        """C 的核心：园丁模式——只修图，不种树。

        点线面架构下，C 不创建新节点（LESSON_C_ 是拓扑死点：入线数永远=0）。
        C 只做三件事：
        1. 矛盾检测 → 加 CONTRADICTS 边（旧节点被标记，GP搜索可见）
        2. 关联发现 → 加 RELATED_TO 边（面BFS跨锥体连接）
        3. 适用范围扩展 → 扩展 metadata_signature（提升搜索命中率）

        全新知识的记录是 GP 的职责，C 不补作业。
        """
        reflection_input = self._build_reflection_input(g_final_response)
        if not reflection_input or len(reflection_input) < 200:
            return {"edges_added": 0, "metadata_expanded": 0, "c_tokens": 0, "reason": "insufficient_input"}

        # 园丁工具：add_edge（加边）——使用 C-Phase 的 vault 实例
        from genesis.tools.node_tools import CreateNodeEdgeTool
        edge_tool = CreateNodeEdgeTool()
        edge_tool.vault = self.vault  # 必须用 C-Phase 的 vault，不能让工具自带新实例
        tool_schema = [edge_tool.to_schema()]

        system_prompt = (
            "你是知识图谱的园丁。你刚才观察了 GP 的完整执行过程。\n\n"
            "你的职责不是记录新知识（那是 GP 的事），而是维护知识图的健康：\n\n"
            "1. **矛盾检测**：GP 的发现跟 Vault 已有知识矛盾吗？\n"
            "   如果矛盾，用 create_node_edge 加 CONTRADICTS 边：\n"
            "   source_id=GP新节点, target_id=被矛盾的旧节点, relation=CONTRADICTS\n\n"
            "2. **关联发现**：两个独立节点其实是同一问题的不同侧面吗？\n"
            "   如果是，用 create_node_edge 加 RELATED_TO 边：\n"
            "   让面BFS能跨锥体连接，丰富图结构\n\n"
            "3. **适用范围扩展**：某条 LESSON 的 metadata_signature 太窄了吗？\n"
            "   例如标记了 language=go 但其实也适用于 python，\n"
            "   暂时跳过（需要单独工具，当前MVP只做边）\n\n"
            "规则：\n"
            "- 如果 GP 已经标记了 contradicts，不要重复加边\n"
            "- 只加有充分证据的边，不要猜测性关联\n"
            "- 如果没有发现矛盾或关联，不调用任何工具（PASS）\n"
            "- 最多加 2 条边\n"
            "- 不要创建新节点，只加边"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": reflection_input},
        ]

        try:
            response = await self.provider.chat(
                messages=messages,
                tools=tool_schema,
                stream=False,
                _trace_id=getattr(self, 'trace_id', None),
                _trace_phase="C",
            )
            self._update_metrics(response, phase="C")
            c_tokens = getattr(response, 'total_tokens', 0)

            if not response.tool_calls:
                return {"edges_added": 0, "metadata_expanded": 0, "c_tokens": c_tokens, "reason": "pass"}

            edges_added = []
            for tc in response.tool_calls[:2]:
                if tc.name != "create_node_edge":
                    continue
                try:
                    args = dict(tc.arguments)
                    source_id = args.get("source_id", "")
                    target_id = args.get("target_id", "")
                    relation = args.get("relation", "")
                    if not all([source_id, target_id, relation]):
                        continue
                    # 只允许 CONTRADICTS 和 RELATED_TO
                    if relation not in ("CONTRADICTS", "RELATED_TO"):
                        relation = "RELATED_TO"  # 降级为关联
                    result = await edge_tool.execute(
                        source_id=source_id,
                        target_id=target_id,
                        relation=relation,
                        weight=args.get("weight", 1.0),
                    )
                    edges_added.append({
                        "source_id": source_id,
                        "target_id": target_id,
                        "relation": relation,
                        "result": str(result)[:100],
                    })
                    logger.info(f"C-Gardener: {source_id} --[{relation}]--> {target_id}")
                except Exception as e:
                    logger.warning(f"Reflection edge creation failed: {e}")

            return {
                "edges_added": len(edges_added),
                "metadata_expanded": 0,
                "c_tokens": c_tokens,
                "edges": edges_added,
            }

        except Exception as e:
            logger.warning(f"Reflection LLM call failed (non-fatal): {e}")
            return {"edges_added": 0, "metadata_expanded": 0, "c_tokens": 0, "error": str(e)}

