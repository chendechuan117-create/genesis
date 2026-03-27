import logging
import json
from typing import Dict, Any, List
from genesis.core.base import Tool
from genesis.v4.manager import NodeVault, METADATA_SIGNATURE_FIELDS, TRUST_TIERS

logger = logging.getLogger(__name__)

# 5 个写入类 Tool 共享的可选信任字段 Schema
TRUST_SCHEMA_PROPERTIES = {
    "metadata_signature": {
        "type": "object",
        "description": "环境/任务签名。核心字段: os_family, language, framework, runtime, error_kind, task_kind, target_kind, environment_scope, validation_status。也接受任意自定义维度（如 polarity, maturity, user_preference 等），系统会自动保存和检索。",
        "properties": {field: {"type": "string", "description": f"{field} 签名"} for field in METADATA_SIGNATURE_FIELDS},
        "additionalProperties": {"type": "string"}
    },
    "confidence_score": {"type": "number", "description": "可选。0-1 之间的弱可信度评分。仅在你有明确把握时填写。"},
    "last_verified_at": {"type": "string", "description": "可选。最近验证时间，建议 ISO 或 'YYYY-MM-DD HH:MM:SS'。"},
    "verification_source": {"type": "string", "description": "可选。验证依据来源，如 command_output, manual_check, reflection。"}
}


