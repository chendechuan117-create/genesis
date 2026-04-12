"""
Node Cleanup — 基于使用数据清理垃圾节点

策略（保守优先，不误删有价值节点）：
  1. 硬删除：从未使用 + 超龄 + 非 HUMAN tier → 直接删除
  2. 统计报告：不做任何修改，只输出清理建议

2026-04 重构：移除 confidence_score 衰减。
知识不会因时间流逝失效，只会因事件失效。
淘汰信号来自：usage_fail > usage_success / epoch_stale / CONTRADICTS 边。
"""

import sqlite3
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_PATH = Path.home() / ".genesis" / "workshop_v4.sqlite"

_DELETE_AGE_DAYS = 7           # 超过多少天未使用才考虑删除


def _cutoff_iso(days: int) -> str:
    """生成 N 天前的 ISO 日期字符串"""
    import datetime
    return (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def analyze(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """分析节点质量分布，不做修改。返回清理建议。"""
    db = sqlite3.connect(str(db_path or _DB_PATH))
    db.row_factory = sqlite3.Row

    total = db.execute("SELECT COUNT(*) FROM knowledge_nodes").fetchone()[0]
    cutoff = _cutoff_iso(_DELETE_AGE_DAYS)

    healthy = db.execute("""
        SELECT COUNT(*) FROM knowledge_nodes WHERE usage_count > 0
    """).fetchone()[0]

    never_used = db.execute("""
        SELECT COUNT(*) FROM knowledge_nodes WHERE usage_count = 0
    """).fetchone()[0]

    # 删除候选：未使用 + 超龄 + 非 HUMAN
    delete_candidates = db.execute("""
        SELECT COUNT(*) FROM knowledge_nodes
        WHERE usage_count = 0
          AND trust_tier NOT IN ('HUMAN')
          AND created_at < ?
          AND node_id NOT LIKE 'MEM_CONV%'
    """, (cutoff,)).fetchone()[0]

    # 失败率高的节点（需要修正而非删除）
    failing = db.execute("""
        SELECT COUNT(*) FROM knowledge_nodes
        WHERE usage_fail_count > 0 AND usage_fail_count > usage_success_count
    """).fetchone()[0]

    # 按类型分布（未使用）
    unused_by_type = db.execute("""
        SELECT type, COUNT(*) as cnt
        FROM knowledge_nodes WHERE usage_count = 0
        GROUP BY type ORDER BY cnt DESC
    """).fetchall()

    db.close()

    return {
        "total_nodes": total,
        "healthy_used": healthy,
        "never_used": never_used,
        "delete_candidates": delete_candidates,
        "failing_nodes": failing,
        "unused_by_type": {r["type"]: r["cnt"] for r in unused_by_type},
    }


def cleanup(dry_run: bool = True, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    执行清理：删除未使用 + 超龄 + 非 HUMAN 的节点。
    dry_run=True 时只报告不执行。
    """
    db = sqlite3.connect(str(db_path or _DB_PATH))
    db.row_factory = sqlite3.Row
    cutoff = _cutoff_iso(_DELETE_AGE_DAYS)

    to_delete = db.execute("""
        SELECT node_id, type, title
        FROM knowledge_nodes
        WHERE usage_count = 0
          AND trust_tier NOT IN ('HUMAN')
          AND created_at < ?
          AND node_id NOT LIKE 'MEM_CONV%'
    """, (cutoff,)).fetchall()

    deleted_ids = [r["node_id"] for r in to_delete]

    if not dry_run and deleted_ids:
        placeholders = ','.join('?' * len(deleted_ids))
        db.execute(f"DELETE FROM node_contents WHERE node_id IN ({placeholders})", deleted_ids)
        db.execute(f"DELETE FROM node_edges WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})",
                   deleted_ids + deleted_ids)
        db.execute(f"DELETE FROM knowledge_nodes WHERE node_id IN ({placeholders})", deleted_ids)
        db.commit()
        logger.info(f"Hard deleted {len(deleted_ids)} unused nodes (age > {_DELETE_AGE_DAYS}d)")

    db.close()

    return {
        "dry_run": dry_run,
        "hard_deleted": len(deleted_ids),
        "deleted_samples": [{"id": r["node_id"], "type": r["type"], "title": r["title"][:60]} for r in to_delete[:5]],
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)

    print("=== ANALYSIS ===")
    analysis = analyze()
    print(json.dumps(analysis, indent=2, ensure_ascii=False))

    print("\n=== DRY RUN ===")
    result = cleanup(dry_run=True)
    print(json.dumps(result, indent=2, ensure_ascii=False))
