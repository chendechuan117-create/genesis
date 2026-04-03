"""
Genesis V4 - Multi-G 透镜阶段 (Lens Phase Mixin)

从 V4Loop 中提取的 10 个 Lens/Multi-G 相关方法。
V4Loop 通过 Mixin 继承获得这些方法，无需改变调用方式。
"""

import re
import json
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional

from genesis.core.base import Message, MessageRole
from genesis.v4.blackboard import Blackboard
from genesis.v4.manager import PERSONA_ACTIVATION_MAP
from genesis.v4.pipeline_config import PIPELINE_CONFIG

logger = logging.getLogger(__name__)


class LensPhaseMixin:
    """Multi-G 透镜阶段方法集合。通过 Mixin 注入 V4Loop。

    依赖 V4Loop 的属性：
    - self.blackboard, self.vault, self.provider, self.tools, self.factory
    - self.inferred_signature, self.TOOL_EXEC_TIMEOUT
    - self._safe_callback, self._emit_llm_call_start/end, self._update_metrics
    """

    # ── 常量 ──────────────────────────────────
    MULTI_G_TASK_KINDS = frozenset(["debug", "refactor", "build", "optimize", "design", "test", "deploy", "configure"])
    LENS_MAX_ITERATIONS = PIPELINE_CONFIG.lens_max_iterations
    LENS_TIMEOUT_SECS = PIPELINE_CONFIG.lens_timeout_secs

    PERSONA_EXTENSION_POOL = ["ISTP", "ENTJ", "ISFJ", "ENFP", "ESTJ", "INFJ", "ISTJ", "INTP", "INTJ"]
    ALL_PERSONAS = [
        "ISTJ", "ISFJ", "INFJ", "INTJ", "ISTP", "ISFP", "INFP", "INTP",
        "ESTP", "ESFP", "ENFP", "ENTP", "ESTJ", "ESFJ", "ENFJ", "ENTJ",
    ]

    # ─── Multi-G 采纳率追踪 ─────────────────────────────────────────────

    def _check_lens_adoption(
        self,
        g_text: str,
        g_active_nodes: List[str] = None,
        event: str = "dispatch"
    ) -> Dict[str, Any]:
        """检测 G 是否采纳了 Multi-G 透镜的建议。零额外 LLM 调用。"""
        if not self.blackboard or not self.blackboard.entries:
            return {"adopted": [], "ignored": [], "adoption_rate": 0.0, "event": event}

        g_nodes = set(g_active_nodes or [])
        adopted = []
        ignored = []

        for entry in self.blackboard.entries:
            persona = entry.persona
            framework = entry.framework or ""
            signals = []

            # 层1：节点重合
            if hasattr(entry, "evidence_node_ids") and entry.evidence_node_ids:
                overlap = g_nodes & set(entry.evidence_node_ids)
                if overlap:
                    signals.append(f"node_overlap={list(overlap)}")

            # 层2：语义相似度
            if g_text and framework and len(framework) > 10:
                try:
                    from genesis.v4.vector_engine import VectorEngine
                    ve = VectorEngine.get_instance()
                    if ve.is_ready:
                        g_vec = ve.encode(g_text[:300])
                        f_vec = ve.encode(framework[:300])
                        import numpy as np
                        sim = float(np.dot(g_vec, f_vec) / (np.linalg.norm(g_vec) * np.linalg.norm(f_vec) + 1e-9))
                        if sim > 0.65:
                            signals.append(f"semantic_sim={sim:.3f}")
                except Exception:
                    pass

            if signals:
                adopted.append({"persona": persona, "signals": signals, "framework": framework[:80]})
            else:
                ignored.append({"persona": persona, "framework": framework[:80]})

        total = len(self.blackboard.entries)
        rate = len(adopted) / total if total > 0 else 0.0

        report = {
            "event": event,
            "adopted": adopted,
            "ignored": ignored,
            "adoption_rate": rate,
            "adopted_count": len(adopted),
            "total_lenses": total,
        }

        logger.info(
            f"[Multi-G 采纳率] event={event} | {len(adopted)}/{total} adopted ({rate:.0%}) | "
            f"adopted={[a['persona'] for a in adopted]} | "
            f"ignored={[i['persona'] for i in ignored]}"
        )

        # 记录到 persona 采纳统计
        for a in adopted:
            Blackboard.record_persona_adoption(a["persona"], adopted=True)
        for i in ignored:
            Blackboard.record_persona_adoption(i["persona"], adopted=False)

        return report

    # ─── Multi-G 透镜编排 ──────────────────────────────────────────────

    def _auto_record_voids(self, blackboard: Blackboard):
        """基础设施层自动记录搜索空洞到 void_tasks 任务队列。"""
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

        import hashlib
        recorded = 0
        for v in unique_voids[:10]:
            query = v["query"]
            persona = v.get("persona", "unknown")
            q_hash = hashlib.md5(query.encode()).hexdigest()[:8].upper()
            void_id = f"VOID_{q_hash}"

            if self.vault.void_exists(void_id):
                continue

            added = self.vault.add_void_task(
                void_id=void_id,
                query=query,
                source=v.get("source", "search_miss"),
                persona=persona,
                task_signature=self.inferred_signature
            )
            if added:
                recorded += 1

        if recorded:
            logger.info(f"Multi-G: recorded {recorded}/{len(unique_voids)} voids to void_tasks")

    def _should_activate_multi_g(self, user_input: str) -> bool:
        """判断是否应启用 Multi-G 透镜阶段"""
        actual_input = user_input
        if "[GENESIS_USER_REQUEST_START]" in user_input:
            actual_input = user_input.split("[GENESIS_USER_REQUEST_START]", 1)[1]
        actual_input = actual_input.strip()

        if "/quick" in actual_input[:20]:
            logger.info("Multi-G skipped by /quick prefix")
            return False
        if "/deep" in actual_input[:20]:
            logger.info("Multi-G activated by /deep prefix (force 7 lenses)")
            return True

        if len(actual_input) < PIPELINE_CONFIG.lens_min_input_chars:
            logger.info(f"Multi-G skipped: input too short ({len(actual_input)} chars)")
            return False

        logger.info(f"Multi-G activated (default-on, input={len(actual_input)} chars)")
        return True

    def _select_personas(self, target_count: int = 3) -> List[str]:
        """根据签名映射选择激活的人格透镜，支持自适应数量 + 动态淘汰/递补"""
        raw_tk = self.inferred_signature.get("task_kind") or ""
        task_kind = (raw_tk[0] if isinstance(raw_tk, list) and raw_tk else str(raw_tk)).lower()
        base = list(PERSONA_ACTIVATION_MAP.get(task_kind, PERSONA_ACTIVATION_MAP["_default"]))
        base = Blackboard.suggest_persona_swap(base, task_kind, self.ALL_PERSONAS)
        if target_count <= len(base):
            return base[:target_count]
        for p in self.PERSONA_EXTENSION_POOL:
            if len(base) >= target_count:
                break
            if p not in base:
                base.append(p)
        return base

    async def _probe_knowledge_density(self, user_input: str) -> int:
        """G 的'第一搜'：快速探测知识库对当前任务的覆盖密度"""
        try:
            text = user_input
            for prefix in ["/deep ", "/quick "]:
                if text.startswith(prefix):
                    text = text[len(prefix):]
            tokens = re.findall(r'[\w\u4e00-\u9fff]{2,}', text)
            keywords = tokens[:5] if tokens else []
            if not keywords:
                return 0
            query_str = " ".join(keywords)
            hits = 0
            if self.vault.vector_engine.is_ready:
                results = self.vault.vector_engine.search(query_str, top_k=10, threshold=0.55)
                hits = len(results)
            logger.info(f"Multi-G probe: query='{query_str}' → {hits} vector hits")
            return hits
        except Exception as e:
            logger.warning(f"Multi-G probe failed: {e}")
            return 0

    async def _build_g_interpretation(self, clean_input: str, knowledge_digest: str, shared_knowledge: str) -> str:
        """G 先对用户问题产出自己的理解，发布到黑板供透镜补充。"""
        digest_hint = f"\n知识库概况：\n{knowledge_digest[:400]}\n" if knowledge_digest else ""
        knowledge_hint = f"\n预搜到的相关信息：\n{shared_knowledge[:800]}\n" if shared_knowledge else ""

        prompt = f"""你是 Genesis 主脑（G-Process）。在透镜团队分析之前，先简明说出你对用户问题的理解。

用户原话：{clean_input}
{digest_hint}{knowledge_hint}
用 3-5 句话回答：
1. 用户真正想知道/想做什么？（底层意图）
2. 你目前的初步判断是什么？
3. 你觉得哪些方面需要更多视角？

直接输出，不要格式化。"""

        try:
            resp = await asyncio.wait_for(
                self.provider.chat(
                    messages=[{"role": "user", "content": prompt}],
                    timeout=15
                ),
                timeout=15
            )
            interpretation = (resp.content or "").strip()
            if interpretation:
                logger.info(f"G interpretation: {interpretation[:120]}...")
                return interpretation
        except Exception as e:
            logger.warning(f"G interpretation generation failed: {e}")

        return ""

    async def _run_lens_phase(self, user_input: str, step_callback: Any) -> Blackboard:
        """运行 Multi-G 透镜阶段（v2 架构：G 先说理解 → 透镜补充建议）"""
        blackboard = Blackboard()

        _actual = user_input
        if "[GENESIS_USER_REQUEST_START]" in user_input:
            _actual = user_input.split("[GENESIS_USER_REQUEST_START]", 1)[1]
        force_deep = "/deep" in _actual.strip()[:20]
        probe_hits = 0
        if not force_deep:
            probe_hits = await self._probe_knowledge_density(user_input)
            if probe_hits <= 2:
                target_count = 3
            elif probe_hits <= 6:
                target_count = 5
            else:
                target_count = 7
            logger.info(f"Multi-G probe: {probe_hits} hits → {target_count} lenses")
        else:
            target_count = 7
            logger.info(f"Multi-G /deep: forcing {target_count} lenses")

        personas = self._select_personas(target_count)

        logger.info(f">>> Multi-G Lens Phase: spawning {len(personas)} lenses: {personas}")

        clean_input = _actual.strip()
        for prefix in ["/deep ", "/quick "]:
            if clean_input.startswith(prefix):
                clean_input = clean_input[len(prefix):]
        clean_input = clean_input.strip()

        # ── 预搜共享知识：一次搜索，所有透镜共享 ──
        shared_knowledge = await self._prefetch_shared_knowledge(clean_input)
        knowledge_digest = self.vault.get_digest()
        conversation_digest = self.vault.get_conversation_digest(limit=10)
        signature_text = self.vault.render_metadata_signature(self.inferred_signature)

        # ── G 先说自己的理解 ──
        g_interpretation = await self._build_g_interpretation(clean_input, knowledge_digest, shared_knowledge)

        await self._safe_callback(step_callback, "lens_start", {
            "phase": "LENS_PHASE",
            "personas": personas, "probe_hits": probe_hits,
            "g_interpretation": g_interpretation[:200] if g_interpretation else "",
        })

        # ── 并行运行所有透镜（限流：最多 2 并发）──
        sem = asyncio.Semaphore(PIPELINE_CONFIG.lens_concurrency)
        async def _throttled_lens(p):
            async with sem:
                return await self._run_single_lens(
                    persona=p,
                    user_question=clean_input,
                    blackboard=blackboard,
                    shared_knowledge=shared_knowledge,
                    g_interpretation=g_interpretation,
                    knowledge_digest=knowledge_digest,
                    conversation_digest=conversation_digest,
                    signature_text=signature_text,
                    step_callback=step_callback
                )
        tasks = [_throttled_lens(p) for p in personas]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for persona, result in zip(personas, results):
            if isinstance(result, Exception):
                logger.error(f"Lens-{persona} failed: {result}")

        await self._safe_callback(step_callback, "lens_done", {
            "phase": "LENS_PHASE",
            "entries": blackboard.entry_count,
            "voids": len(blackboard.search_voids)
        })

        return blackboard

    async def _prefetch_shared_knowledge(self, clean_input: str) -> str:
        """预搜一次 NodeVault，构建共享知识包。"""
        search_args = {"keywords": [clean_input[:80]]}
        if self.inferred_signature:
            search_args["signature"] = self.inferred_signature

        try:
            search_result = await asyncio.wait_for(
                self.tools.execute("search_knowledge_nodes", search_args),
                timeout=self.TOOL_EXEC_TIMEOUT
            )
        except Exception as e:
            logger.warning(f"Multi-G prefetch search failed: {e}")
            return ""

        if not search_result or "未找到" in str(search_result) or "未命中" in str(search_result):
            return ""

        node_ids = re.findall(r'\[([A-Z_]+_[^\]]+)\]', str(search_result))
        seen = set()
        unique_ids = []
        for nid in node_ids:
            if nid not in seen and not nid.startswith("MEM_CONV"):
                seen.add(nid)
                unique_ids.append(nid)
                if len(unique_ids) >= 5:
                    break

        contents = self.vault.get_multiple_contents(unique_ids) if unique_ids else {}

        lines = [str(search_result)[:2000]]
        if contents:
            lines.append("\n--- 相关节点详细内容 ---")
            for nid in unique_ids:
                content = contents.get(nid, "")
                if content:
                    lines.append(f"\n[{nid}] 内容：\n{content[:500]}")

        knowledge = "\n".join(lines)
        logger.info(f"Multi-G prefetch: {len(unique_ids)} nodes, {len(knowledge)} chars shared knowledge")
        return knowledge

    async def _run_single_lens(
        self,
        persona: str,
        user_question: str,
        blackboard: Blackboard,
        shared_knowledge: str,
        g_interpretation: str,
        knowledge_digest: str,
        conversation_digest: str,
        signature_text: str,
        step_callback: Any
    ):
        """运行单个透镜：基于 G 的理解 + 共享知识，输出补充建议。"""
        lens_prompt = self.factory.build_lens_prompt(
            persona=persona,
            user_question=user_question,
            shared_knowledge=shared_knowledge,
            g_interpretation=g_interpretation,
            blackboard_state=blackboard.render_for_g() if blackboard.entry_count > 0 else "",
            knowledge_digest=knowledge_digest,
            inferred_signature=signature_text,
            conversation_digest=conversation_digest
        )

        messages = [
            Message(role=MessageRole.SYSTEM, content=lens_prompt),
            Message(role=MessageRole.USER, content="从你的认知视角分析这个问题。直接输出 JSON。")
        ]

        llm_call_started = time.time()
        llm_call_id = await self._emit_llm_call_start(step_callback, "LENS_PHASE", 0, stream=False, label=persona)
        try:
            response = await asyncio.wait_for(
                self.provider.chat(
                    messages=[m.to_dict() for m in messages],
                    tools=[],
                    stream=False
                ),
                timeout=self.LENS_TIMEOUT_SECS
            )
            await self._emit_llm_call_end(step_callback, "LENS_PHASE", llm_call_id, 0, llm_call_started, stream=False, response=response, label=persona)
        except asyncio.TimeoutError:
            await self._emit_llm_call_end(step_callback, "LENS_PHASE", llm_call_id, 0, llm_call_started, stream=False, error=f"timeout>{self.LENS_TIMEOUT_SECS}s", label=persona)
            logger.warning(f"Lens-{persona} timeout")
            return
        except Exception as e:
            await self._emit_llm_call_end(step_callback, "LENS_PHASE", llm_call_id, 0, llm_call_started, stream=False, error=e, label=persona)
            logger.error(f"Lens-{persona} LLM call failed: {e}")
            return

        self._update_metrics(response, phase="G")

        if response.content:
            self._parse_lens_output(persona, response.content, blackboard)
            await self._safe_callback(step_callback, "lens_analysis", {
                "phase": "LENS_PHASE",
                "persona": persona,
                "content_preview": response.content[:150]
            })

        logger.info(f"Lens-{persona} finished")

    def _parse_lens_output(self, persona: str, content: str, blackboard: Blackboard):
        """解析透镜 LLM 输出的 JSON 三元组，写入黑板"""
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
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end > start:
                try:
                    parsed = json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass

        if not parsed or not isinstance(parsed, dict):
            logger.warning(f"Lens-{persona} output not valid JSON, treating as hypothesis: {text[:100]}")
            blackboard.add_hypothesis(
                persona=persona,
                framework=text[:200] if text else "无法解析的输出",
                reasoning_chain=text,
                suggested_search_directions=[]
            )
            return

        entry_type = parsed.get("type", "hypothesis")

        if entry_type == "analysis":
            interpretation = parsed.get("interpretation", "")
            key_insight = parsed.get("key_insight", "")
            solution = parsed.get("solution_approach", "")
            risk = parsed.get("risk_or_blind_spot", "")
            node_ids = parsed.get("evidence_node_ids", [])

            rich_framework = interpretation
            if key_insight:
                rich_framework += f" | 洞察: {key_insight}"

            if node_ids:
                rich_action = solution
                if risk:
                    rich_action += f" [风险: {risk}]"
                blackboard.add_evidence(
                    persona=persona,
                    framework=rich_framework,
                    evidence_node_ids=node_ids,
                    verification_action=rich_action
                )
            else:
                blackboard.add_hypothesis(
                    persona=persona,
                    framework=rich_framework,
                    reasoning_chain=solution,
                    suggested_search_directions=[risk] if risk else []
                )
        elif entry_type == "evidence":
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
