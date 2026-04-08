"""
Genesis V4 - C-Phase Mixin (Reflector / Knowledge Extraction / Challenger)

从 V4Loop 中提取的 C-Phase 相关方法：
- _determine_c_phase_mode: 信号质量 → C-Phase 模式判断
- _classify_tool_result: 工具返回值客观成功/失败信号
- _compute_env_success: Op 工具调用客观成功率
- _run_c_phase_safe: 后台安全包装器
- _run_c_phase: C-Process 反思循环主体
- _extract_execution_signals: 确定性信号提取（阶段1，零 LLM）
- _run_discovery_recording: 受限 tool calling 记录 DISCOVERY（阶段2）
- _run_c_phase 通过 asyncio.gather 并发调用 ChallengerMixin._run_challenger_review

V4Loop 通过 Mixin 继承获得这些方法，无需改变调用方式。
"""

import re
import json
import hashlib
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
    - self._run_challenger_review (来自 ChallengerMixin，通过 MRO 解析)
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

        # ── Discovery Recording + Challenger Review（并发 LLM 调用）────
        # Discovery: 从结构化信号中分类+压缩观察（DISCOVERY 节点）
        # Challenger: 审查路径效率，产出 METHOD_REVIEW（方法效率知识）
        discovery_result = {"discoveries_recorded": 0, "c_tokens": 0}
        challenger_result = {"status": "skipped", "challenger_tokens": 0}
        if mode != "SKIP":
            results = await asyncio.gather(
                self._run_discovery_recording(g_final_response),
                self._run_challenger_review(g_final_response),
                return_exceptions=True,
            )
            if isinstance(results[0], Exception):
                logger.warning(f"Discovery recording failed (non-fatal): {results[0]}")
            else:
                discovery_result = results[0]
            if isinstance(results[1], Exception):
                logger.warning(f"Challenger review failed (non-fatal): {results[1]}")
            else:
                challenger_result = results[1]

            # Log discovery results
            disc_n = discovery_result.get("discoveries_recorded", 0)
            c_tokens = discovery_result.get("c_tokens", 0)
            if disc_n > 0:
                logger.info(f"Discovery Recording: {disc_n} discoveries (c_tokens={c_tokens})")
                for d in discovery_result.get("discoveries", []):
                    logger.info(f"  → [{d.get('category','?')}] {d.get('subject','?')}: {d.get('result','')[:60]}")
            else:
                logger.info(f"Discovery Recording: 0 discoveries (c_tokens={c_tokens}, reason={discovery_result.get('reason', 'none')})")

            # Log challenger results
            ch_status = challenger_result.get("status", "unknown")
            ch_tokens = challenger_result.get("challenger_tokens", 0)
            if ch_status == "suggestion":
                logger.info(f"Challenger: METHOD_REVIEW written → {challenger_result.get('node_id', '?')} (tokens={ch_tokens})")
            else:
                logger.info(f"Challenger: {ch_status} (tokens={ch_tokens})")

        # ── PATTERN 自动提升（确定性，零 LLM）──
        promotion_result = {"patterns_promoted": 0}
        if mode != "SKIP":
            try:
                promotion_result = self._try_promote_discoveries_to_pattern(
                    discoveries_this_session=discovery_result.get("discoveries_recorded", 0)
                )
                if promotion_result.get("patterns_promoted", 0) > 0:
                    logger.info(f"PATTERN promotion: {promotion_result['patterns_promoted']} patterns created")
            except Exception as e:
                logger.warning(f"PATTERN promotion failed (non-fatal): {e}")

        c_tokens_total = discovery_result.get("c_tokens", 0) + challenger_result.get("challenger_tokens", 0)
        self.c_messages = []
        logger.info(f"C-Process finished (Arena + Trace + Discovery + Challenger + Promotion). c_tokens={c_tokens_total}, discoveries={discovery_result.get('discoveries_recorded', 0)}, patterns={promotion_result.get('patterns_promoted', 0)}, challenger={challenger_result.get('status', 'n/a')}, total={self.metrics.total_tokens}")
        await self._safe_callback(step_callback, "c_phase_done", {
            "mode": mode, "c_tokens": c_tokens_total,
            "trace_pipeline": trace_pipeline_result,
            "discovery_recording": discovery_result,
            "pattern_promotion": promotion_result,
            "challenger_review": challenger_result,
        })

    # ─── Discovery Recording（阶段1: 信号提取 + 阶段2: 受限 tool calling）───

    def _extract_execution_signals(self, g_final_response: str) -> str:
        """阶段1：确定性信号提取，从执行数据中生成结构化候选列表。

        不用自然语言流水账，而是提取具体的、可分类的信号点。
        输出供 LLM 做分类+压缩（不做自由发挥）。
        """
        signals = []

        # 信号1: 工具失败（ERROR_PATTERN 候选）
        failed_tools = [o for o in self._op_tool_outcomes if not o["success"]]
        if failed_tools:
            tool_names = [o["tool"] for o in failed_tools]
            signals.append(f"SIGNAL[ERROR_PATTERN]: tools_failed={tool_names}")
            # 从 g_messages 中提取失败工具的错误信息
            for msg in self.g_messages:
                if (msg.role == MessageRole.TOOL and msg.name in tool_names
                        and msg.content and "Error" in str(msg.content)[:200]):
                    signals.append(f"  error_detail[{msg.name}]: {str(msg.content)[:150]}")

        # 信号2: 失败→成功序列（APPROACH 候选）
        if len(self._op_tool_outcomes) >= 2:
            for i in range(1, len(self._op_tool_outcomes)):
                prev, curr = self._op_tool_outcomes[i-1], self._op_tool_outcomes[i]
                if not prev["success"] and curr["success"]:
                    signals.append(
                        f"SIGNAL[APPROACH]: failed({prev['tool']}) → succeeded({curr['tool']})"
                    )

        # 信号3: 环境事实（ENV_FACT 候选）— 从工具输出中提取关键路径/配置
        env_facts = []
        for msg in self.g_messages:
            if msg.role == MessageRole.TOOL and msg.content and msg.name in ("shell", "read_file"):
                content_str = str(msg.content)[:500]
                # 检测配置/版本/路径信息
                if any(kw in content_str.lower() for kw in
                       ["version", "config", "port", "path", "installed", "running", "active",
                        "listening", "enabled", "disabled"]):
                    env_facts.append(f"  [{msg.name}] {content_str[:120]}")
        if env_facts:
            signals.append("SIGNAL[ENV_FACT]: environment_observations")
            signals.extend(env_facts[:5])

        # 信号4: 工具行为（TOOL_BEHAVIOR 候选）— 超时/重试/断路器
        tool_counts = {}
        for o in self._op_tool_outcomes:
            tool_counts[o["tool"]] = tool_counts.get(o["tool"], 0) + 1
        repeated = {t: c for t, c in tool_counts.items() if c >= 3}
        if repeated:
            signals.append(f"SIGNAL[TOOL_BEHAVIOR]: repeated_calls={repeated}")

        # 如果没有信号，返回空
        if not signals:
            return ""

        # 附加上下文（简短）
        header = f"TASK: {self.user_input[:200]}"
        env_ratio = self._compute_env_success()
        if env_ratio is not None:
            header += f" | success_rate={env_ratio:.0%}"
        header += f" | tool_calls={len(self._op_tool_outcomes)}"

        return header + "\n" + "\n".join(signals)

    async def _run_discovery_recording(self, g_final_response: str) -> Dict[str, Any]:
        """阶段2：LLM 通过 tool calling 记录 DISCOVERY（受限语言）。

        与旧 _run_knowledge_extraction 的本质区别：
          - 输入是结构化信号（非自由文本流水账）
          - 输出受 tool schema 约束（非自由 JSON）
          - LLM 做分类+压缩（非因果推理）
          - 无信号时跳过（不强迫 LLM 产出）
        """
        signals_text = self._extract_execution_signals(g_final_response)
        if not signals_text:
            return {"discoveries_recorded": 0, "c_tokens": 0, "reason": "no_signals"}

        # 构建 record_discovery 工具的 schema（约束 LLM 输出空间）
        from genesis.tools.node_tools import RecordDiscoveryTool
        discovery_tool = RecordDiscoveryTool()
        tool_schema = [discovery_tool.to_schema()]

        messages = [
            {"role": "system", "content": (
                "You are a signal classifier. You receive structured execution signals.\n"
                "For each signal worth recording, call record_discovery ONCE.\n"
                "Rules:\n"
                "- Only record genuinely NEW observations, not common knowledge\n"
                "- subject: dot notation, max 3 levels (e.g. nginx.port.conflict)\n"
                "- description: max 30 tokens, use → | + symbols for compression\n"
                "- If no signal is worth recording, do NOT call any tool\n"
                "- Max 5 discoveries per session"
            )},
            {"role": "user", "content": f"Classify these execution signals:\n\n{signals_text}"},
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
                logger.info(f"Discovery recording: LLM chose not to record (no tool calls). c_tokens={c_tokens}")
                return {"discoveries_recorded": 0, "c_tokens": c_tokens, "reason": "llm_no_calls"}

            # 执行每个 tool call（最多 5 个）
            recorded = []
            for tc in response.tool_calls[:5]:
                if tc.name != "record_discovery":
                    continue
                try:
                    result = await discovery_tool.execute(**tc.arguments)
                    recorded.append({
                        "subject": tc.arguments.get("subject", "?"),
                        "category": tc.arguments.get("category", "?"),
                        "result": str(result)[:100],
                    })
                except Exception as e:
                    logger.warning(f"Discovery recording failed for {tc.arguments}: {e}")

            return {
                "discoveries_recorded": len(recorded),
                "c_tokens": c_tokens,
                "discoveries": recorded,
            }

        except Exception as e:
            logger.warning(f"Discovery recording LLM call failed (non-fatal): {e}")
            return {"discoveries_recorded": 0, "c_tokens": 0, "error": str(e)}

    # ─── 阶段3: PATTERN 自动提升 ───

    PATTERN_PROMOTION_THRESHOLD = 3  # 同 subject 前缀 ≥3 个 DISCOVERY → 提升

    def _try_promote_discoveries_to_pattern(self, discoveries_this_session: int = 0) -> Dict[str, Any]:
        """确定性逻辑：同 subject 前缀累积 ≥3 个 DISCOVERY 时自动合并为 PATTERN。

        零 LLM，纯 SQL + Python。在 _run_c_phase 末尾调用。
        PATTERN 半衰期 180 天（DISCOVERY 90 天），置信度取子节点最大值 +0.1。
        短路：本轮未录入新 DISCOVERY 时跳过（避免每轮空跑 200 条查询）。
        """
        if discoveries_this_session <= 0:
            return {"patterns_promoted": 0, "reason": "no_new_discoveries"}
        vault = self.vault
        promoted = []

        try:
            rows = vault._conn.execute(  # 使用 self.vault 的连接，能看到本轮刚录入的 DISCOVERY
                """SELECT kn.node_id, nc.full_content, kn.confidence_score
                   FROM knowledge_nodes kn
                   JOIN node_contents nc ON kn.node_id = nc.node_id
                   WHERE kn.type = 'DISCOVERY'
                   ORDER BY kn.created_at DESC
                   LIMIT 200"""
            ).fetchall()

            if len(rows) < self.PATTERN_PROMOTION_THRESHOLD:
                return {"patterns_promoted": 0, "reason": "too_few_discoveries"}

            from collections import defaultdict
            subject_groups = defaultdict(list)
            for r in rows:
                try:
                    content = json.loads(r['full_content'])
                    subject = content.get('subject', '')
                    description = content.get('description', '')
                    parts = subject.split('.')
                    prefix = '.'.join(parts[:2]) if len(parts) >= 2 else subject
                    if prefix:
                        subject_groups[prefix].append({
                            'node_id': r['node_id'],
                            'subject': subject,
                            'description': description,
                            'confidence': float(r['confidence_score'] or 0.5),
                        })
                except (json.JSONDecodeError, TypeError):
                    continue

            existing_patterns = set()
            pat_rows = vault._conn.execute(
                "SELECT node_id FROM knowledge_nodes WHERE type = 'PATTERN'"
            ).fetchall()
            for pr in pat_rows:
                existing_patterns.add(pr['node_id'])

            for prefix, discoveries in subject_groups.items():
                if len(discoveries) < self.PATTERN_PROMOTION_THRESHOLD:
                    continue

                pattern_id = f"PAT_{hashlib.md5(prefix.encode()).hexdigest()[:8].upper()}"
                if pattern_id in existing_patterns:
                    vault.promote_node_confidence(pattern_id, boost=0.05, max_score=0.95)
                    logger.info(f"PATTERN [{pattern_id}] already exists, confidence boosted")
                    continue

                descriptions = [f"- {d['subject']}: {d['description']}" for d in discoveries[:10]]
                max_conf = max(d['confidence'] for d in discoveries)
                pattern_conf = min(max_conf + 0.1, 0.95)

                pattern_content = json.dumps({
                    "subject_prefix": prefix,
                    "observation_count": len(discoveries),
                    "observations": descriptions,
                }, ensure_ascii=False)

                vault.create_node(
                    node_id=pattern_id,
                    ntype="PATTERN",
                    title=f"[PATTERN] {prefix} ({len(discoveries)} observations)",
                    human_translation=f"{prefix}: consolidated from {len(discoveries)} discoveries",
                    tags=f"pattern,auto_promoted,{prefix.replace('.', ',')}",
                    full_content=pattern_content,
                    source="c_phase_promotion",
                    resolves=prefix,
                    metadata_signature={
                        "subject_prefix": prefix,
                        "promotion_source": "auto",
                        "observation_count": len(discoveries),
                    },
                    confidence_score=pattern_conf,
                    trust_tier="REFLECTION",
                )

                for d in discoveries:
                    try:
                        vault.add_edge(d['node_id'], pattern_id, "RELATED_TO", weight=0.8)
                    except Exception:
                        pass

                promoted.append({
                    "pattern_id": pattern_id,
                    "prefix": prefix,
                    "discovery_count": len(discoveries),
                    "confidence": pattern_conf,
                })
                logger.info(f"PATTERN promoted: [{pattern_id}] {prefix} from {len(discoveries)} discoveries (conf={pattern_conf:.2f})")

            return {"patterns_promoted": len(promoted), "patterns": promoted}

        except Exception as e:
            logger.warning(f"PATTERN promotion failed (non-fatal): {e}")
            return {"patterns_promoted": 0, "error": str(e)}
