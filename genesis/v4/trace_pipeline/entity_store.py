"""
Trace Entity Store — 持久化存储提取的实体和跨 session 聚合

SQLite 后端，与 traces.db 同目录但独立文件（trace_entities.db）。
设计原则：
  1. 每个实体保留溯源链（span_id → trace_id）
  2. 跨 session 去重：同类型+同值 = 同一个规范实体，合并出现计数
  3. 支持按类型、频率、时间范围查询
"""

import sqlite3
import logging
import time
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path
from .entity_extractor import TraceEntity, EntityType

logger = logging.getLogger(__name__)

_DB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "runtime"
_DB_PATH = _DB_DIR / "trace_entities.db"

_SCHEMA = """
-- 规范实体表：跨 session 的唯一实体
CREATE TABLE IF NOT EXISTS canonical_entities (
    entity_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type     TEXT NOT NULL,           -- EntityType.*
    value           TEXT NOT NULL,           -- 规范化后的值
    first_seen_at   REAL NOT NULL,           -- 首次发现时间
    last_seen_at    REAL NOT NULL,           -- 最近发现时间
    occurrence_count INTEGER DEFAULT 1,      -- 跨 session 出现次数
    session_count   INTEGER DEFAULT 1,       -- 出现在多少个不同 session 中
    avg_confidence  REAL DEFAULT 1.0,        -- 平均置信度
    UNIQUE(entity_type, value)
);

-- 实体出现记录：每次提取的详细溯源
CREATE TABLE IF NOT EXISTS entity_occurrences (
    occurrence_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id       INTEGER NOT NULL,        -- 关联到 canonical_entities
    span_id         TEXT NOT NULL,            -- 溯源：哪个 span
    trace_id        TEXT NOT NULL,            -- 溯源：哪个 session
    source_tool     TEXT NOT NULL,            -- 工具名
    extraction_rule TEXT NOT NULL,            -- 提取规则
    confidence      REAL NOT NULL,            -- 本次提取的置信度
    raw_fragment    TEXT,                     -- 原始文本片段
    extracted_at    REAL NOT NULL,            -- 提取时间
    FOREIGN KEY (entity_id) REFERENCES canonical_entities(entity_id)
);

-- 已处理的 trace 记录（防止重复提取）
CREATE TABLE IF NOT EXISTS processed_traces (
    trace_id        TEXT PRIMARY KEY,
    processed_at    REAL NOT NULL,
    entity_count    INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_ce_type ON canonical_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_ce_count ON canonical_entities(occurrence_count DESC);
CREATE INDEX IF NOT EXISTS idx_eo_trace ON entity_occurrences(trace_id);
CREATE INDEX IF NOT EXISTS idx_eo_entity ON entity_occurrences(entity_id);
"""