class BaseNodeTool(Tool):
    """所有节点管理工具的公共基类，统一 vault 初始化。"""
    def __init__(self):
        self.vault = NodeVault()


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
        ntype = (node.get("type") or "").upper()
        if ntype in ["ASSET", "LESSON", "CONTEXT"]:
            return "recommended"
        if ntype == "EPISODE":
            return "conditional"
        return "support"

    def _active_reason(self, node: Dict[str, Any]) -> str:
        ntype = (node.get("type") or "").upper()
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

    def _metric_score(self, node: Dict[str, Any]) -> float:
        """UCB 战绩评分：未经测试的节点获得探索加成，随数据积累自然衰减。
        
        公式: exploitation + exploration_bonus
        - exploitation = success_rate (0~1)
        - exploration_bonus = sqrt(2 * ln(N+1) / (n+1))，N=全局总使用次数，n=该节点使用次数
        - 未测试节点 ≈ 0.7，经过考验的好节点 > 0.8，失败多的节点 < 0.4
        """
        import math
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
        ntype = (node.get("type") or "").upper()
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
        value = (signature or {}).get(key)
        if not value:
            return []
        return value if isinstance(value, list) else [value]

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
        known_keys = hard_keys | soft_keys
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
        row['fusion_score'] = round(fused, 4)
        return fused

    async def execute(self, keywords: List[str] = None, ntype: str = "ALL", signature: Dict[str, Any] = None, conversation_context: str = None) -> str:
        try:
            normalized_signature = self.vault.normalize_metadata_signature(signature)
            # Query Expansion: 用对话上下文扩展搜索关键词
            expanded_keywords = list(keywords) if keywords else []
            if conversation_context and conversation_context.strip():
                import re
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
                query = "SELECT node_id, type, title, tags, prerequisites, resolves, metadata_signature, usage_count, usage_success_count, usage_fail_count, confidence_score, last_verified_at, verification_source, updated_at, trust_tier FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%'"
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
                        import re as _re
                        split_tokens = []
                        for kw in keywords:
                            tokens = _re.findall(r'[\w\u4e00-\u9fff]+', kw)
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
                    return f"⚠️ [未命中] 未找到与 {keywords} 相关的 {ntype} 节点（字面+语义均无匹配）。当前处于未知区域，请基于通用能力处理。"

                # Reranker 精排：用 Cross-Encoder 按相关度重新排序
                query_str = " ".join(keywords) if keywords else ""
                row_dicts = [dict(r) for r in rows]
                if normalized_signature:
                    row_dicts = [r for r in row_dicts if self._signature_gate(self.vault.parse_metadata_signature(r.get('metadata_signature')), normalized_signature)]
                    if not row_dicts:
                        self._record_search_stats(hit=False)
                        sig_text = self.vault.render_metadata_signature(normalized_signature)
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
                    parsed_signature = self.vault.parse_metadata_signature(row.get('metadata_signature'))
                    row['signature_text'] = self.vault.render_metadata_signature(parsed_signature)
                    row['signature_match_score'] = self._signature_score(parsed_signature, normalized_signature)
                    # 构建 closure signature：自身签名 + prerequisite 签名（无额外 SQL）
                    closure_sigs = [parsed_signature] if parsed_signature else []
                    prereq_str = (row.get('prerequisites') or '').strip()
                    if prereq_str:
                        for pid in prereq_str.split(','):
                            pid = pid.strip()
                            pb = prereq_briefs.get(pid)
                            if pb and pb.get('metadata_signature'):
                                closure_sigs.append(self.vault.parse_metadata_signature(pb['metadata_signature']))
                    row['signature_closure_text'] = self.vault.render_metadata_signature(
                        self.vault.merge_metadata_signatures(*closure_sigs) if closure_sigs else {}
                    )
                    row['reliability'] = self.vault.build_reliability_profile(row)
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
                
                # === Graph Walk (圆锥模型：连根拔起) ===
                # 强边(REQUIRES/TRIGGERS)做 2 跳拉出深度，弱边(RELATED_TO)保持 1 跳拉出宽度
                DEEP_EDGES = {"REQUIRES", "TRIGGERS", "RESOLVES"}
                graph_context = {}
                graph_related_ids = {}
                cone_edge_count = 0
                cone_all_neighbor_ids = set()
                
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
                            cone_all_neighbor_ids.add(n2id)
                            cone_edge_count += 1
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
                                cone_all_neighbor_ids.add(h2id)
                                cone_edge_count += 1
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
                support_rows = []
                for row in row_dicts:
                    bucket = self._active_bucket(row)
                    if bucket in ["recommended", "conditional"]:
                        recommended_rows.append(row)
                    else:
                        support_rows.append(row)

                recommended_rows.sort(
                    key=lambda r: (
                        0 if self._active_bucket(r) == "recommended" else 1,
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

                # === 知识邻域视图（连根拔起） ===
                total_neighbors = sum(len(v) for v in graph_related_ids.values())
                lines = [f"🔍 [知识邻域] 查询: {keywords} | 命中 {len(row_dicts)} 节点，关联 {total_neighbors} 邻居"]
                if normalized_signature:
                    lines.append(f"签名: {self.vault.render_metadata_signature(normalized_signature)}")
                lines.append("")

                # 直接命中节点 + 维度信息 + 内联边（连根拔起视图）
                for r in row_dicts[:8]:
                    nid = r['node_id']
                    # 紧凑元数据
                    meta = []
                    if r.get('fusion_score'):
                        meta.append(f"f:{r['fusion_score']:.2f}")
                    wins = r.get('usage_success_count', 0) or 0
                    losses = r.get('usage_fail_count', 0) or 0
                    if wins or losses:
                        meta.append(f"{wins}W/{losses}L")
                    reliability = r.get('reliability') or {}
                    if reliability.get('freshness_label'):
                        meta.append(reliability['freshness_label'])
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
                if hot_neighbors:
                    lines.append(f"[高频邻居] {', '.join(hot_neighbors)}（被多个命中节点引用，建议一起挂载）")

                # === 圆锥凝实度摘要（含空洞检测） ===
                cone_node_count = len(row_dicts) + len(cone_all_neighbor_ids)
                conf_values = [r.get('confidence_score') or 0.5 for r in row_dicts]
                avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0
                proven_count = sum(1 for r in row_dicts if (r.get('usage_success_count') or 0) >= 2)
                untested_count = sum(1 for r in row_dicts if (r.get('usage_count') or 0) == 0)
                untested_pct = round(untested_count / len(row_dicts) * 100) if row_dicts else 0

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

                # 凝实度判定（综合 PROVEN + UNTESTED 比例 + VOID 空洞）
                if proven_count >= 3 and avg_conf >= 0.7 and cone_edge_count >= 5 and untested_pct < 40:
                    density_label = "高凝实 — 已有成熟解法，可直接组装"
                elif cone_node_count >= 5 and avg_conf >= 0.5:
                    density_label = "中凝实 — 有基础知识，部分区域需验证"
                elif cone_node_count >= 2:
                    density_label = "低凝实 — 知识稀疏，建议先探索再执行"
                else:
                    density_label = "近乎未知 — 无成熟积木，需要全面探索"

                density_parts = [f"{cone_node_count} 节点({untested_count} 未验证)", f"置信 {avg_conf:.2f}", f"{cone_edge_count} 条边", f"{proven_count} PROVEN"]
                if void_count:
                    density_parts.append(f"{void_count} VOID")
                lines.append(f"[知识密度] {' | '.join(density_parts)} → {density_label}")
                if void_hints:
                    lines.append("[知识空洞]")
                    lines.extend(void_hints)

                # ── 搜索仪表盘统计 ──
                top_scores = [r.get('fusion_score', 0.0) for r in row_dicts[:5]]
                self._record_search_stats(hit=True, top_fusion_scores=top_scores)

                return "\n".join(lines)
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return f"Error: {e}"


class RecordContextNodeTool(BaseNodeTool):
    """节点管理工具：记录环境与状态变量节点。专属后台 C 进程权限。"""

    @property
    def name(self) -> str:
        return "record_context_node"

    @property
    def description(self) -> str:
        return "沉淀静态参数类节点 (CONTEXT)，用于记录纯粹的 Key-Value 状态变量或环境信息。(仅超级管理员 C 进程 有权限使用)"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "必须以 CTX_ 开头，大写字母和下划线组成，如 CTX_N8N_API"},
                "title": {"type": "string", "description": "一句话标题，如 'n8n API认证方式'"},
                "state_description": {"type": "string", "description": "纯文本的状态说明或变量值"},
                **TRUST_SCHEMA_PROPERTIES
            },
            "required": ["node_id", "title", "state_description"]
        }

    async def execute(self, node_id: str, title: str, state_description: str, metadata_signature: Dict[str, Any] = None, confidence_score: float = None, last_verified_at: str = None, verification_source: str = None) -> str:
        try:
            self.vault.create_node(
                node_id=node_id,
                ntype="CONTEXT",
                title=title,
                human_translation=title,
                tags="auto_managed",
                full_content=state_description,
                source="reflection",
                metadata_signature=metadata_signature,
                confidence_score=confidence_score,
                last_verified_at=last_verified_at,
                verification_source=verification_source,
                trust_tier="REFLECTION"
            )
            return f"✅ CONTEXT节点 [{node_id}] '{title}' 写入/覆盖成功。"
        except Exception as e:
            logger.error(f"Context node creation failed: {e}")
            return f"Error: {e}"


