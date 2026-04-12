"""
Evidence Assessor — trace 证据自动评估已有 LESSON 节点的一致性

灵感来自 Hindsight (arxiv 2512.12818) 的 Opinion Reinforcement：
  当新事实到来 → 评估与已有信念的关系 → {reinforce, weaken, neutral}

与 Arena 的区别：
  - Arena: 节点被 **使用** 后，按任务成功/失败调节 confidence
  - Evidence Assessor: 被动观察 trace 证据，即使节点 **没被使用**，
    也能通过统计趋势发现它是否仍然有效

运行时机：batch trace processing 之后（process_pending_traces）
"""

import sqlite3
import logging
import time
import re
from typing import Dict, Any, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# 评估参数
_RECENCY_DAYS = 7          # "最近" 的定义：7天
_MIN_RESOLVES_LEN = 5      # resolves 字段最短有效长度
_MAX_ADJUSTMENTS = 20      # 单次运行最多调整的节点数


def assess_evidence() -> Dict[str, Any]:
    """主入口：评估 trace 证据对已有 LESSON 的影响。

    Returns:
        {"reinforced": [...], "weakened": [...], "neutral_count": int}
    """
    try:
        from genesis.v4.manager import DB_PATH, _LEGACY_DB_PATH
        vault_path = DB_PATH if DB_PATH.exists() else _LEGACY_DB_PATH
        if not vault_path.exists():
            return {"error": "vault_not_found"}
    except ImportError:
        return {"error": "import_failed"}

    from .entity_store import TraceEntityStore

    store = TraceEntityStore()
    vault_conn = sqlite3.connect(str(vault_path), timeout=5)
    vault_conn.row_factory = sqlite3.Row

    try:
        # 1. 获取所有有 resolves 字段的 LESSON 节点
        lessons = vault_conn.execute("""
            SELECT node_id, title, resolves,
                   usage_success_count, usage_fail_count
            FROM knowledge_nodes
            WHERE type = 'LESSON'
              AND resolves IS NOT NULL
              AND LENGTH(resolves) >= ?
              AND node_id NOT LIKE 'MEM_CONV%'
        """, (_MIN_RESOLVES_LEN,)).fetchall()

        if not lessons:
            store.close()
            vault_conn.close()
            return {"reinforced": [], "weakened": [], "neutral_count": 0}

        # 2. 获取最近的 ERROR 实体（含时间信息）
        now = time.time()
        recent_cutoff = now - _RECENCY_DAYS * 86400
        trace_conn = store._get_conn()

        recent_errors = trace_conn.execute("""
            SELECT entity_id, value, last_seen_at, occurrence_count, session_count
            FROM canonical_entities
            WHERE entity_type = 'ERROR'
            ORDER BY occurrence_count DESC
        """).fetchall()

        # 建立错误文本索引（用于模糊匹配 LESSON.resolves）
        error_index = []
        for err in recent_errors:
            error_index.append({
                "value": err["value"],
                "last_seen_at": err["last_seen_at"],
                "occurrence_count": err["occurrence_count"],
                "session_count": err["session_count"],
                "is_recent": err["last_seen_at"] >= recent_cutoff,
            })

        # 3. 逐个 LESSON 评估
        reinforced = []
        weakened = []
        neutral_count = 0

        for lesson in lessons:
            resolves_text = lesson["resolves"].lower()
            node_id = lesson["node_id"]

            # 找到匹配的错误实体
            matched_errors = _match_errors(resolves_text, error_index)

            if not matched_errors:
                neutral_count += 1
                continue

            # 评估逻辑
            verdict = _assess_match(matched_errors, recent_cutoff)

            if verdict == "reinforce" and len(reinforced) < _MAX_ADJUSTMENTS:
                # 证据支持：节点声称解决的错误最近未出现 → 记录为 usage success
                vault_conn.execute(
                    "UPDATE knowledge_nodes SET usage_success_count = usage_success_count + 1, updated_at = CURRENT_TIMESTAMP WHERE node_id = ?",
                    (node_id,)
                )
                reinforced.append({
                    "node_id": node_id,
                    "title": lesson["title"][:50],
                    "reason": "resolved_error_not_seen_recently",
                })

            elif verdict == "weaken" and len(weakened) < _MAX_ADJUSTMENTS:
                # 保护高战绩节点：Arena 已验证的不被被动证据削弱
                wins = lesson["usage_success_count"] or 0
                fails = lesson["usage_fail_count"] or 0
                if wins >= 5 and wins / max(wins + fails, 1) >= 0.8:
                    neutral_count += 1
                    continue
                # 证据矛盾：节点声称解决的错误仍频繁出现 → 记录为 usage fail
                vault_conn.execute(
                    "UPDATE knowledge_nodes SET usage_fail_count = usage_fail_count + 1, updated_at = CURRENT_TIMESTAMP WHERE node_id = ?",
                    (node_id,)
                )
                weakened.append({
                    "node_id": node_id,
                    "title": lesson["title"][:50],
                    "reason": "resolved_error_still_frequent",
                })
            else:
                neutral_count += 1

        vault_conn.commit()

        if reinforced or weakened:
            logger.info(
                f"Evidence assessment: reinforced={len(reinforced)} "
                f"weakened={len(weakened)} neutral={neutral_count}"
            )

        return {
            "reinforced": reinforced,
            "weakened": weakened,
            "neutral_count": neutral_count,
        }

    except Exception as e:
        logger.warning(f"Evidence assessment failed (non-fatal): {e}")
        return {"error": str(e)}
    finally:
        store.close()
        vault_conn.close()


def _match_errors(resolves_text: str, error_index: List[Dict]) -> List[Dict]:
    """模糊匹配 LESSON.resolves 与 ERROR 实体"""
    # 从 resolves 提取关键词（至少3字符的词）
    keywords = set()
    for token in re.split(r'[\s,;:]+', resolves_text):
        token = token.strip().lower()
        if len(token) >= 3 and token not in {"the", "and", "for", "not", "error", "failed"}:
            keywords.add(token)

    if not keywords:
        return []

    matched = []
    for err in error_index:
        err_lower = err["value"].lower()
        # 要求至少匹配 2 个关键词（防止单词碰撞导致误匹配）
        hit_count = sum(1 for kw in keywords if kw in err_lower)
        if hit_count >= min(2, len(keywords)):
            matched.append(err)
    return matched


def _assess_match(matched_errors: List[Dict], recent_cutoff: float) -> str:
    """根据匹配的错误模式评估 reinforce/weaken/neutral

    - 所有匹配错误都不在最近出现 → reinforce（LESSON 生效了）
    - 大部分匹配错误最近仍在出现且频率高 → weaken（LESSON 没有效果）
    - 混合信号 → neutral
    """
    if not matched_errors:
        return "neutral"

    recent_count = sum(1 for e in matched_errors if e["is_recent"])
    total = len(matched_errors)

    # 没有一个匹配的错误最近出现 → LESSON 生效
    if recent_count == 0:
        return "reinforce"

    # 超过一半的匹配错误最近仍在出现 → LESSON 可能失效
    if recent_count > total * 0.5:
        # 额外条件：这些错误要足够频繁才算"矛盾"
        avg_sessions = sum(e["session_count"] for e in matched_errors if e["is_recent"]) / max(recent_count, 1)
        if avg_sessions >= 3:
            return "weaken"

    return "neutral"
