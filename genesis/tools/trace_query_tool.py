"""
Trace Query Tool — 让 G 查询执行轨迹中提取的结构化知识

查询模式：
  1. entity_search: 按类型/关键词搜索实体
  2. related: 查看某实体的关联实体（共现 + 因果）
  3. history: 查看某文件/服务的历史操作轨迹
  4. errors: 查看最常见的错误模式及其诊断路径
"""

import logging
from typing import Dict, Any

from genesis.core.base import Tool
from genesis.v4.trace_pipeline.entity_store import TraceEntityStore
from genesis.v4.trace_pipeline.relationship_builder import TraceRelationshipBuilder

logger = logging.getLogger(__name__)


class TraceQueryTool(Tool):
    """查询执行轨迹中提取的结构化实体和关系"""

    @property
    def name(self) -> str:
        return "trace_query"

    @property
    def description(self) -> str:
        return (
            "回忆 Genesis 的执行经验（程序性记忆）。不同于知识库中的声明式知识，"
            "这里存储的是系统实际做过什么、什么和什么一起出现过、错误怎么处理的。"
            "用 recall 模式获取某个话题的完整关联记忆，用 search 精确查找实体。"
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["recall", "search", "related", "errors", "communities", "stats"],
                    "description": (
                        "查询模式: "
                        "recall=联想记忆（推荐首选，给定话题返回完整关联上下文）, "
                        "search=精确搜索实体, "
                        "related=查看某实体的关联, "
                        "errors=查看错误模式及诊断路径, "
                        "communities=查看功能集群, "
                        "stats=统计"
                    )
                },
                "query": {
                    "type": "string",
                    "description": "搜索关键词（mode=search 时使用）"
                },
                "entity_type": {
                    "type": "string",
                    "enum": ["FILE", "SERVICE", "ERROR", "PACKAGE", "DIRECTORY", "URL", "COMMAND", "EXIT_CODE"],
                    "description": "限定实体类型（可选）"
                },
                "entity_id": {
                    "type": "integer",
                    "description": "实体 ID（mode=related 时使用，从 search 结果获取）"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量上限，默认 10"
                }
            },
            "required": ["mode"]
        }

    async def execute(self, mode: str, query: str = "", entity_type: str = None,
                      entity_id: int = None, limit: int = 10, **kwargs) -> str:
        store = TraceEntityStore()
        rb = TraceRelationshipBuilder()

        try:
            if mode == "recall":
                return self._do_recall(store, rb, query, limit)
            elif mode == "search":
                return self._do_search(store, query, entity_type, limit)
            elif mode == "related":
                return self._do_related(store, rb, entity_id, entity_type, limit)
            elif mode == "errors":
                return self._do_errors(store, rb, limit)
            elif mode == "communities":
                return self._do_communities(query, entity_id, limit)
            elif mode == "stats":
                return self._do_stats(store, rb)
            else:
                return f"未知模式: {mode}。可用: search, related, errors, communities, stats"
        except Exception as e:
            logger.error(f"trace_query failed: {e}")
            return f"查询失败: {e}"
        finally:
            store.close()
            rb.close()

    def _do_recall(self, store: TraceEntityStore, rb: TraceRelationshipBuilder,
                   query: str, limit: int) -> str:
        """联想记忆：给定话题，返回完整的关联上下文叙事"""
        if not query:
            return "请提供 query（话题关键词），例如 trace_query(mode='recall', query='v2ray')"

        conn = store._get_conn()
        like = f"%{query}%"

        # 1. 找所有匹配实体，按出现频率排序
        entities = conn.execute("""
            SELECT entity_id, entity_type, value, occurrence_count, session_count
            FROM canonical_entities WHERE value LIKE ?
            ORDER BY occurrence_count DESC LIMIT ?
        """, (like, 30)).fetchall()

        if not entities:
            return f"没有关于 '{query}' 的执行经验。"

        # 按类型分组
        by_type = {}
        for e in entities:
            by_type.setdefault(e["entity_type"], []).append(e)

        lines = [f"=== 关于 '{query}' 的执行经验 ===\n"]

        # 2. 概览：涉及的实体类型和数量
        type_summary = ", ".join(f"{len(v)} {k}" for k, v in by_type.items())
        total_sessions = max((e["session_count"] for e in entities), default=0)
        lines.append(f"涉及 {len(entities)} 个实体（{type_summary}），跨 {total_sessions} 个 session\n")

        # 3. 核心实体（取 top 5 高频）
        top_entities = entities[:5]
        lines.append("── 核心实体 ──")
        for e in top_entities:
            short = e["value"].rsplit("/", 1)[-1] if "/" in e["value"] else e["value"]
            lines.append(f"  [{e['entity_type']:10s}] {short[:50]:50s} ({e['occurrence_count']}次/{e['session_count']}session)")

        # 4. 关联网络：取 top 3 实体的关系
        lines.append("\n── 关联记忆 ──")
        seen_related = set()
        for e in top_entities[:3]:
            rels = rb.get_related(e["entity_id"], limit=8)
            if not rels:
                continue
            short_name = e["value"].rsplit("/", 1)[-1] if "/" in e["value"] else e["value"][:40]
            for r in rels:
                rval = r["value"].rsplit("/", 1)[-1] if "/" in r["value"] else r["value"][:50]
                key = (r["related_entity_id"], e["entity_id"])
                if key in seen_related or r["related_entity_id"] in {x["entity_id"] for x in entities[:10]}:
                    continue
                seen_related.add(key)
                rel_label = {"CO_OCCURS": "共现", "DIAGNOSED_BY": "诊断"}.get(r["rel_type"], r["rel_type"])
                lines.append(
                    f"  {short_name[:25]:25s} ─{rel_label}─ [{r['entity_type']:8s}] {rval[:40]} (evidence={r['evidence_count']})"
                )
            if len(seen_related) >= 12:
                break

        # 5. 错误模式：matching ERROR entities + their diagnostic paths
        error_entities = by_type.get("ERROR", [])
        if error_entities:
            lines.append("\n── 历史错误 & 处理方式 ──")
            for err in error_entities[:3]:
                lines.append(f"  ⚠ {err['value'][:70]} ({err['occurrence_count']}次)")
                diag = rb.get_related(err["entity_id"], rel_type="DIAGNOSED_BY", limit=3)
                for d in diag:
                    if d["direction"] == "outgoing":
                        dval = d["value"].rsplit("/", 1)[-1] if "/" in d["value"] else d["value"][:50]
                        lines.append(f"    → [{d['entity_type']:8s}] {dval}")

        # 6. 功能集群：找 top 实体所属社区
        try:
            from genesis.v4.trace_pipeline.community_detector import TraceCommunityDetector
            cd = TraceCommunityDetector()
            community_shown = False
            for e in top_entities[:2]:
                comm = cd.find_entity_community(e["entity_id"])
                if comm and not community_shown:
                    members = cd.get_community_members(comm["community_id"])
                    others = [m for m in members if query.lower() not in m["value"].lower()][:5]
                    if others:
                        lines.append(f"\n── 所属功能集群: {comm['label'][:40]} ({comm['member_count']} 成员) ──")
                        for m in others:
                            mval = m["value"].rsplit("/", 1)[-1] if "/" in m["value"] else m["value"][:50]
                            lines.append(f"  [{m['entity_type']:10s}] {mval}")
                        community_shown = True
            cd.close()
        except Exception:
            pass

        # 7. Cross-reference: 相关的声明式知识（NodeVault LESSON）
        try:
            from genesis.v4.manager import DB_PATH, _LEGACY_DB_PATH
            vault_path = DB_PATH if DB_PATH.exists() else _LEGACY_DB_PATH
            if vault_path.exists():
                import sqlite3 as _sql
                vconn = _sql.connect(str(vault_path), timeout=3)
                vconn.row_factory = _sql.Row
                lessons = vconn.execute("""
                    SELECT node_id, title, usage_success_count, usage_fail_count
                    FROM knowledge_nodes
                    WHERE type IN ('LESSON', 'CONTEXT', 'ASSET')
                      AND (title LIKE ? OR tags LIKE ?)
                    ORDER BY usage_success_count DESC
                    LIMIT 5
                """, (like, like)).fetchall()
                vconn.close()
                if lessons:
                    lines.append("\n── 相关声明式知识（NodeVault） ──")
                    for l in lessons:
                        win = l["usage_success_count"] or 0
                        fail = l["usage_fail_count"] or 0
                        record = f"  win={win}/{win+fail} | {l['title'][:60]}"
                        lines.append(record)
                    lines.append("  → 用 get_knowledge_node_content 查看详情")
        except Exception:
            pass

        return "\n".join(lines)

    def _do_search(self, store: TraceEntityStore, query: str,
                   entity_type: str, limit: int) -> str:
        if not query and not entity_type:
            return "请提供 query（关键词）或 entity_type（实体类型）"

        conn = store._get_conn()

        if query:
            # 模糊搜索
            like_pattern = f"%{query}%"
            type_clause = "AND entity_type = ?" if entity_type else ""
            params = [like_pattern]
            if entity_type:
                params.append(entity_type)
            params.append(limit)

            rows = conn.execute(f"""
                SELECT entity_id, entity_type, value, occurrence_count, session_count,
                       avg_confidence
                FROM canonical_entities
                WHERE value LIKE ? {type_clause}
                ORDER BY occurrence_count DESC
                LIMIT ?
            """, params).fetchall()
        else:
            rows = conn.execute("""
                SELECT entity_id, entity_type, value, occurrence_count, session_count,
                       avg_confidence
                FROM canonical_entities
                WHERE entity_type = ?
                ORDER BY occurrence_count DESC
                LIMIT ?
            """, (entity_type, limit)).fetchall()

        if not rows:
            return f"未找到匹配 '{query or entity_type}' 的实体"

        lines = [f"找到 {len(rows)} 个实体：\n"]
        for r in rows:
            lines.append(
                f"  [ID:{r['entity_id']}] [{r['entity_type']:10s}] "
                f"出现{r['occurrence_count']}次/{r['session_count']}个session "
                f"conf={r['avg_confidence']:.2f} | {r['value'][:80]}"
            )
        lines.append(f"\n💡 用 trace_query(mode='related', entity_id=<ID>) 查看关联实体")
        return "\n".join(lines)

    def _do_related(self, store: TraceEntityStore, rb: TraceRelationshipBuilder,
                    entity_id: int, rel_type: str, limit: int) -> str:
        if entity_id is None:
            return "请提供 entity_id（从 search 结果获取）"

        # 先获取实体本身信息
        conn = store._get_conn()
        entity = conn.execute(
            "SELECT * FROM canonical_entities WHERE entity_id = ?", (entity_id,)
        ).fetchone()
        if not entity:
            return f"实体 ID {entity_id} 不存在"

        rels = rb.get_related(entity_id, rel_type=rel_type, limit=limit)

        lines = [
            f"实体: [{entity['entity_type']}] {entity['value'][:80]}",
            f"出现 {entity['occurrence_count']} 次 / {entity['session_count']} 个 session\n",
        ]

        if not rels:
            lines.append("暂无已发现的关联关系")
            # 回退到共现查询
            co = store.get_co_occurring_entities(entity_id, limit=limit)
            if co:
                lines.append(f"\n共现实体（同 session 出现）：")
                for c in co:
                    lines.append(
                        f"  {c['co_count']:3d}x [{c['entity_type']:10s}] {c['value'][:70]}"
                    )
        else:
            # 按关系类型分组
            by_type = {}
            for r in rels:
                by_type.setdefault(r["rel_type"], []).append(r)

            for rtype, items in by_type.items():
                label = {
                    "CO_OCCURS": "经常一起出现",
                    "DIAGNOSED_BY": "诊断/处理方式",
                    "FIXED_BY": "修复方式",
                    "SEQUENTIAL": "时序关联",
                }.get(rtype, rtype)
                lines.append(f"── {label} ({rtype}) ──")
                for r in items:
                    direction = "→" if r["direction"] == "outgoing" else "←"
                    lines.append(
                        f"  {direction} [{r['entity_type']:10s}] evidence={r['evidence_count']:3d} "
                        f"conf={r['confidence']:.2f} | {r['value'][:60]}"
                    )
                lines.append("")

        return "\n".join(lines)

    def _do_errors(self, store: TraceEntityStore, rb: TraceRelationshipBuilder,
                   limit: int) -> str:
        errors = store.get_top_entities("ERROR", limit=limit)
        if not errors:
            return "暂无错误记录"

        lines = [f"最常见的 {len(errors)} 个错误模式：\n"]
        for err in errors:
            lines.append(
                f"  [{err['occurrence_count']:3d}x / {err['session_count']} sessions] "
                f"{err['value'][:80]}"
            )
            # 获取诊断路径
            rels = rb.get_related(err["entity_id"], rel_type="DIAGNOSED_BY", limit=3)
            diagnosed = [r for r in rels if r["direction"] == "outgoing"]
            if diagnosed:
                for d in diagnosed:
                    lines.append(
                        f"    → [{d['entity_type']:10s}] evidence={d['evidence_count']:3d} | {d['value'][:60]}"
                    )
            lines.append("")

        return "\n".join(lines)

    def _do_communities(self, query: str, entity_id: int, limit: int) -> str:
        from genesis.v4.trace_pipeline.community_detector import TraceCommunityDetector
        cd = TraceCommunityDetector()
        try:
            # 如果提供了 entity_id，找该实体所属社区
            if entity_id is not None:
                community = cd.find_entity_community(entity_id)
                if not community:
                    return f"实体 ID {entity_id} 不属于任何已检测到的社区"
                members = cd.get_community_members(community["community_id"])
                lines = [
                    f"社区: {community['label']}",
                    f"成员: {community['member_count']} 个, 证据强度: {community['total_evidence']}\n",
                ]
                for m in members[:20]:
                    lines.append(
                        f"  centrality={m['centrality']:.3f} [{m['entity_type']:10s}] {m['value'][:70]}"
                    )
                if len(members) > 20:
                    lines.append(f"  ... +{len(members)-20} more")
                return "\n".join(lines)

            # 如果提供了 query，搜索匹配的社区
            communities = cd.get_communities(limit=50)
            if query:
                query_lower = query.lower()
                communities = [c for c in communities if query_lower in c["label"].lower()]

            if not communities:
                return f"未找到匹配 '{query}' 的社区" if query else "暂无社区数据（需要先运行批量处理）"

            lines = [f"功能集群（{len(communities[:limit])} 个）：\n"]
            for c in communities[:limit]:
                members = cd.get_community_members(c["community_id"])
                top3 = [m["value"].rsplit("/", 1)[-1] if "/" in m["value"] else m["value"]
                        for m in members[:3]]
                lines.append(
                    f"  [{c['label'][:40]:40s}] {c['member_count']:3d} members, "
                    f"evidence={c['total_evidence']:5d} | {' + '.join(top3)}"
                )
            lines.append(f"\n💡 用 trace_query(mode='communities', entity_id=<ID>) 查看某实体所属集群的详细成员")
            return "\n".join(lines)
        finally:
            cd.close()

    def _do_stats(self, store: TraceEntityStore, rb: TraceRelationshipBuilder) -> str:
        es = store.stats()
        rs = rb.stats()

        lines = [
            "=== 轨迹知识库统计 ===\n",
            f"规范实体: {es['canonical_entities']}",
            f"处理的 session: {es['traces_processed']}",
            f"总出现记录: {es['total_occurrences']}",
            f"\n实体类型分布:"
        ]
        for etype, cnt in es["by_type"].items():
            lines.append(f"  {etype:12s}: {cnt}")

        lines.append(f"\n关系: {rs['total_relationships']} 条")
        for rtype, info in rs.get("by_type", {}).items():
            lines.append(
                f"  {rtype:15s}: {info['count']} (avg_conf={info['avg_confidence']:.2f}, evidence={info['total_evidence']})"
            )

        return "\n".join(lines)
