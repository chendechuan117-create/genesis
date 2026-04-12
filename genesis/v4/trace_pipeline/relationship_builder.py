"""
Trace Relationship Builder — 从实体共现和执行序列推导关系

关系类型与置信度:
  CO_OCCURS  (0.3-0.9): 两个实体在同一 session 中出现，频率越高置信度越高
  SEQUENTIAL (0.7):     实体 A 的 span 在 B 之前执行（同 session 内）
  DIAGNOSED_BY (0.8):   错误实体 → 随后的文件/命令操作（调试模式）
  FIXED_BY   (0.85):    错误出现后，exit_code 从非0变为0（修复模式）

所有关系可溯源到具体的 trace_id 和 span_id 对。
"""

import sqlite3
import logging
import time
import math
from typing import List, Dict, Optional, Any, Tuple, Set
from pathlib import Path
from collections import defaultdict

from .entity_extractor import EntityType
from .entity_store import TraceEntityStore

logger = logging.getLogger(__name__)

_ENTITY_DB = Path(__file__).resolve().parent.parent.parent.parent / "runtime" / "trace_entities.db"


class RelationType:
    CO_OCCURS = "CO_OCCURS"         # 同 session 出现
    SEQUENTIAL = "SEQUENTIAL"       # 时间顺序（A 在 B 之前）
    DIAGNOSED_BY = "DIAGNOSED_BY"   # 错误 → 诊断操作
    FIXED_BY = "FIXED_BY"           # 错误 → 修复操作

# 关系存储 schema（扩展 trace_entities.db）
_REL_SCHEMA = """
CREATE TABLE IF NOT EXISTS entity_relationships (
    rel_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_entity_id INTEGER NOT NULL,
    target_entity_id INTEGER NOT NULL,
    rel_type        TEXT NOT NULL,
    confidence      REAL NOT NULL,
    evidence_count  INTEGER DEFAULT 1,   -- 多少个不同 session 支持这个关系
    first_seen_at   REAL NOT NULL,
    last_seen_at    REAL NOT NULL,
    UNIQUE(source_entity_id, target_entity_id, rel_type),
    FOREIGN KEY (source_entity_id) REFERENCES canonical_entities(entity_id),
    FOREIGN KEY (target_entity_id) REFERENCES canonical_entities(entity_id)
);

-- 关系的证据溯源
CREATE TABLE IF NOT EXISTS relationship_evidence (
    evidence_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    rel_id          INTEGER NOT NULL,
    trace_id        TEXT NOT NULL,
    source_span_id  TEXT,
    target_span_id  TEXT,
    created_at      REAL NOT NULL,
    FOREIGN KEY (rel_id) REFERENCES entity_relationships(rel_id)
);

CREATE INDEX IF NOT EXISTS idx_er_source ON entity_relationships(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_er_target ON entity_relationships(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_er_type ON entity_relationships(rel_type);
CREATE INDEX IF NOT EXISTS idx_re_trace ON relationship_evidence(trace_id);
"""

# 只为高信号实体类型建立关系（COMMAND 太多太杂，过滤掉）
_RELATIONSHIP_ENTITY_TYPES = frozenset([
    EntityType.FILE, EntityType.SERVICE, EntityType.ERROR,
    EntityType.PACKAGE, EntityType.DIRECTORY, EntityType.URL,
])