class RecordLessonNodeTool(BaseNodeTool):
    """节点管理工具：记录经验与执行流节点。专属后台 C 进程权限。"""

    @property
    def name(self) -> str:
        return "record_lesson_node"

    @property
    def description(self) -> str:
        return "沉淀经验流程类节点 (LESSON)，用于记录具体的排错手段或操作流。(仅超级管理员 C 进程 有权限使用)"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "必须以 LESSON_ 开头，大写字母和下划线组成，如 LESSON_DEPLOY"},
                "title": {"type": "string", "description": "一句话标题，如 'Nginx 端口占用解决流'"},
                "trigger_verb": {"type": "string", "description": "触发此动作的动词，如 debug, install"},
                "trigger_noun": {"type": "string", "description": "针对的目标名词，如 nginx, docker"},
                "trigger_context": {"type": "string", "description": "问题触发的环境或上下文，如 startup_failed"},
                "action_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "具体的执行步骤数组，也就是破局点操作"
                },
                "because_reason": {"type": "string", "description": "底层原因说明，解释为何这么做，防止Op幻觉猜忌"},
                "prerequisites": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "执行此操作强制依赖的前置节点ID数组（通常是 CTX_ 节点）。如果无依赖留空数组。"
                },
                "resolves": {"type": "string", "description": "此经验主要解决的具体报错信息或异常现象简述（用于丰富图谱寻找）"},
                **TRUST_SCHEMA_PROPERTIES
            },
            "required": ["node_id", "title", "trigger_verb", "trigger_noun", "trigger_context", "action_steps", "because_reason", "resolves"]
        }

    async def execute(self, node_id: str, title: str, trigger_verb: str, trigger_noun: str, trigger_context: str, action_steps: List[str], because_reason: str, prerequisites: List[str] = None, resolves: str = None, metadata_signature: Dict[str, Any] = None, confidence_score: float = None, last_verified_at: str = None, verification_source: str = None) -> str:
        try:
            lesson_struct = {
                "IF_trigger": {
                    "verb": trigger_verb,
                    "noun": trigger_noun,
                    "context": trigger_context
                },
                "THEN_action": action_steps,
                "BECAUSE_reason": because_reason
            }
            content = json.dumps(lesson_struct, ensure_ascii=False, indent=2)
            prereq_str = ",".join(prerequisites) if prerequisites else None

            # === 语义去重：写入前搜索相似 LESSON ===
            dedup_action = None
            merged_node_id = None
            if self.vault.vector_engine.is_ready:
                query_text = f"{title} {trigger_noun} {trigger_context} {resolves or ''}"
                similar = self.vault.vector_engine.search(query_text, top_k=3, threshold=0.75)
                # 批量获取候选节点的类型信息（公共 API，不直接访问 _conn）
                candidate_ids = [sid for sid, _ in similar if sid != node_id]
                candidate_briefs = self.vault.get_node_briefs(candidate_ids) if candidate_ids else {}
                for sim_id, sim_score in similar:
                    if sim_id == node_id:
                        continue
                    brief = candidate_briefs.get(sim_id)
                    if not brief or brief.get('type') != 'LESSON':
                        continue
                    if sim_score >= 0.85:
                        # 高度相似：合并到已有节点（含版本快照 + 向量重嵌入）
                        dedup_action = "merge"
                        merged_node_id = sim_id
                        self.vault.update_node_content(sim_id, content, source="reflection_merged")
                        self.vault.promote_node_confidence(sim_id, boost=0.1, max_score=0.95)
                        logger.info(f"LESSON dedup: merged [{node_id}] into [{sim_id}] (sim={sim_score:.2f})")
                        break
                    elif sim_score >= 0.65:
                        # 中等相似：创建新节点但建立关联边
                        dedup_action = "relate"
                        merged_node_id = sim_id
                        break

            if dedup_action == "merge":
                return f"♻️ LESSON [{node_id}] 与已有 [{merged_node_id}] 高度相似(>0.85)，已合并更新内容并提升置信度。"

            self.vault.create_node(
                node_id=node_id,
                ntype="LESSON",
                title=title,
                human_translation=title,
                tags="auto_managed",
                full_content=content,
                source="reflection",
                prerequisites=prereq_str,
                resolves=resolves,
                metadata_signature=metadata_signature,
                confidence_score=confidence_score,
                last_verified_at=last_verified_at,
                verification_source=verification_source,
                trust_tier="REFLECTION"
            )

            if dedup_action == "relate" and merged_node_id:
                self.vault.add_edge(node_id, merged_node_id, "RELATED_TO", weight=0.7)
                return f"✅ LESSON节点 [{node_id}] '{title}' 写入成功。检测到相似节点 [{merged_node_id}]，已建立 RELATED_TO 边。"

            return f"✅ LESSON节点 [{node_id}] '{title}' 写入成功。"
        except Exception as e:
            logger.error(f"Lesson node creation failed: {e}")
            return f"Error: {e}"


