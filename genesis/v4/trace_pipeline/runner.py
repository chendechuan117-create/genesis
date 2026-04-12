"""
Trace Pipeline Runner — 增量处理新 trace，提取实体、构建关系

两种使用方式：
  1. 从 C-Phase 调用：process_current_trace(trace_id) — 处理当前 session，轻量关系更新
  2. 独立脚本/批量：process_pending_traces() — 处理所有待处理 trace + 全量关系重建
"""

import sqlite3
import logging
import time
from typing import Dict, Any
from pathlib import Path

from .entity_extractor import TraceEntityExtractor
from .entity_store import TraceEntityStore
from .relationship_builder import TraceRelationshipBuilder

logger = logging.getLogger(__name__)

_TRACES_DB = Path(__file__).resolve().parent.parent.parent.parent / "runtime" / "traces.db"

# 每处理 N 个 trace 后重建一次 co-occurrence 关系（批量模式）
_CO_OCCURRENCE_REBUILD_INTERVAL = 50


def process_current_trace(trace_id: str) -> Dict[str, Any]:
    """处理单个 trace（从 C-Phase 调用）。提取实体 + 轻量关系更新。"""
    ext = TraceEntityExtractor()
    store = TraceEntityStore()

    try:
        if store.is_trace_processed(trace_id):
            return {"status": "skipped", "reason": "already_processed"}

        entities = ext.extract_from_trace(trace_id)
        if not entities:
            return {"status": "empty", "entity_count": 0}

        new_canonical = store.store_entities(entities, trace_id)
        summary = ext.summary(entities)

        # 轻量关系更新：只对含 ERROR 的 trace 构建 DIAGNOSED_BY
        has_errors = any(e.entity_type == "ERROR" for e in entities)
        rel_count = 0
        if has_errors:
            try:
                rb = TraceRelationshipBuilder()
                rel_count = rb.build_error_patterns()
                rb.close()
            except Exception as e:
                logger.warning(f"Relationship build failed (non-fatal): {e}")

        logger.info(
            f"Trace pipeline: {trace_id} → {len(entities)} entities "
            f"({new_canonical} new canonical), rels={rel_count}, types={summary['by_type']}"
        )

        return {
            "status": "ok",
            "entity_count": len(entities),
            "new_canonical": new_canonical,
            "new_relationships": rel_count,
            "by_type": summary["by_type"],
        }
    finally:
        store.close()


def process_pending_traces(limit: int = 100, rebuild_relationships: bool = True) -> Dict[str, Any]:
    """批量处理所有未处理的 trace + 可选全量关系重建。"""
    ext = TraceEntityExtractor()
    store = TraceEntityStore()

    try:
        conn = sqlite3.connect(str(_TRACES_DB), timeout=5)
        conn.row_factory = sqlite3.Row
        all_traces = conn.execute("""
            SELECT s.trace_id, MAX(s.started_at) as last_at
            FROM spans s
            WHERE s.span_type = 'tool_call'
              AND s.tool_name IN ('shell','read_file','write_file','web_search','list_directory')
            GROUP BY s.trace_id
            ORDER BY last_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()

        t0 = time.time()
        processed = 0
        skipped = 0
        total_entities = 0
        total_new = 0

        for row in all_traces:
            tid = row["trace_id"]
            if store.is_trace_processed(tid):
                skipped += 1
                continue

            entities = ext.extract_from_trace(tid)
            if entities:
                nc = store.store_entities(entities, tid)
                total_entities += len(entities)
                total_new += nc
            processed += 1

        # 全量关系重建（批量模式下执行）
        rel_stats = {}
        community_stats = {}
        if rebuild_relationships and processed > 0:
            try:
                rb = TraceRelationshipBuilder()
                co_new = rb.build_co_occurrence(min_sessions=2)
                err_new = rb.build_error_patterns()
                rel_stats = rb.stats()
                rb.close()
                logger.info(f"Relationships rebuilt: {co_new} CO_OCCURS, {err_new} DIAGNOSED_BY")
            except Exception as e:
                logger.warning(f"Relationship rebuild failed (non-fatal): {e}")

            # 社区检测（依赖关系图，所以在关系重建之后）
            try:
                from .community_detector import TraceCommunityDetector
                cd = TraceCommunityDetector()
                community_result = cd.detect(resolution=1.5, min_size=3)
                community_stats = {
                    "valid": community_result.get("valid_communities", 0),
                    "total": community_result.get("total_communities", 0),
                }
                cd.close()
                logger.info(f"Communities: {community_stats['valid']} valid / {community_stats['total']} total")
            except Exception as e:
                logger.warning(f"Community detection failed (non-fatal): {e}")

        # Evidence assessment: trace 证据被动评估已有 LESSON 节点
        evidence_stats = {}
        if rebuild_relationships and processed > 0:
            try:
                from .evidence_assessor import assess_evidence
                evidence_stats = assess_evidence()
            except Exception as e:
                logger.warning(f"Evidence assessment failed (non-fatal): {e}")

        elapsed = time.time() - t0
        entity_stats = store.stats()

        return {
            "processed": processed,
            "skipped": skipped,
            "total_entities": total_entities,
            "new_canonical": total_new,
            "elapsed_s": round(elapsed, 1),
            "entity_stats": entity_stats,
            "relationship_stats": rel_stats,
            "community_stats": community_stats,
            "evidence_stats": evidence_stats,
        }
    finally:
        store.close()


def generate_experience_summary(max_communities: int = 8) -> str:
    """生成紧凑的执行经验概览，用于 GP prompt 注入。

    展示 trace 网络作为程序性记忆层的全貌：
    - 经验规模（实体、关系、session 数）
    - Top 社区（功能集群）作为"我做过什么"的索引
    - 高频错误模式
    约 10-20 行，~300-600 tokens。
    """
    try:
        store = TraceEntityStore()
        stats = store.stats()
        store.close()
    except Exception:
        return ""

    if stats["canonical_entities"] < 10:
        return ""

    lines = []
    lines.append(
        f"{stats['canonical_entities']} 实体 / "
        f"{stats['total_occurrences']} 次出现 / "
        f"{stats['traces_processed']} 个 session"
    )

    # Top communities as experience areas
    try:
        from .community_detector import TraceCommunityDetector
        cd = TraceCommunityDetector()
        communities = cd.get_communities(limit=max_communities)
        if communities:
            lines.append("")
            lines.append("经验领域（功能集群）：")
            for c in communities:
                members = cd.get_community_members(c["community_id"])
                # 提取干净的标签名（去掉类型计数后缀）
                label = c["label"].split(" (")[0] if " (" in c["label"] else c["label"]
                top3 = []
                for m in members[:3]:
                    v = m["value"]
                    short = v.rsplit("/", 1)[-1] if "/" in v else v
                    if short not in top3:
                        top3.append(short[:20])
                lines.append(
                    f"  {label[:25]:25s} {c['member_count']:3d}实体 | {', '.join(top3)}"
                )
        cd.close()
    except Exception:
        pass

    # Top 3 error patterns
    try:
        store2 = TraceEntityStore()
        errors = store2.get_top_entities("ERROR", limit=3)
        if errors:
            lines.append("")
            lines.append("高频错误：")
            for err in errors:
                lines.append(f"  {err['occurrence_count']}次 | {err['value'][:60]}")
        store2.close()
    except Exception:
        pass

    return "\n".join(lines)


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    result = process_pending_traces(limit=5000)
    print(json.dumps(result, indent=2, ensure_ascii=False))
