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
  输出：GP 遗漏的深层洞察（LESSON 节点，通过 record_lesson_node）

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
        # C 与 GP 等值但方向相反：GP 记录现在，C 回顾过去
        # 输入：GP 的完整推理链 + 工具输出 + 写入的知识 + vault 已有相关知识
        # 输出：GP 遗漏的深层洞察（LESSON 节点）
        reflection_result = {"lessons_recorded": 0, "c_tokens": 0}
        if mode != "SKIP":
            try:
                reflection_result = await self._run_reflection(g_final_response)
            except Exception as e:
                logger.warning(f"Reflection failed (non-fatal): {e}", exc_info=True)

            r_n = reflection_result.get("lessons_recorded", 0)
            r_tokens = reflection_result.get("c_tokens", 0)
            if r_n > 0:
                logger.info(f"Reflection: {r_n} lessons (c_tokens={r_tokens})")
                for lesson in reflection_result.get("lessons", []):
                    logger.info(f"  → {lesson.get('node_id', '?')}: {lesson.get('title', '?')[:80]}")
            else:
                logger.info(f"Reflection: PASS (c_tokens={r_tokens}, reason={reflection_result.get('reason', 'none')})")

        # ── PATTERN 自动提升（确定性，零 LLM）── 基于已有 DISCOVERY 节点
        promotion_result = {"patterns_promoted": 0}

        c_tokens_total = reflection_result.get("c_tokens", 0)
        self.c_messages = []
        logger.info(f"C-Process finished (Arena + Trace + Reflection). c_tokens={c_tokens_total}, lessons={reflection_result.get('lessons_recorded', 0)}, total={self.metrics.total_tokens}")
        await self._safe_callback(step_callback, "c_phase_done", {
            "mode": mode, "c_tokens": c_tokens_total,
            "trace_pipeline": trace_pipeline_result,
            "reflection": reflection_result,
            "pattern_promotion": promotion_result,
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
                    if tc_name in ('record_lesson_node', 'record_context_node'):
                        title = tc_args.get('title', '')
                        reason = tc_args.get('because_reason', '')
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

        # 7. Multi-G 发现的知识空洞（已知的未知）
        if self.blackboard and self.blackboard.search_voids:
            void_lines = [f"  - {v}" for v in self.blackboard.search_voids[:5]]
            parts.append("[知识空洞 — Multi-G 搜索未命中的方向]\n" + "\n".join(void_lines))

        # 8. 任务签名（领域上下文）
        if self.inferred_signature:
            sig_text = self.vault.signature.render(self.inferred_signature)
            if sig_text:
                parts.append(f"[任务签名]\n{sig_text}")

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
            return {"lessons_recorded": 0, "c_tokens": 0, "reason": "insufficient_input"}

        # 使用 record_lesson_node 作为输出工具（与 GP 共享同一工具，C 的产出是一等公民）
        from genesis.tools.node_tools import RecordLessonNodeTool
        lesson_tool = RecordLessonNodeTool()
        tool_schema = [lesson_tool.to_schema()]

        system_prompt = (
            "你是回顾者。你刚才观察了 GP 的完整执行过程。\n\n"
            "你的任务不是评判 GP 的工具使用效率（那不重要），"
            "而是审视 GP 工作的内容本身：\n"
            "1. GP 的核心结论是否成立？推理链有没有逻辑跳跃或未验证的假设？\n"
            "2. GP 的发现跟 Vault 已有知识是矛盾、重复、还是扩展？"
            "如果矛盾，用 contradicts 字段指向旧节点。\n"
            "3. 从 GP 的具体发现中，能提炼出什么更一般化的、可跨场景复用的原则？\n"
            "4. GP 的视野之外还有什么相关但未触及的重要方向？\n\n"
            "规则：\n"
            "- 如果 GP 已经通过 record_lesson_node 记录了某个发现，不要重复记录同样的内容\n"
            "- 只记录 GP 遗漏的、更深层的、或跨领域的洞察\n"
            "- 每条 LESSON 必须是原子的（一个核心步骤），可独立复用\n"
            "- 如果 GP 的工作已经足够完整，没有遗漏的深层洞察，不调用任何工具\n"
            "- 最多记录 2 条 LESSON\n"
            "- node_id 前缀用 LESSON_C_ 以区分来源"
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
                return {"lessons_recorded": 0, "c_tokens": c_tokens, "reason": "pass"}

            recorded = []
            for tc in response.tool_calls[:2]:  # 最多 2 条
                if tc.name != "record_lesson_node":
                    continue
                try:
                    args = dict(tc.arguments)
                    # 强制 node_id 前缀为 LESSON_C_
                    nid = args.get("node_id", "")
                    if not nid.startswith("LESSON_C_"):
                        nid_hash = hashlib.md5(nid.encode()).hexdigest()[:8].upper()
                        args["node_id"] = f"LESSON_C_{nid_hash}"
                    result = await lesson_tool.execute(**args)
                    recorded.append({
                        "node_id": args["node_id"],
                        "title": args.get("title", "?"),
                        "result": str(result)[:100],
                    })
                except Exception as e:
                    logger.warning(f"Reflection lesson recording failed: {e}")

            return {
                "lessons_recorded": len(recorded),
                "c_tokens": c_tokens,
                "lessons": recorded,
            }

        except Exception as e:
            logger.warning(f"Reflection LLM call failed (non-fatal): {e}")
            return {"lessons_recorded": 0, "c_tokens": 0, "error": str(e)}

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
                """SELECT kn.node_id, nc.full_content
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
                    vault.touch_node(pattern_id)
                    logger.info(f"PATTERN [{pattern_id}] already exists, marked active")
                    continue

                descriptions = [f"- {d['subject']}: {d['description']}" for d in discoveries[:10]]

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
