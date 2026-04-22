"""
Search Knowledge Nodes Tool — 全局知识搜索工具。

从 node_tools.py 提取。包含完整的搜索管线：
  向量粗排 → LIKE 字面匹配 → 签名门控 → Cross-Encoder 精排 → 分数融合 → Graph Walk → 输出渲染
"""

import logging
import json
import hashlib
import math
import re
from typing import Dict, Any, List

from genesis.v4.manager import METADATA_SIGNATURE_FIELDS
from genesis.v4.knowledge_query import normalize_node_dict
from genesis.tools._base import BaseNodeTool

logger = logging.getLogger(__name__)


class SearchKnowledgeNodesTool(BaseNodeTool):
    """节点管理工具：全局搜索。前后台均有权限使用。"""

    # ── 搜索命中率仪表盘（进程级统计） ──
    _search_total: int = 0
    _search_hits: int = 0
    _search_misses: int = 0
    _fusion_score_sum: float = 0.0
    _fusion_score_count: int = 0
    # ── 节点级信用归因缓存：最近一次搜索的 {node_id: fusion_score} ──
    _last_fusion_scores: Dict[str, float] = {}

    @classmethod
    def _record_search_stats(cls, hit: bool, top_fusion_scores: list = None):
        cls._search_total += 1
        if hit:
            cls._search_hits += 1
        else:
            cls._search_misses += 1
        if top_fusion_scores:
            cls._fusion_score_sum += sum(top_fusion_scores)
            cls._fusion_score_count += len(top_fusion_scores)
        # 每 5 次搜索输出一次摘要日志
        if cls._search_total % 5 == 0:
            hit_rate = cls._search_hits / cls._search_total if cls._search_total else 0
            avg_fusion = cls._fusion_score_sum / cls._fusion_score_count if cls._fusion_score_count else 0
            logger.info(
                f"[搜索仪表盘] total={cls._search_total} hit_rate={hit_rate:.1%} "
                f"avg_fusion={avg_fusion:.3f} misses={cls._search_misses}"
            )

    def _record_search_void(self, keywords, ntype=None, extra=None):
        """搜索未命中或锥体薄时记录 VOID（知识缺口），引导未来探索方向。
        auto mode 禁用 Multi-G，导致 lens_phase 的 void 记录不触发，
        此处补齐搜索层的 void 记录。
        extra: 可选附加信息（如锥体密度指标），会追加到 source 中。
        """
        if not keywords:
            return
        try:
            query_text = " ".join(keywords) if isinstance(keywords, (list, tuple)) else str(keywords)
            void_id = f"VOID_SEARCH_{hashlib.md5(query_text.encode()).hexdigest()[:8].upper()}"
            source = f"search_miss:{ntype or 'any'}"
            if extra:
                source += f" | {extra}"
            self.vault.add_void_task(void_id=void_id, query=query_text, source=source)
        except Exception as e:
            logger.debug(f"search void recording failed: {e}")

    @classmethod
    def get_fusion_scores(cls, node_ids: list = None) -> Dict[str, float]:
        """获取指定节点的 fusion_score（供 Arena 信用归因），未指定则返回全部缓存"""
        if node_ids is None:
            return dict(cls._last_fusion_scores)
        return {nid: cls._last_fusion_scores.get(nid, 0.0) for nid in node_ids}

    @classmethod
    def reset_fusion_cache(cls):
        """每次请求开始时重置，防止上一次请求的分数污染当前归因"""
        cls._last_fusion_scores = {}

    @classmethod
    def get_search_stats(cls) -> dict:
        """供 heartbeat / 外部监控获取搜索健康指标"""
        return {
            "search_total": cls._search_total,
            "search_hits": cls._search_hits,
            "search_misses": cls._search_misses,
            "hit_rate": round(cls._search_hits / cls._search_total, 4) if cls._search_total else None,
            "avg_fusion_score": round(cls._fusion_score_sum / cls._fusion_score_count, 4) if cls._fusion_score_count else None,
        }

    @property
    def name(self) -> str:
        return "search_knowledge_nodes"

    @property
    def description(self) -> str:
        return "在整个认知元信息库中搜索已有经验、环境、资产、轨迹和图谱节点（支持关键词查询）。"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "搜索关键词列表，如 ['n8n', 'jwt']。支持中文。为空将拉取最新活跃节点。"
                },
                "ntype": {
                    "type": "string", 
                    "enum": ["ALL", "LESSON", "ASSET", "CONTEXT", "EPISODE"],
                    "description": "要筛选的节点类型，默认为 'ALL'"
                },
                "signature": {
                    "type": "object",
                    "description": "可选的签名过滤条件。核心字段: os_family, language, framework, runtime, error_kind, task_kind。也支持任意自定义维度过滤。",
                    "properties": {field: {"type": "string", "description": f"{field} 过滤条件"} for field in METADATA_SIGNATURE_FIELDS},
                    "additionalProperties": {"type": "string"}
                },
                "conversation_context": {
                    "type": "string",
                    "description": "可选。最近对话的关键上下文摘要，用于扩展搜索范围。系统会自动注入，G 无需手动填写。"
                }
            },
            "required": ["keywords"]
        }

    def _active_bucket(self, node: Dict[str, Any]) -> str:
        ntype = (node.get("ntype") or "").upper()
        reliability = node.get("reliability") or {}
        invalidation_reason = reliability.get("invalidation_reason")
        if reliability.get("epoch_stale") or invalidation_reason == "superseded_env":
            return "support"
        if invalidation_reason == "manual_outdated":
            return "support"
        if invalidation_reason == "audit_outdated":
            return "conditional"
        knowledge_state = reliability.get("knowledge_state")
        if knowledge_state == "unverified":
            return "support"
        if knowledge_state == "historical":
            return "conditional"
        if ntype in ["ASSET", "LESSON", "CONTEXT"]:
            return "recommended"
        if ntype == "EPISODE":
            return "conditional"
        return "support"

    def _active_reason(self, node: Dict[str, Any]) -> str:
        ntype = (node.get("ntype") or "").upper()
        reliability = node.get("reliability") or {}
        if reliability.get("epoch_stale"):
            return "适用环境来自旧 Doctor epoch 的快照，默认不按当前环境挂载"
        invalidation_reason = reliability.get("invalidation_reason")
        if invalidation_reason == "superseded_env":
            return "适用环境已被新环境取代，仅作为旧快照参考"
        if invalidation_reason == "audit_outdated":
            return "经审计判定已过时，默认不直接挂载；仅在兼容旧方案时参考"
        if invalidation_reason == "manual_outdated":
            return "已被手动标记为过时，默认不挂载，仅在复盘时参考"
        knowledge_state = reliability.get("knowledge_state")
        if knowledge_state == "historical":
            return "历史知识，仅在复盘或延续旧轨迹时再挂载"
        if knowledge_state == "unverified":
            return "未验证知识，先作为背景参考"
        if ntype == "ASSET":
            return "可直接复用给 Op 的产物"
        if ntype == "LESSON":
            return "可直接指导 Op 的方法或原则"
        if ntype == "CONTEXT":
            return "执行前应挂载的环境约束"
        if ntype == "EPISODE":
            return "仅在延续当前任务轨迹时再挂载"
        if ntype in ["ACTION", "EVENT", "ENTITY"]:
            return "更适合作为因果背景或图谱补充"
        return "作为背景参考"

    def _bucket_label(self, bucket: str) -> str:
        labels = {
            "recommended": "推荐",
            "conditional": "条件",
            "support": "背景",
        }
        return labels.get(bucket or "", "背景")

    def _bucket_summary(self, rows: List[Dict[str, Any]], limit: int = 4) -> str:
        parts = []
        for row in rows[:limit]:
            reason = row.get("active_reason") or self._active_reason(row)
            parts.append(f"{row['node_id']}({reason})")
        return " | ".join(parts)

    def _metric_score(self, node: Dict[str, Any]) -> float:
        """UCB 战绩评分：未经测试的节点获得探索加成，随数据积累自然衰减。
        
        公式: exploitation + exploration_bonus
        - exploitation = success_rate (0~1)
        - exploration_bonus = sqrt(2 * ln(N+1) / (n+1))，N=全局总使用次数，n=该节点使用次数
        - 未测试节点 ≈ 0.7，经过考验的好节点 > 0.8，失败多的节点 < 0.4
        """
        success = node.get('usage_success_count', 0) or 0
        fail = node.get('usage_fail_count', 0) or 0
        n = success + fail
        if n == 0:
            return 0.7  # 探索奖励：给未测试节点显著高于旧版 0.5 的基线
        exploitation = success / n
        # 探索项：随 n 增大而衰减，让数据说话
        exploration = math.sqrt(2.0 * math.log(n + 2) / (n + 1))
        return min(1.0, exploitation + 0.15 * exploration)

    def _type_rank(self, node: Dict[str, Any]) -> int:
        ntype = (node.get("ntype") or "").upper()
        ranks = {
            "ASSET": 0,
            "LESSON": 1,
            "CONTEXT": 2,
            "EPISODE": 3,
            "ACTION": 4,
            "EVENT": 5,
            "ENTITY": 6,
            "TOOL": 7,
        }
        return ranks.get(ntype, 99)

    def _signature_values(self, signature: Dict[str, Any], key: str) -> List[str]:
        signature = signature or {}
        alias_keys = [key]
        if key == "environment_scope":
            alias_keys = ["applies_to_environment_scope", "environment_scope"]
        elif key == "environment_epoch":
            alias_keys = ["applies_to_environment_epoch", "environment_epoch"]
        result: List[str] = []
        for alias_key in alias_keys:
            value = signature.get(alias_key)
            if not value:
                continue
            values = value if isinstance(value, list) else [value]
            for raw in values:
                if isinstance(raw, str) and "," in raw:
                    parts = [part.strip() for part in raw.split(",") if part.strip()]
                    for part in parts:
                        if part not in result:
                            result.append(part)
                    continue
                item = str(raw).strip()
                if item and item not in result:
                    result.append(item)
        return result

    def _signature_gate(self, node_signature: Dict[str, Any], query_signature: Dict[str, Any]) -> bool:
        if not query_signature:
            return True
        hard_keys = ["os_family", "runtime", "language", "framework", "environment_scope"]
        for key in hard_keys:
            query_values = set(self._signature_values(query_signature, key))
            node_values = set(self._signature_values(node_signature, key))
            if query_values and node_values and not (query_values & node_values):
                return False
        return True

    def _signature_score(self, node_signature: Dict[str, Any], query_signature: Dict[str, Any]) -> int:
        if not query_signature:
            return 0
        score = 0
        hard_keys = {"os_family", "runtime", "language", "framework", "environment_scope"}
        soft_keys = {"task_kind", "target_kind", "error_kind", "validation_status"}
        known_keys = hard_keys | soft_keys | {"applies_to_environment_scope", "applies_to_environment_epoch", "metadata_schema_version"}
        for key in hard_keys:
            query_values = set(self._signature_values(query_signature, key))
            if not query_values:
                continue
            node_values = set(self._signature_values(node_signature, key))
            if node_values & query_values:
                score += 4
            elif not node_values:
                score -= 1
        for key in soft_keys:
            query_values = set(self._signature_values(query_signature, key))
            if not query_values:
                continue
            node_values = set(self._signature_values(node_signature, key))
            if node_values & query_values:
                score += 2
        for key in query_signature:
            if key in known_keys:
                continue
            query_values = set(self._signature_values(query_signature, key))
            if not query_values:
                continue
            node_values = set(self._signature_values(node_signature, key))
            if node_values & query_values:
                score += 2  # 与 soft_keys 同权，让注册表维度有实际区分力
        return score

    # ── 分数融合 (Score Fusion) ──
    # 加权融合代替元组排序，每个信号归一化后按权重叠加
    # 效用驱动检索（MemRL 启发）：metric(战绩) 是主信号，rerank(相关度) 是门槛
    FUSION_WEIGHTS = {"rerank": 0.30, "trust": 0.15, "metric": 0.35, "signature": 0.20}
    # reranker 不可用时，效用信号权重更高——缺乏相关度精排时，靠实战记录说话
    FUSION_WEIGHTS_NO_RERANK = {"trust": 0.20, "metric": 0.50, "signature": 0.30}

    def _fusion_score(self, row: Dict[str, Any], max_sig: float = 1.0) -> float:
        has_rerank = 'rerank_score' in row and row['rerank_score'] is not None
        reliability = row.get('reliability') or {}
        trust_raw = reliability.get('trust_score', 0.0)
        trust = min(1.0, max(0.0, trust_raw / 10.0))  # trust_score 范围 ~0-10 归一化
        metric = self._metric_score(row)
        sig_raw = row.get('signature_match_score', 0)
        sig = min(1.0, max(0.0, sig_raw / max(max_sig, 1.0))) if max_sig > 0 else 0.0
        if has_rerank:
            w = self.FUSION_WEIGHTS
            rerank = min(1.0, max(0.0, row.get('rerank_score', 0.0) or 0.0))
            fused = w["rerank"] * rerank + w["trust"] * trust + w["metric"] * metric + w["signature"] * sig
        else:
            w = self.FUSION_WEIGHTS_NO_RERANK
            fused = w["trust"] * trust + w["metric"] * metric + w["signature"] * sig
        if reliability.get('epoch_stale'):
            fused = max(0.0, fused - 0.18)
        invalidation_reason = reliability.get('invalidation_reason')
        if invalidation_reason == 'audit_outdated':
            fused = max(0.0, fused - 0.08)
        elif invalidation_reason == 'manual_outdated':
            fused = max(0.0, fused - 0.14)
        elif invalidation_reason == 'superseded_env' and not reliability.get('epoch_stale'):
            fused = max(0.0, fused - 0.18)
        row['fusion_score'] = round(fused, 4)
        return fused

    async def execute(self, keywords: List[str] = None, ntype: str = "ALL", signature: Dict[str, Any] = None, conversation_context: str = None) -> str:
        try:
            normalized_signature = self.vault.signature.normalize(signature)
            # Query Expansion: 用对话上下文扩展搜索关键词
            expanded_keywords = list(keywords) if keywords else []
            if conversation_context and conversation_context.strip():
                # 从对话上下文中提取有意义的关键词片段（去重，不超过 3 个）
                context_tokens = re.findall(r'[\w\u4e00-\u9fff]{2,}', conversation_context)
                existing_set = set(k.lower() for k in expanded_keywords)
                added = 0
                for token in context_tokens:
                    if token.lower() not in existing_set and added < 3:
                        expanded_keywords.append(token)
                        existing_set.add(token.lower())
                        added += 1
            semantic_ids = []
            if self.vault.vector_engine.is_ready and expanded_keywords:
                query_str = " ".join(expanded_keywords)
                results = self.vault.vector_engine.search(query_str, top_k=15, threshold=0.55)
                semantic_ids = [r[0] for r in results]

            conn = self.vault._conn
            with conn:
                query = ("SELECT node_id, type, title, tags, prerequisites, resolves, metadata_signature, "
                         "usage_count, usage_success_count, usage_fail_count, last_verified_at, "
                         "verification_source, updated_at, trust_tier FROM knowledge_nodes "
                         "WHERE node_id NOT LIKE 'MEM_CONV%'"
                         " AND node_id NOT IN (SELECT target_id FROM node_edges WHERE relation = 'CONTRADICTS')")
                params = []

                if ntype != "ALL":
                    query += " AND type = ?"
                    params.append(ntype)

                if keywords or semantic_ids:
                    conditions = []
                    
                    # 传统的字面量匹配 (LIKE)
                    # 将短语拆分为独立词：LLM 常传 'v2ray socks5 routing' 这样的短语，
                    # LIKE '%v2ray socks5 routing%' 要求整串连续匹配，几乎永远命不中。
                    # 拆成 ['v2ray', 'socks5', 'routing'] 后每个词独立 LIKE，召回率大幅提升。
                    if keywords:
                        split_tokens = []
                        for kw in keywords:
                            tokens = re.findall(r'[\w\u4e00-\u9fff]+', kw)
                            split_tokens.extend(tokens)
                        # 去重保序
                        seen = set()
                        unique_tokens = []
                        for t in split_tokens:
                            t_lower = t.lower()
                            if t_lower not in seen and len(t) >= 2:
                                seen.add(t_lower)
                                unique_tokens.append(t)
                        keyword_conditions = []
                        for token in unique_tokens:
                            keyword_conditions.append("(title LIKE ? OR tags LIKE ? OR node_id LIKE ? OR resolves LIKE ?)")
                            kw_like = f"%{token}%"
                            params.extend([kw_like, kw_like, kw_like, kw_like])
                        if keyword_conditions:
                            conditions.append("(" + " OR ".join(keyword_conditions) + ")")
                    
                    # 降维式的语义向量匹配 (Vector Similarity)
                    if semantic_ids:
                        placeholders = ','.join('?' * len(semantic_ids))
                        conditions.append(f"node_id IN ({placeholders})")
                        params.extend(semantic_ids)

                    if conditions:
                        query += " AND (" + " OR ".join(conditions) + ")"

                query += " ORDER BY updated_at DESC LIMIT ?"
                params.append(40 if normalized_signature else 15)
                rows = conn.execute(query, tuple(params)).fetchall()

                if not rows:
                    self._record_search_stats(hit=False)
                    # 记录搜索空洞 → VOID 任务队列（引导未来探索方向）
                    self._record_search_void(keywords, ntype)
                    return f"⚠️ [未命中] 未找到与 {keywords} 相关的 {ntype} 节点（字面+语义均无匹配）。当前处于未知区域，请基于通用能力处理。"

                # 读时衰减：软淘汰 effective_confidence < 0.2 的节点
                query_str = " ".join(keywords) if keywords else ""
                row_dicts = [normalize_node_dict(dict(r)) for r in rows]
                row_dicts = [r for r in row_dicts if self.vault.effective_confidence(r) >= 0.2]
                if not row_dicts:
                    self._record_search_stats(hit=False)
                    return f"⚠️ [未命中] 未找到与 {keywords} 相关的有效 {ntype} 节点（所有候选已衰减淘汰）。当前处于未知区域，请基于通用能力处理。"

                # Reranker 精排：用 Cross-Encoder 按相关度重新排序
                if normalized_signature:
                    row_dicts = [r for r in row_dicts if self._signature_gate(self.vault.signature.parse(r.get('metadata_signature')), normalized_signature)]
                    if not row_dicts:
                        self._record_search_stats(hit=False)
                        sig_text = self.vault.signature.render(normalized_signature)
                        return f"⚠️ [签名过滤后未命中] 未找到同时满足关键词 {keywords} 与签名 {sig_text} 的 {ntype} 节点。建议放宽部分硬环境约束后重试。"
                row_dicts = self.vault.vector_engine.rerank(query_str, row_dicts)
                if row_dicts and 'rerank_score' not in row_dicts[0]:
                    logger.warning("搜索降级: reranker 不可用，fusion_score 已切换为三信号归一化权重模式")
                # 批量预取所有 prerequisite 节点签名（1 次 SQL 代替 N 次）
                all_prereq_node_ids = set()
                for row in row_dicts:
                    prereq_str = (row.get('prerequisites') or '').strip()
                    if prereq_str:
                        for pid in prereq_str.split(','):
                            pid = pid.strip()
                            if pid:
                                all_prereq_node_ids.add(pid)
                prereq_briefs = self.vault.get_node_briefs(list(all_prereq_node_ids)) if all_prereq_node_ids else {}
                for row in row_dicts:
                    parsed_signature = self.vault.signature.parse(row.get('metadata_signature'))
                    row['signature_text'] = self.vault.signature.render(parsed_signature)
                    row['signature_match_score'] = self._signature_score(parsed_signature, normalized_signature)
                    # 构建 closure signature：自身签名 + prerequisite 签名（无额外 SQL）
                    closure_sigs = [parsed_signature] if parsed_signature else []
                    prereq_str = (row.get('prerequisites') or '').strip()
                    if prereq_str:
                        for pid in prereq_str.split(','):
                            pid = pid.strip()
                            pb = prereq_briefs.get(pid)
                            if pb and pb.get('metadata_signature'):
                                closure_sigs.append(self.vault.signature.parse(pb['metadata_signature']))
                    row['signature_closure_text'] = self.vault.signature.render(
                        self.vault.signature.merge(*closure_sigs) if closure_sigs else {}
                    )
                    row['reliability'] = self.vault.build_reliability_profile(row)
                    row['active_bucket'] = self._active_bucket(row)
                    row['active_reason'] = self._active_reason(row)
                # 分数融合：加权排序代替元组排序
                max_sig = max((r.get('signature_match_score', 0) for r in row_dicts), default=1) or 1
                for r in row_dicts:
                    self._fusion_score(r, max_sig=max_sig)
                row_dicts.sort(key=lambda r: r.get('fusion_score', 0.0), reverse=True)
                # ── 信用归因缓存：累积每次搜索的 fusion_score（同节点取最高分） ──
                for r in row_dicts:
                    nid = r.get('node_id')
                    score = r.get('fusion_score', 0.0)
                    if nid and score > self.__class__._last_fusion_scores.get(nid, 0.0):
                        self.__class__._last_fusion_scores[nid] = score
                
                # === Graph Walk (点线面：连根拔起) ===
                # 强边(REQUIRES/TRIGGERS)做 2 跳拉出深度，弱边(RELATED_TO)保持 1 跳拉出宽度
                DEEP_EDGES = {"REQUIRES", "TRIGGERS", "RESOLVES", "PREREQUISITE"}
                graph_context = {}
                graph_related_ids = {}
                
                for r in row_dicts:
                    nid = r['node_id']
                    if nid not in graph_context: graph_context[nid] = []
                    if nid not in graph_related_ids: graph_related_ids[nid] = []
                    
                    # 1-hop: 所有边
                    hop1_deep_ids = []
                    for direction, arrow_fmt in [("out", "--> [{rel}] --> <{type}> {title} ({nid2})"),
                                                  ("in",  "<-- [{rel}] -- <{type}> {title} ({nid2})")]:
                        neighbors = self.vault.get_related_nodes(nid, direction=direction)
                        for neighbor in neighbors:
                            rel = neighbor['relation']
                            n2id = neighbor['node_id']
                            line = arrow_fmt.format(rel=rel, type=neighbor['type'], title=neighbor['title'], nid2=n2id)
                            graph_context[nid].append(line)
                            if n2id not in graph_related_ids[nid]:
                                graph_related_ids[nid].append(n2id)
                            # 记录强边邻居，用于 2-hop
                            if rel in DEEP_EDGES:
                                hop1_deep_ids.append(n2id)
                    
                    # 2-hop: 只沿强边再走一层（限制每个源节点最多 6 个 2-hop 邻居）
                    hop2_count = 0
                    seen_hop2 = set()
                    for h1id in hop1_deep_ids:
                        if hop2_count >= 6:
                            break
                        for direction in ["out", "in"]:
                            hop2_neighbors = self.vault.get_related_nodes(h1id, direction=direction)
                            for h2 in hop2_neighbors:
                                h2id = h2['node_id']
                                h2rel = h2['relation']
                                if h2id == nid or h2id in seen_hop2:
                                    continue
                                if h2rel not in DEEP_EDGES:
                                    continue
                                seen_hop2.add(h2id)
                                hop2_line = f"    (2-hop via {h1id}) --> [{h2rel}] --> <{h2['type']}> {h2['title']} ({h2id})"
                                graph_context[nid].append(hop2_line)
                                if h2id not in graph_related_ids[nid]:
                                    graph_related_ids[nid].append(h2id)
                                hop2_count += 1
                                if hop2_count >= 6:
                                    break

                all_prereq_ids = set()
                for r in row_dicts:
                    if r.get('prerequisites'):
                        for pid in r['prerequisites'].split(','):
                            all_prereq_ids.add(pid.strip())
                
                prereq_nodes = []
                if all_prereq_ids:
                    placeholders = ','.join('?' * len(all_prereq_ids))
                    prereq_query = f"SELECT node_id, type, title, tags FROM knowledge_nodes WHERE node_id IN ({placeholders})"
                    prereq_nodes = conn.execute(prereq_query, tuple(all_prereq_ids)).fetchall()

                recommended_rows = []
                conditional_rows = []
                support_rows = []
                for row in row_dicts:
                    bucket = row.get('active_bucket') or self._active_bucket(row)
                    if bucket == "recommended":
                        recommended_rows.append(row)
                    elif bucket == "conditional":
                        conditional_rows.append(row)
                    else:
                        support_rows.append(row)

                recommended_rows.sort(
                    key=lambda r: (
                        self._type_rank(r),
                        -(r.get('fusion_score', 0.0)),
                    )
                )
                conditional_rows.sort(
                    key=lambda r: (
                        self._type_rank(r),
                        -(r.get('fusion_score', 0.0)),
                    )
                )
                support_rows.sort(
                    key=lambda r: (
                        self._type_rank(r),
                        -(r.get('fusion_score', 0.0)),
                    )
                )

                # === 点线面：面扩散（替代圆锥凝实度摘要） ===
                seed_ids = [r['node_id'] for r in row_dicts[:8]]
                surface = self.vault.expand_surface(seed_ids, context_budget=25000)
                surface_points = surface.get("points", [])
                surface_frontiers = surface.get("frontiers", [])
                surface_voids = surface.get("voids", [])

                # 交叉查询 void_tasks：找出与本次搜索相关的知识空洞
                void_count = 0
                void_hints = []
                try:
                    void_conditions = []
                    void_params = []
                    for kw in (expanded_keywords or keywords or []):
                        void_conditions.append("query LIKE ?")
                        void_params.append(f"%{kw}%")
                    if void_conditions:
                        void_sql = f"SELECT void_id, query FROM void_tasks WHERE status = 'open' AND ({' OR '.join(void_conditions)}) LIMIT 5"
                        void_rows = conn.execute(void_sql, tuple(void_params)).fetchall()
                        void_count = len(void_rows)
                        void_hints = [f"  [?] {vr['query'][:60]} ({vr['void_id']})" for vr in void_rows]
                except Exception:
                    pass

                # === 知识邻域视图（连根拔起） ===
                total_neighbors = sum(len(v) for v in graph_related_ids.values())

                # 面拓扑呈现（合并到首行，防Discord截断；无数字评分，GP从拓扑自己感受价值）
                depth_counts = {}
                for p in surface_points:
                    d = p.get("depth", 0)
                    depth_counts[d] = depth_counts.get(d, 0) + 1
                depth_str = " | ".join(f"d{d}:{c}" for d, c in sorted(depth_counts.items()))
                terrain_str = f"地形:{len(surface_points)}点({depth_str}) {len(surface_frontiers)}前沿 {len(surface_voids)}空洞"
                lines = [f"🔍 [知识邻域] 查询: {keywords} | 命中 {len(row_dicts)} 节点，关联 {total_neighbors} 邻居 | {terrain_str}"]

                if surface_frontiers:
                    frontier_names = [f["title"][:30] for f in surface_frontiers[:5]]
                    lines.append(f"[前沿] {', '.join(frontier_names)}")
                if surface_voids:
                    void_briefs = self.vault.get_node_briefs(surface_voids[:5])
                    void_names = [void_briefs.get(vid, {}).get("title", vid)[:30] for vid in surface_voids[:5]]
                    lines.append(f"[空洞边界] {', '.join(void_names)} — 这些方向无后续推导")
                if void_hints:
                    lines.append("[知识空洞]")
                    lines.extend(void_hints)

                if normalized_signature:
                    lines.append(f"签名: {self.vault.signature.render(normalized_signature)}")
                lines.append("")

                # 直接命中节点 + 维度信息 + 内联边（连根拔起视图）
                for r in row_dicts[:8]:
                    nid = r['node_id']
                    # 紧凑元数据
                    meta = []
                    wins = r.get('usage_success_count', 0) or 0
                    losses = r.get('usage_fail_count', 0) or 0
                    if wins or losses:
                        meta.append(f"{wins}W/{losses}L")
                    reliability = r.get('reliability') or {}
                    if reliability.get('epoch_stale'):
                        meta.append("旧快照")
                    elif reliability.get('invalidation_reason') == 'audit_outdated':
                        meta.append("审计过时")
                    elif reliability.get('invalidation_reason') == 'manual_outdated':
                        meta.append("手动作废")
                    elif reliability.get('knowledge_state') == 'historical':
                        meta.append("historical")
                    elif reliability.get('knowledge_state') == 'unverified':
                        meta.append("unverified")
                    if reliability.get('temporally_expired'):
                        meta.append("已过期")
                    if reliability.get('freshness_label'):
                        meta.append(reliability['freshness_label'])
                    meta.append(self._bucket_label(r.get('active_bucket') or self._active_bucket(r)))
                    match_type = "语义" if nid in semantic_ids else "字面"
                    meta.append(match_type)
                    meta_str = " | ".join(meta)
                    lines.append(f"● <{r['type']}> {r['title']} [{nid}] ({meta_str})")
                    # 维度信息：tags + signature + resolves（G 决策需要）
                    detail_parts = []
                    if r.get('tags'):
                        detail_parts.append(f"tags:{r['tags']}")
                    if r.get('signature_text'):
                        detail_parts.append(f"sig:{r['signature_text']}")
                    if reliability.get('epoch_stale'):
                        active_epoch = reliability.get('active_environment_epoch') or ""
                        if active_epoch:
                            detail_parts.append(f"epoch:stale→{active_epoch[-12:]}")
                        else:
                            detail_parts.append("epoch:stale")
                    elif reliability.get('environment_epoch'):
                        detail_parts.append(f"epoch:{reliability['environment_epoch'][-12:]}")
                    observed_scope = reliability.get('observed_environment_scope') or ""
                    applies_scope = reliability.get('applies_to_environment_scope') or reliability.get('environment_scope') or ""
                    if observed_scope and observed_scope != applies_scope:
                        detail_parts.append(f"observed:{observed_scope}")
                    observed_epoch = reliability.get('observed_environment_epoch') or ""
                    applies_epoch = reliability.get('applies_to_environment_epoch') or reliability.get('environment_epoch') or ""
                    if observed_epoch and observed_epoch != applies_epoch:
                        detail_parts.append(f"observed_epoch:{observed_epoch[-12:]}")
                    invalidation_reason = reliability.get('invalidation_reason') or ""
                    if invalidation_reason:
                        detail_parts.append(f"invalid:{invalidation_reason}")
                    if r.get('resolves'):
                        detail_parts.append(f"resolves:{r['resolves'][:80]}")
                    if detail_parts:
                        lines.append(f"  {' | '.join(detail_parts)}")
                    # 内联边：展示知识邻域连接（含 2-hop 深度）
                    if nid in graph_context:
                        for rel_line in graph_context[nid][:6]:
                            lines.append(f"  {rel_line}")
                    if r.get('prerequisites'):
                        lines.append(f"  requires: {r['prerequisites']}")

                # 建议挂载（紧凑列表）
                lines.append("")
                suggested_ids = [r['node_id'] for r in recommended_rows[:6]]
                # 补充：被多个命中节点引用的邻居也值得挂载
                neighbor_freq = {}
                for nid, neighbors in graph_related_ids.items():
                    for neighbor_id in neighbors:
                        if neighbor_id not in {r['node_id'] for r in row_dicts}:
                            neighbor_freq[neighbor_id] = neighbor_freq.get(neighbor_id, 0) + 1
                hot_neighbors = [nid for nid, cnt in sorted(neighbor_freq.items(), key=lambda x: -x[1]) if cnt >= 2][:3]
                if hot_neighbors:
                    suggested_ids.extend(hot_neighbors)
                lines.append(f"[建议挂载] {', '.join(suggested_ids[:8]) if suggested_ids else '无强推荐'}")
                if conditional_rows:
                    lines.append(f"[条件挂载] {self._bucket_summary(conditional_rows)}")
                if support_rows:
                    lines.append(f"[支撑背景] {self._bucket_summary(support_rows)}")
                if hot_neighbors:
                    lines.append(f"[高频邻居] {', '.join(hot_neighbors)}（被多个命中节点引用，建议一起挂载）")

                # ── 稀疏面 → VOID 记录（知识缺口，引导未来探索） ──
                if len(surface_points) < 3:
                    self._record_search_void(keywords, ntype,
                                             extra=f"surface_points={len(surface_points)},frontiers={len(surface_frontiers)}")

                # ── 搜索仪表盘统计 ──
                top_scores = [r.get('fusion_score', 0.0) for r in row_dicts[:5]]
                self._record_search_stats(hit=True, top_fusion_scores=top_scores)

                return "\n".join(lines)
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return f"Error: {e}"