class TraceRelationshipBuilder:
    """从实体共现和时序模式推导关系"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or _ENTITY_DB
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=5)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _ensure_schema(self):
        conn = self._get_conn()
        conn.executescript(_REL_SCHEMA)
        conn.commit()

    def build_co_occurrence(self, min_sessions: int = 2, top_k_per_entity: int = 10) -> int:
        """
        从 entity_occurrences 表建立 CO_OCCURS 关系。
        置信度 = log2(共现session数) / log2(max_session_count)，归一化到 [0.3, 0.9]。
        只对 _RELATIONSHIP_ENTITY_TYPES 中的实体类型建关系。
        """
        conn = self._get_conn()
        now = time.time()

        # 找所有共现对（同 trace_id 中出现的不同实体）
        # 限制：只看高信号类型，且两个实体都至少出现在 min_sessions 个 session 中
        pairs = conn.execute("""
            SELECT
                eo1.entity_id as src_id,
                eo2.entity_id as tgt_id,
                COUNT(DISTINCT eo1.trace_id) as co_sessions
            FROM entity_occurrences eo1
            JOIN entity_occurrences eo2
                ON eo1.trace_id = eo2.trace_id
                AND eo1.entity_id < eo2.entity_id
            JOIN canonical_entities ce1 ON ce1.entity_id = eo1.entity_id
            JOIN canonical_entities ce2 ON ce2.entity_id = eo2.entity_id
            WHERE ce1.entity_type IN ({types})
              AND ce2.entity_type IN ({types})
              AND ce1.session_count >= ?
              AND ce2.session_count >= ?
            GROUP BY eo1.entity_id, eo2.entity_id
            HAVING co_sessions >= ?
            ORDER BY co_sessions DESC
        """.format(types=','.join(f"'{t}'" for t in _RELATIONSHIP_ENTITY_TYPES)),
            (min_sessions, min_sessions, min_sessions)
        ).fetchall()

        if not pairs:
            return 0

        # 归一化置信度
        max_co = max(p["co_sessions"] for p in pairs)
        log_max = math.log2(max_co + 1)

        new_rels = 0
        for p in pairs:
            raw_conf = math.log2(p["co_sessions"] + 1) / log_max if log_max > 0 else 0.5
            confidence = 0.3 + raw_conf * 0.6  # 映射到 [0.3, 0.9]

            existing = conn.execute(
                "SELECT rel_id, evidence_count FROM entity_relationships "
                "WHERE source_entity_id = ? AND target_entity_id = ? AND rel_type = ?",
                (p["src_id"], p["tgt_id"], RelationType.CO_OCCURS)
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE entity_relationships SET confidence = ?, "
                    "evidence_count = ?, last_seen_at = ? WHERE rel_id = ?",
                    (round(confidence, 3), p["co_sessions"], now, existing["rel_id"])
                )
            else:
                conn.execute(
                    "INSERT INTO entity_relationships "
                    "(source_entity_id, target_entity_id, rel_type, confidence, "
                    "evidence_count, first_seen_at, last_seen_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (p["src_id"], p["tgt_id"], RelationType.CO_OCCURS,
                     round(confidence, 3), p["co_sessions"], now, now)
                )
                new_rels += 1

        conn.commit()
        logger.info(f"CO_OCCURS: {len(pairs)} pairs evaluated, {new_rels} new relationships")
        return new_rels

    def build_error_patterns(self) -> int:
        """
        检测 DIAGNOSED_BY 模式：ERROR 实体出现后，同 session 中的后续 FILE 操作。
        检测 FIXED_BY 模式：ERROR 后 exit_code 从非0变为0。
        """
        conn = self._get_conn()
        now = time.time()
        new_rels = 0

        # 找所有有 ERROR 实体的 session
        error_sessions = conn.execute("""
            SELECT DISTINCT eo.trace_id, eo.entity_id, eo.span_id,
                   ce.value as error_value
            FROM entity_occurrences eo
            JOIN canonical_entities ce ON ce.entity_id = eo.entity_id
            WHERE ce.entity_type = 'ERROR'
        """).fetchall()

        for err in error_sessions:
            # 找同 session 中 ERROR 之后出现的 FILE/SERVICE 实体
            followups = conn.execute("""
                SELECT DISTINCT eo2.entity_id, ce2.entity_type, ce2.value, eo2.span_id
                FROM entity_occurrences eo_err
                JOIN entity_occurrences eo2
                    ON eo_err.trace_id = eo2.trace_id
                    AND eo2.entity_id != eo_err.entity_id
                JOIN canonical_entities ce2 ON ce2.entity_id = eo2.entity_id
                WHERE eo_err.entity_id = ?
                  AND eo_err.trace_id = ?
                  AND ce2.entity_type IN ('FILE', 'SERVICE', 'PACKAGE')
                  AND eo2.extracted_at >= eo_err.extracted_at
            """, (err["entity_id"], err["trace_id"])).fetchall()

            for fu in followups:
                rel_type = RelationType.DIAGNOSED_BY
                existing = conn.execute(
                    "SELECT rel_id, evidence_count FROM entity_relationships "
                    "WHERE source_entity_id = ? AND target_entity_id = ? AND rel_type = ?",
                    (err["entity_id"], fu["entity_id"], rel_type)
                ).fetchone()

                if existing:
                    conn.execute(
                        "UPDATE entity_relationships SET evidence_count = evidence_count + 1, "
                        "last_seen_at = ? WHERE rel_id = ?",
                        (now, existing["rel_id"])
                    )
                    rel_id = existing["rel_id"]
                else:
                    cursor = conn.execute(
                        "INSERT INTO entity_relationships "
                        "(source_entity_id, target_entity_id, rel_type, confidence, "
                        "evidence_count, first_seen_at, last_seen_at) "
                        "VALUES (?, ?, ?, 0.75, 1, ?, ?)",
                        (err["entity_id"], fu["entity_id"], rel_type, now, now)
                    )
                    rel_id = cursor.lastrowid
                    new_rels += 1

                # 记录证据
                conn.execute(
                    "INSERT INTO relationship_evidence "
                    "(rel_id, trace_id, source_span_id, target_span_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (rel_id, err["trace_id"], err["span_id"], fu["span_id"], now)
                )

        conn.commit()
        logger.info(f"Error patterns: {new_rels} new DIAGNOSED_BY relationships")
        return new_rels

    # ── Query API ──────────────────────────────────────────────────────

    def get_related(self, entity_id: int, rel_type: Optional[str] = None,
                    limit: int = 20) -> List[Dict[str, Any]]:
        """获取与某实体相关的所有实体"""
        conn = self._get_conn()
        type_clause = "AND er.rel_type = ?" if rel_type else ""
        params: list = [entity_id, entity_id, entity_id, entity_id, entity_id]
        if rel_type:
            params.append(rel_type)
        params.append(limit)

        rows = conn.execute(f"""
            SELECT
                er.rel_id, er.rel_type, er.confidence, er.evidence_count,
                CASE WHEN er.source_entity_id = ? THEN er.target_entity_id
                     ELSE er.source_entity_id END as related_entity_id,
                CASE WHEN er.source_entity_id = ? THEN 'outgoing' ELSE 'incoming' END as direction,
                ce.entity_type, ce.value, ce.occurrence_count, ce.session_count
            FROM entity_relationships er
            JOIN canonical_entities ce ON ce.entity_id = (
                CASE WHEN er.source_entity_id = ? THEN er.target_entity_id
                     ELSE er.source_entity_id END
            )
            WHERE (er.source_entity_id = ? OR er.target_entity_id = ?)
            {type_clause}
            ORDER BY er.evidence_count DESC
            LIMIT ?
        """, params).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> Dict[str, Any]:
        """关系统计"""
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM entity_relationships").fetchone()[0]
        by_type = conn.execute(
            "SELECT rel_type, COUNT(*) as cnt, AVG(confidence) as avg_conf, SUM(evidence_count) as total_evidence "
            "FROM entity_relationships GROUP BY rel_type ORDER BY cnt DESC"
        ).fetchall()
        evidence_count = conn.execute("SELECT COUNT(*) FROM relationship_evidence").fetchone()[0]
        return {
            "total_relationships": total,
            "by_type": {r["rel_type"]: {
                "count": r["cnt"],
                "avg_confidence": round(r["avg_conf"], 3),
                "total_evidence": r["total_evidence"],
            } for r in by_type},
            "total_evidence": evidence_count,
        }

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