class TraceEntityStore:
    """持久化实体存储 + 跨 session 聚合"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or _DB_PATH
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_db()

    def _ensure_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=5)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def is_trace_processed(self, trace_id: str) -> bool:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM processed_traces WHERE trace_id = ?", (trace_id,)
        ).fetchone()
        return row is not None

    def store_entities(self, entities: List[TraceEntity], trace_id: str) -> int:
        """存储一批实体，返回新增的规范实体数"""
        if not entities:
            return 0

        conn = self._get_conn()
        now = time.time()
        new_canonical = 0

        try:
            # 追踪本 trace 中已见过的 entity_id（用于 session_count 去重）
            seen_entity_ids = set()
            # 追踪已存在的 entity（本 trace 首次遇到时 +1 session_count）
            session_increment_ids = set()

            for e in entities:
                # Upsert 规范实体
                existing = conn.execute(
                    "SELECT entity_id, occurrence_count, avg_confidence "
                    "FROM canonical_entities WHERE entity_type = ? AND value = ?",
                    (e.entity_type, e.value)
                ).fetchone()

                if existing:
                    entity_id = existing["entity_id"]
                    old_count = existing["occurrence_count"]
                    old_avg = existing["avg_confidence"]
                    new_avg = (old_avg * old_count + e.confidence) / (old_count + 1)
                    conn.execute(
                        "UPDATE canonical_entities SET "
                        "last_seen_at = ?, occurrence_count = occurrence_count + 1, "
                        "avg_confidence = ? WHERE entity_id = ?",
                        (now, round(new_avg, 4), entity_id)
                    )
                    # 这个 entity 在本 trace 首次出现 → 需要 +1 session_count
                    if entity_id not in seen_entity_ids:
                        session_increment_ids.add(entity_id)
                else:
                    cursor = conn.execute(
                        "INSERT INTO canonical_entities "
                        "(entity_type, value, first_seen_at, last_seen_at, "
                        "occurrence_count, session_count, avg_confidence) "
                        "VALUES (?, ?, ?, ?, 1, 1, ?)",
                        (e.entity_type, e.value, now, now, e.confidence)
                    )
                    entity_id = cursor.lastrowid
                    new_canonical += 1
                    # 新建的已经 session_count=1，不需要再 +1

                seen_entity_ids.add(entity_id)

                # 记录出现
                conn.execute(
                    "INSERT INTO entity_occurrences "
                    "(entity_id, span_id, trace_id, source_tool, "
                    "extraction_rule, confidence, raw_fragment, extracted_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (entity_id, e.source_span_id, e.source_trace_id,
                     e.source_tool, e.extraction_rule, e.confidence,
                     e.raw_fragment[:200] if e.raw_fragment else None, now)
                )

            # 批量更新 session_count
            if session_increment_ids:
                placeholders = ','.join('?' * len(session_increment_ids))
                conn.execute(
                    f"UPDATE canonical_entities SET session_count = session_count + 1 "
                    f"WHERE entity_id IN ({placeholders})",
                    list(session_increment_ids)
                )

            # 标记 trace 已处理
            conn.execute(
                "INSERT OR REPLACE INTO processed_traces (trace_id, processed_at, entity_count) "
                "VALUES (?, ?, ?)",
                (trace_id, now, len(entities))
            )

            conn.commit()
            return new_canonical

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to store entities for trace {trace_id}: {e}")
            raise

    # ── Query API ──────────────────────────────────────────────────────

    def get_top_entities(self, entity_type: Optional[str] = None,
                         limit: int = 20) -> List[Dict[str, Any]]:
        """获取最常出现的实体"""
        conn = self._get_conn()
        if entity_type:
            rows = conn.execute(
                "SELECT * FROM canonical_entities WHERE entity_type = ? "
                "ORDER BY occurrence_count DESC LIMIT ?",
                (entity_type, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM canonical_entities "
                "ORDER BY occurrence_count DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_entity_provenance(self, entity_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """获取实体的溯源记录"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM entity_occurrences WHERE entity_id = ? "
            "ORDER BY extracted_at DESC LIMIT ?",
            (entity_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_entities_in_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        """获取某个 session 中的所有实体"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT ce.*, eo.span_id, eo.source_tool, eo.extraction_rule, eo.confidence as local_confidence "
            "FROM entity_occurrences eo "
            "JOIN canonical_entities ce ON ce.entity_id = eo.entity_id "
            "WHERE eo.trace_id = ? "
            "ORDER BY eo.extracted_at",
            (trace_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_co_occurring_entities(self, entity_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """获取与某实体经常共现的其他实体（同 session 出现）"""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT ce.entity_id, ce.entity_type, ce.value, COUNT(DISTINCT eo2.trace_id) as co_count
            FROM entity_occurrences eo1
            JOIN entity_occurrences eo2 ON eo1.trace_id = eo2.trace_id AND eo1.entity_id != eo2.entity_id
            JOIN canonical_entities ce ON ce.entity_id = eo2.entity_id
            WHERE eo1.entity_id = ?
            GROUP BY ce.entity_id
            ORDER BY co_count DESC
            LIMIT ?
        """, (entity_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> Dict[str, Any]:
        """存储统计"""
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM canonical_entities").fetchone()[0]
        by_type = conn.execute(
            "SELECT entity_type, COUNT(*) as cnt FROM canonical_entities GROUP BY entity_type ORDER BY cnt DESC"
        ).fetchall()
        traces_processed = conn.execute("SELECT COUNT(*) FROM processed_traces").fetchone()[0]
        occurrences = conn.execute("SELECT COUNT(*) FROM entity_occurrences").fetchone()[0]
        return {
            "canonical_entities": total,
            "by_type": {r["entity_type"]: r["cnt"] for r in by_type},
            "traces_processed": traces_processed,
            "total_occurrences": occurrences,
        }

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