class CreateMetaNodeTool(BaseNodeTool):

    @property
    def name(self) -> str:
        return "create_meta_node"

    @property
    def description(self) -> str:
        return "创建元信息节点 (ASSET/EPISODE)。用于记录可复用产物或阶段性任务轨迹。(仅超级管理员 C 进程 有权限使用)"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "节点ID，如 ASSET_DEPLOY_SCRIPT 或 EP_TASK_DEBUG_ROUND1"},
                "ntype": {"type": "string", "enum": ["ASSET", "EPISODE"], "description": "节点类型"},
                "title": {"type": "string", "description": "节点标题"},
                "content": {"type": "string", "description": "节点完整内容"},
                "tags": {"type": "string", "description": "逗号分隔标签"},
                "resolves": {"type": "string", "description": "该资产或轨迹主要对应的问题、任务或现象", "default": ""},
                **TRUST_SCHEMA_PROPERTIES
            },
            "required": ["node_id", "ntype", "title", "content"]
        }

    async def execute(self, node_id: str, ntype: str, title: str, content: str, tags: str = "", resolves: str = "", metadata_signature: Dict[str, Any] = None, confidence_score: float = None, last_verified_at: str = None, verification_source: str = None) -> str:
        try:
            self.vault.create_node(
                node_id=node_id,
                ntype=ntype,
                title=title,
                human_translation=title,
                tags=tags,
                full_content=content,
                source="reflection_meta",
                resolves=resolves or None,
                metadata_signature=metadata_signature,
                confidence_score=confidence_score,
                last_verified_at=last_verified_at,
                verification_source=verification_source,
                trust_tier="REFLECTION"
            )
            return f"✅ {ntype}节点 [{node_id}] 创建成功。"
        except Exception as e:
            logger.error(f"Meta node creation failed: {e}")
            return f"Error: {e}"


