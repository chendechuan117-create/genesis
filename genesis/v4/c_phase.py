"""
Genesis V4 - C-Phase Mixin (Reflector)

C 与 GP 等值但方向相反：
- GP 面向现在：执行 + 记录（错题本）
- C 面向过去：回顾 + 提炼（自我反思）

确定性组件（零 LLM）：
- Knowledge Arena 反馈
- Persona 在线学习
- Trace Analysis Pipeline
- PATTERN 自动提升

LLM 组件：
- Reflector: 内容级反思，审视 GP 工作的实际内容（非工具效率）
  输入：GP 的完整推理链 + 工具输出 + 写入的知识 + vault 已有相关知识
  输出：补建边（create_node_edge）+ 补深层线（record_line, source='C'）

V4Loop 通过 Mixin 继承获得这些方法，无需改变调用方式。
"""

import os
import re
import json
import hashlib
import asyncio
import logging
from typing import Any, Dict, Optional

from genesis.core.base import MessageRole

logger = logging.getLogger(__name__)


def _check_cgroup_memory_pressure(headroom_mb: int = 384) -> bool:
    """同步检查 cgroup 内存压力。不依赖 asyncio，在事件循环冻结前可调用。

    当 memory.current 接近 memory.high 时返回 True。
    headroom_mb: 距离 high 阈值的安全余量（MB），默认 384MB（约 12% of 2.8GB high）。
    """
    try:
        cgroup_path = f"/proc/self/cgroup"
        with open(cgroup_path) as f:
            for line in f:
                parts = line.strip().split(":")
                if len(parts) >= 3 and "yogg" in parts[2]:
                    slice_name = parts[2].lstrip("/")
                    base = f"/sys/fs/cgroup/{slice_name}"
                    current_s = (base + "/memory.current")
                    high_s = (base + "/memory.high")
                    try:
                        with open(current_s) as cf:
                            current = int(cf.read().strip())
                        with open(high_s) as hf:
                            high_val = int(hf.read().strip())
                    except (FileNotFoundError, ValueError):
                        return False
                    threshold = high_val - headroom_mb * 1024 * 1024
                    if current >= threshold:
                        logger.warning(
                            f"C-Phase memory pressure: current={current // 1048576}MB, "
                            f"high={high_val // 1048576}MB, headroom={(high_val - current) // 1048576}MB < {headroom_mb}MB"
                        )
                        return True
                    return False
        # No yogg cgroup found — check /proc/self/status VmRSS as fallback
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    rss_kb = int(line.split()[1])
                    rss_mb = rss_kb // 1024
                    # Hard limit: if RSS > 2.4GB on 8GB system, skip
                    if rss_mb > 2400:
                        logger.warning(f"C-Phase memory pressure (RSS fallback): {rss_mb}MB > 2400MB")
                        return True
        return False
    except Exception:
        return False


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

        # ── Reflector: 内容级反思（单次 LLM 调用）─────────────────────
        # V2: C 不再创建点，改为审核+补全（补建边 + 补深层线）
        reflection_result = {"supplements": 0, "c_tokens": 0}
        if mode != "SKIP":
            # 同步内存检查：cgroup memory.high 节流会冻结 asyncio 事件循环，
            # 导致 wall_clock_timeout 和 memory guard 全部失效（根因：D 状态卡死）
            if _check_cgroup_memory_pressure():
                logger.warning("C-Phase Reflection SKIPPED: cgroup memory near throttle threshold. "
                               "Skipping LLM call to prevent event loop freeze.")
                reflection_result = {"supplements": 0, "c_tokens": 0, "reason": "memory_pressure_skip"}
            else:
                try:
                    reflection_result = await self._run_reflection(g_final_response)
                except Exception as e:
                    logger.warning(f"Reflection failed (non-fatal): {e}", exc_info=True)

            r_n = reflection_result.get("supplements", 0)
            r_tokens = reflection_result.get("c_tokens", 0)
            if r_n > 0:
                logger.info(f"Reflection: {r_n} supplements (c_tokens={r_tokens})")
                for sup in reflection_result.get("details", []):
                    logger.info(f"  → {sup.get('type', '?')}: {str(sup)[:80]}")
            else:
                logger.info(f"Reflection: PASS (c_tokens={r_tokens}, reason={reflection_result.get('reason', 'none')})")

        c_tokens_total = reflection_result.get("c_tokens", 0)
        self.c_messages = []
        logger.info(f"C-Process finished (Arena + Trace + Reflection). c_tokens={c_tokens_total}, supplements={reflection_result.get('supplements', 0)}, total={self.metrics.total_tokens}")
        await self._safe_callback(step_callback, "c_phase_done", {
            "mode": mode, "c_tokens": c_tokens_total,
            "trace_pipeline": trace_pipeline_result,
            "reflection": reflection_result,
        })

    # ─── Reflector: 内容级反思 ───────────────────────────────────────

    def _build_reflection_input(self, g_final_response: str) -> str:
        """构建 C 的反思输入：GP 的完整执行上下文（内容级，非工具级）。

        设计原则：C 应该能看到 GP 看到的一切核心内容，
        但以回顾视角审视，而非重复执行。
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
                    if tc_name in ('record_lesson_node', 'record_context_node', 'record_point', 'record_context_point'):
                        title = tc_args.get('title', '')
                        reason = tc_args.get('because_reason', '') or tc_args.get('content', '')[:150]
                        resolves = tc_args.get('resolves', '')
                        gp_knowledge_writes.append(
                            f"  [{tc_name}] {title}"
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
                if msg.name in ('record_lesson_node', 'record_context_node', 'record_point', 'record_context_point', 'record_discovery'):
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

        # 7. Multi-G 发现的知识空洞（已知的未知）
        if self.blackboard and self.blackboard.search_voids:
            void_lines = [f"  - {v}" for v in self.blackboard.search_voids[:5]]
            parts.append("[知识空洞 — Multi-G 搜索未命中的方向]\n" + "\n".join(void_lines))

        # 8. 任务签名（领域上下文）
        if self.inferred_signature:
            sig_text = self.vault.signature.render(self.inferred_signature)
            if sig_text:
                parts.append(f"[任务签名]\n{sig_text}")

        # 8.5 基础盘感知：当前领域的锚点和救生索拓扑
        density_info = self._query_component_density()
        if density_info:
            parts.append(f"[基础盘 — 当前领域的锚点和救生索]\n{density_info}")

        # 9. 跨轮行为观测（GP 自身无法察觉的行为模式）
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

    def _query_component_density(self) -> str:
        """查询当前任务相关的基础盘（面），供 C-Phase 密度感知。
        面是拓扑描述——枢纽点、覆盖情况、重合点，不是评分。
        防原地踏步：让 C 知道当前领域已有哪些锚点。"""
        try:
            # 从当前任务的 component 找种子节点
            current_comp = (self.inferred_signature or {}).get("component")
            if not current_comp:
                return ""
            
            # 找该 component 最近的 LESSON 作为种子
            seed_rows = self.vault._conn.execute("""
                SELECT kn.node_id FROM knowledge_nodes kn
                WHERE json_extract(kn.metadata_signature, '$.component') = ?
                AND kn.type = 'LESSON'
                ORDER BY kn.updated_at DESC LIMIT 5
            """, (current_comp,)).fetchall()
            
            if not seed_rows:
                return f"  {current_comp}: 0个锚点，未探索领域"
            
            seed_ids = [r[0] for r in seed_rows]
            landscape = self.vault.build_landscape(seed_node_ids=seed_ids)
            
            if not landscape:
                # 没有ANCHORED边时的降级输出
                count = len(seed_rows)
                return f"  {current_comp}: {count}个锚点（无救生索连线）"
            
            return f"  当前领域: {current_comp}\n{landscape}"
        except Exception as e:
            logger.debug(f"Landscape query failed (non-fatal): {e}")
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

        # Sandbox outcome rate (ground truth from diff-status snapshots)
        or_ratio = obs.get("outcome_ratio", 0)
        or_rounds = obs.get("outcome_rounds_in_window", 0)
        window = obs.get("window_size", 0)
        if window > 0:
            lines.append(f"  沙箱产出率: {or_rounds}/{window} 轮产生diff变化 ({or_ratio:.0%})")
            if or_ratio < 0.2 and window >= 5:
                lines.append(f"  ⚠ GP 连续多轮未产生沙箱代码变化 — 可能在纯分析循环")

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
        """C 的核心：内容级反思。

        与 GP 等值但方向相反：
        - GP 面向现在，执行 + 记录（错题本）
        - C 面向过去，回顾 + 提炼（自我反思）

        C 看到 GP 的完整执行上下文（推理链、工具输出、写入的知识），
        审视内容本身而非工具使用效率。
        """
        reflection_input = self._build_reflection_input(g_final_response)
        if not reflection_input or len(reflection_input) < 200:
            return {"supplements": 0, "c_tokens": 0, "reason": "insufficient_input"}

        # V2: C 不再创建点，改为审核+补全（补建边 + 补深层线）
        from genesis.tools.node_tools import CreateNodeEdgeTool, RecordLineTool
        edge_tool = CreateNodeEdgeTool()
        line_tool = RecordLineTool()
        tool_schema = [edge_tool.to_schema(), line_tool.to_schema()]

        # 收集本轮 GP 创建的新点
        gp_new_points = []
        for msg in self.g_messages:
            if msg.role == MessageRole.TOOL and msg.name == "record_point":
                content_str = str(msg.content) if msg.content else ""
                if "写入成功" in content_str:
                    import re
                    m = re.search(r'\[(P_\w+)\]', content_str)
                    if m:
                        gp_new_points.append(m.group(1))

        gp_points_info = ""
        if gp_new_points:
            gp_points_info = f"\n\n本轮 GP 创建的新点: {gp_new_points}"

        system_prompt = (
            "你是回顾者。你刚才观察了 GP 的完整执行过程。\n\n"
            "V2 规则：你不再创建新知识节点（GP 已经用 record_point 实时记录了），"
            "你的任务是**补全**——补建边、补深层线、审核质量。\n\n"
            "具体任务：\n"
            "1. **补建边**：GP 的 record_point 可能只带了 resolves，"
            "但从执行轨迹中你能发现更多关系（REQUIRES/TRIGGERS/CONTRADICTS）。"
            "用 create_node_edge 补建。\n"
            "2. **补深层线**：GP 连了浅层因果（'这个有用因为X'），"
            "你能连深层（'为什么X成立'）。用 record_line 补线。\n"
            "3. **审核**：如果 GP 写了两个高度相似的点，"
            "用 create_node_edge 建立 RELATED_TO 边标记关联。\n\n"
            "规则：\n"
            "- 如果 GP 的工作已经足够完整，不需要补全，不调用任何工具\n"
            "- 最多 5 条补全操作\n"
            "- record_line 的 to_id 必须是知识库中实际存在的节点ID\n"
            "- create_node_edge 的 source_id/target_id 必须是实际存在的节点ID\n"
            "- 注意基础盘：如果已有大量锚点和枢纽，补全必须有实质增量"
        )

        messages = [
            {"role": "system", "content": system_prompt + gp_points_info},
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
                return {"supplements": 0, "c_tokens": c_tokens, "reason": "pass"}

            supplements = []
            for tc in response.tool_calls[:5]:  # 最多 5 条补全
                try:
                    args = dict(tc.arguments)
                    if tc.name == "create_node_edge":
                        result = await edge_tool.execute(**args)
                        supplements.append({"type": "edge", "result": str(result)[:100]})
                    elif tc.name == "record_line":
                        # C-Phase 的线标记 source='C'
                        # record_line schema: to_id + why (no from_id)
                        from_id = gp_new_points[0] if gp_new_points else ""
                        lid = self.vault.add_reasoning_line(
                            new_point_id=from_id,
                            basis_point_id=args.get("to_id", ""),
                            reasoning=args.get("why", ""),
                            source='C',
                        )
                        supplements.append({"type": "line", "line_id": lid})
                except Exception as e:
                    logger.warning(f"C-Phase supplement failed: {e}")

            return {
                "supplements": len(supplements),
                "c_tokens": c_tokens,
                "details": supplements,
            }

        except Exception as e:
            logger.warning(f"Reflection LLM call failed (non-fatal): {e}")
            return {"supplements": 0, "c_tokens": 0, "error": str(e)}