class DeleteNodeTool(BaseNodeTool):
    """节点管理工具：删除知识节点。专属后台 C 进程权限。"""

    @property
    def name(self) -> str:
        return "delete_node"

    @property
    def description(self) -> str:
        return "删除错误或过时的节点。(仅超级管理员 C 进程 有权限使用此工具)"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "目标节点的 node_id"}
            },
            "required": ["node_id"]
        }

    async def execute(self, node_id: str) -> str:
        try:
            success = self.vault.delete_node(node_id)
            if success:
                logger.info(f"NodeVault: Deleted node [{node_id}] and its edges")
                return f"✅ 节点 [{node_id}] 及其关联边已删除。"
            return f"Error: delete_node returned False for [{node_id}]"
        except Exception as e:
            logger.error(f"Node deletion failed: {e}")
            return f"Error: {e}"


class CreateGraphNodeTool(BaseNodeTool):
    """节点管理工具：创建图谱原子节点 (Entity/Event/Action)。专属后台 C 进程权限。"""

    @property
    def name(self) -> str:
        return "create_graph_node"

    @property
    def description(self) -> str:
        return "创建图谱中的原子节点 (ENTITY/EVENT/ACTION)。(仅超级管理员 C 进程 有权限使用)"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "节点ID，格式前缀必须是 ENT_ / EVT_ / ACT_"},
                "ntype": {"type": "string", "enum": ["ENTITY", "EVENT", "ACTION"], "description": "节点类型"},
                "title": {"type": "string", "description": "节点标题/名称"},
                "content": {"type": "string", "description": "节点的详细内容或描述"},
                "tags": {"type": "string", "description": "逗号分隔的标签"},
                **TRUST_SCHEMA_PROPERTIES
            },
            "required": ["node_id", "ntype", "title", "content"]
        }

    async def execute(self, node_id: str, ntype: str, title: str, content: str, tags: str = "", metadata_signature: Dict[str, Any] = None, confidence_score: float = None, last_verified_at: str = None, verification_source: str = None) -> str:
        try:
            self.vault.create_node(
                node_id=node_id,
                ntype=ntype,
                title=title,
                human_translation=title,
                tags=tags,
                full_content=content,
                source="reflection_graph",
                metadata_signature=metadata_signature,
                confidence_score=confidence_score,
                last_verified_at=last_verified_at,
                verification_source=verification_source,
                trust_tier="REFLECTION"
            )
            return f"✅ {ntype}节点 [{node_id}] 创建成功。"
        except Exception as e:
            logger.error(f"Graph node creation failed: {e}")
            return f"Error: {e}"


class CreateNodeEdgeTool(BaseNodeTool):
    """节点管理工具：创建节点间的关联边。专属后台 C 进程权限。"""

    @property
    def name(self) -> str:
        return "create_node_edge"

    @property
    def description(self) -> str:
        return "创建两个节点之间的有向边。(仅超级管理员 C 进程 有权限使用)"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source_id": {"type": "string", "description": "源节点ID"},
                "target_id": {"type": "string", "description": "目标节点ID"},
                "relation": {
                    "type": "string", 
                    "enum": ["TRIGGERS", "RESOLVES", "REQUIRES", "LOCATED_AT", "RELATED_TO"],
                    "description": "关系类型"
                },
                "weight": {"type": "number", "description": "权重 (0.0-1.0)", "default": 1.0}
            },
            "required": ["source_id", "target_id", "relation"]
        }

    async def execute(self, source_id: str, target_id: str, relation: str, weight: float = 1.0) -> str:
        try:
            self.vault.add_edge(source_id, target_id, relation, weight)
            return f"✅ 边建立: {source_id} --[{relation}]--> {target_id}"
        except Exception as e:
            logger.error(f"Edge creation failed: {e}")
            return f"Error: {e}"
class RecordToolNodeTool(BaseNodeTool):
    """节点管理工具：记录工具节点 (TOOL_NODE)。专属后台 C 进程权限。"""

    @property
    def name(self) -> str:
        return "record_tool_node"

    @property
    def description(self) -> str:
        return "将 Python 工具源码作为 TOOL 节点记录到认知库中。(仅超级管理员 C 进程 有权限使用)"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "节点ID，格式前缀必须是 TOOL_"},
                "tool_name": {"type": "string", "description": "工具名称（小写字母和下划线）"},
                "title": {"type": "string", "description": "工具功能描述"},
                "source_code": {"type": "string", "description": "Python 源码文本，必须包含一个继承自 Tool 的类定义"},
                "tags": {"type": "string", "description": "逗号分隔的标签，如 tool,python,skill", "default": "tool,python,skill"},
                **TRUST_SCHEMA_PROPERTIES
            },
            "required": ["node_id", "tool_name", "title", "source_code"]
        }

    async def execute(self, node_id: str, tool_name: str, title: str, source_code: str, tags: str = "tool,python,skill", metadata_signature: Dict[str, Any] = None, confidence_score: float = None, last_verified_at: str = None, verification_source: str = None) -> str:
        try:
            # 验证源码是否包含 Tool 类
            if "class" not in source_code or "Tool" not in source_code:
                return "Error: 源码必须包含一个继承自 Tool 的类定义"
            
            # 创建工具节点
            self.vault.create_node(
                node_id=node_id,
                ntype="TOOL",
                title=title,
                human_translation=f"Python工具: {tool_name}",
                tags=tags,
                full_content=source_code,
                source="skill_creation",
                metadata_signature=metadata_signature,
                confidence_score=confidence_score or 0.8,
                last_verified_at=last_verified_at,
                verification_source=verification_source,
                trust_tier="REFLECTION"
            )
            
            logger.info(f"NodeVault: Recorded tool node [{node_id}] - {tool_name}")
            return f"✅ 工具节点 [{node_id}] 记录成功。工具名称: {tool_name}"
            
        except Exception as e:
            logger.error(f"Tool node recording failed: {e}")
            return f"Error: {e}"