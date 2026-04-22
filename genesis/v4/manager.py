"""
Genesis V4 - 认知装配师 (The Factory Manager G)
核心：节点是标题，内容用链接联通。G 看标题，Op 看内容。
"""

import json
import sqlite3
import functools
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
from genesis.v4.vector_engine import VectorEngine
from genesis.v4.signature_engine import SignatureEngine
from genesis.v4.knowledge_query import KnowledgeQuery, normalize_node_dict
from genesis.v4.environment_mixin import EnvironmentEpochMixin
from genesis.v4.arena_mixin import ArenaConfidenceMixin

logger = logging.getLogger(__name__)

DB_PATH = Path.home() / '.genesis' / 'workshop_v4.sqlite'
_LEGACY_DB_PATH = Path.home() / '.nanogenesis' / 'workshop_v4.sqlite'

# ── Trust Tier 出生证系统 ──────────────────────────────────
# 每个知识节点携带不可伪造的来源水印，决定其初始信任和执行权限。
TRUST_TIERS = ("HUMAN", "REFLECTION", "FERMENTED", "SCAVENGED", "CONVERSATION")
TRUST_TIER_RANK = {"HUMAN": 4, "REFLECTION": 3, "FERMENTED": 2, "SCAVENGED": 1, "CONVERSATION": 0}
TOOL_EXEC_MIN_TIER = "REFLECTION"  # TOOL 节点 exec() 最低信任等级

KNOWLEDGE_STATES = ("current", "unverified", "historical")

# ── 签名常量从 signature_constants.py 统一导入 ──────────────────────
from genesis.v4.signature_constants import (  # noqa: E402
    METADATA_SIGNATURE_FIELDS,
    METADATA_SCHEMA_VERSION,
    METADATA_SCHEMA_VERSION_FIELD,
    _VALIDATION_STATUS_ALIASES,
    _KNOWLEDGE_STATE_ALIASES,
    _INVALIDATION_REASON_ALIASES,
    _DIM_OPERATIONAL_BLACKLIST,
    _DIM_MIN_FREQ,
    _MAX_CUSTOM_DIMS_PER_NODE,
    _CORE_FIELDS_SET,
    _PROTECTED_METADATA_FIELDS,
    _ENVIRONMENT_SCOPE_ALIASES,
)

class NodeVault(EnvironmentEpochMixin, ArenaConfidenceMixin):
    """万物皆节点库 — 双层架构（索引 + 内容）, 单例模式"""
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(NodeVault, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_path: Path = DB_PATH, skip_vector_engine: bool = False):
        if self._initialized:
            return
        self.db_path = db_path
        # 自动迁移：首次使用新路径时，从旧 ~/.nanogenesis/ 拷贝过来（原文件保留作备份）
        if not self.db_path.exists() and _LEGACY_DB_PATH.exists():
            import shutil
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(_LEGACY_DB_PATH), str(self.db_path))
            logger.info(f"NodeVault: migrated {_LEGACY_DB_PATH} → {self.db_path} (legacy backup kept)")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 持久连接 + WAL 模式（读写不阻塞）
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        
        self._ensure_schema()
        self._migrate_old_data()
        
        # 启动并加载向量引擎（守护进程可跳过以节省内存和启动时间）
        if skip_vector_engine:
            self.vector_engine = VectorEngine()  # 空壳，is_ready=False
            self._last_matrix_sync = "2000-01-01 00:00:00"
            logger.info("NodeVault: skip_vector_engine=True, 跳过嵌入模型加载")
        else:
            self.vector_engine = VectorEngine()
            self.vector_engine.initialize()
            self._load_embeddings_to_memory()
            self._last_matrix_sync: str = self._get_db_now()
        self._initialized = True
        self.signature = SignatureEngine(self._conn, vault=self)
        self.signature.initialize()
        self.query = KnowledgeQuery(self._conn)

    def _get_db_now(self) -> str:
        """SQLite CURRENT_TIMESTAMP 的 Python 等价"""
        row = self._conn.execute("SELECT datetime('now')").fetchone()
        return row[0] if row else "2000-01-01 00:00:00"

    def _load_embeddings_to_memory(self):
        rows = self._conn.execute("SELECT node_id, embedding FROM knowledge_nodes WHERE embedding IS NOT NULL AND node_id NOT LIKE 'MEM_CONV%'").fetchall()
        self.vector_engine.load_matrix([dict(r) for r in rows])

    def sync_vector_matrix_incremental(self) -> int:
        """
        心跳驱动的增量同步：只加载上次同步以来新增/更新的向量。
        解决跨进程不同步：后台守护进程写入的新节点向量
        能被主循环进程及时看到，而不需要重启。
        返回同步的节点数。
        """
        if not self.vector_engine or not self.vector_engine.is_ready:
            return 0
        rows = self._conn.execute(
            "SELECT node_id, embedding FROM knowledge_nodes "
            "WHERE embedding IS NOT NULL AND node_id NOT LIKE 'MEM_CONV%' "
            "AND updated_at > ?",
            (self._last_matrix_sync,)
        ).fetchall()
        if not rows:
            return 0
        import json as _json
        items = []
        for r in rows:
            try:
                vec = _json.loads(r['embedding'])
                items.append((r['node_id'], vec))
            except Exception:
                pass
        if items:
            self.vector_engine.add_to_matrix_batch(items)
        synced = len(items)
        self._last_matrix_sync = self._get_db_now()
        if synced:
            logger.debug(f"VectorSync: 增量同步 {synced} 个向量 (since {self._last_matrix_sync})")
            self.signature._build_dimension_registry()  # 新节点可能带来新的自定义维度
        return synced

    def _ensure_schema(self):
        """建立双层表结构 + 图谱边表"""
        conn = self._conn
        conn.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_nodes (
            node_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            human_translation TEXT NOT NULL,
            tags TEXT,
            prerequisites TEXT,
            resolves TEXT,
            parent_node_id TEXT,
            metadata_signature TEXT,
            embedding TEXT,
            usage_count INTEGER DEFAULT 0,
            usage_success_count INTEGER DEFAULT 0,
            usage_fail_count INTEGER DEFAULT 0,
            confidence_score REAL DEFAULT 0.55,
            last_verified_at TIMESTAMP,
            verification_source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        for col in [
            ('prerequisites', 'TEXT'),
            ('resolves', 'TEXT'),
            ('parent_node_id', 'TEXT'),
            ('metadata_signature', 'TEXT'),
            ('embedding', 'TEXT'),
            ('usage_success_count', 'INTEGER DEFAULT 0'),
            ('usage_fail_count', 'INTEGER DEFAULT 0'),
            ('confidence_score', 'REAL DEFAULT 0.55'),
            ('last_verified_at', 'TIMESTAMP'),
            ('verification_source', 'TEXT'),
            ('trust_tier', 'TEXT DEFAULT \'REFLECTION\''),
            ('epistemic_status', 'TEXT DEFAULT \'BELIEF\'')
        ]:
            try:
                conn.execute(f"ALTER TABLE knowledge_nodes ADD COLUMN {col[0]} {col[1]}")
            except sqlite3.OperationalError:
                pass
        # One-time backfill: promote qualified nodes from default BELIEF
        try:
            has_facts = conn.execute(
                "SELECT 1 FROM knowledge_nodes WHERE epistemic_status = 'FACT' LIMIT 1"
            ).fetchone()
            if not has_facts:
                # epistemic_status backfill removed (2026-04 restructure: field phased out)
                conn.commit()
        except Exception:
            pass
        # 心跳水位线：进程间协调表
        conn.execute('''
        CREATE TABLE IF NOT EXISTS process_heartbeat (
            process_name TEXT PRIMARY KEY,
            status TEXT DEFAULT 'idle',
            last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_summary TEXT DEFAULT '',
            pid INTEGER,
            extra TEXT
        )
        ''')
        conn.execute('''
        CREATE TABLE IF NOT EXISTS node_contents (
            node_id TEXT PRIMARY KEY,
            full_content TEXT NOT NULL,
            source TEXT DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (node_id) REFERENCES knowledge_nodes(node_id)
        )
        ''')
        # 版本链：节点编辑历史
        conn.execute('''
        CREATE TABLE IF NOT EXISTS node_versions (
            version_id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            title TEXT,
            full_content TEXT,
            metadata_signature TEXT,
            confidence_score REAL,
            trust_tier TEXT,
            source TEXT,
            epistemic_status TEXT,
            snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (node_id) REFERENCES knowledge_nodes(node_id)
        )
        ''')
        try:
            conn.execute("ALTER TABLE node_versions ADD COLUMN epistemic_status TEXT")
        except sqlite3.OperationalError:
            pass
        # 新增：图谱边表 (Experience Graph Edges)
        conn.execute('''
        CREATE TABLE IF NOT EXISTS node_edges (
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            relation TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (source_id, target_id, relation),
            FOREIGN KEY (source_id) REFERENCES knowledge_nodes(node_id),
            FOREIGN KEY (target_id) REFERENCES knowledge_nodes(node_id)
        )
        ''')
        # 签名推断自学习表：C-Phase 偏差检测发现的新 marker
        conn.execute('''
        CREATE TABLE IF NOT EXISTS learned_signature_markers (
            dim_key TEXT NOT NULL,
            marker_value TEXT NOT NULL,
            source_persona TEXT DEFAULT 'c_phase',
            hit_count INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (dim_key, marker_value)
        )
        ''')
        # Persona 学习持久化表（Multi-G Arena 跨重启记忆）
        conn.execute('''
        CREATE TABLE IF NOT EXISTS persona_stats (
            persona TEXT NOT NULL,
            task_kind TEXT NOT NULL DEFAULT '',
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (persona, task_kind)
        )
        ''')
        # VOID 任务队列（从 knowledge_nodes 分离，不污染知识搜索空间）
        conn.execute('''
        CREATE TABLE IF NOT EXISTS void_tasks (
            void_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            source TEXT DEFAULT 'search_miss',
            persona TEXT,
            task_signature TEXT,
            status TEXT DEFAULT 'open',
            resolution_node_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP
        )
        ''')
        conn.execute('''
        CREATE TABLE IF NOT EXISTS environment_epochs (
            epoch_id TEXT PRIMARY KEY,
            scope TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            origin TEXT DEFAULT 'manual',
            snapshot_summary TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            superseded_at TIMESTAMP
        )
        ''')
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_environment_epochs_scope_status "
            "ON environment_epochs(scope, status, created_at)"
        )
        # ── 推理线表（点线面架构）：独立于 edges，存储因果推理链 ──
        conn.execute('''
        CREATE TABLE IF NOT EXISTS reasoning_lines (
            line_id TEXT PRIMARY KEY,
            new_point_id TEXT NOT NULL,
            basis_point_id TEXT NOT NULL,
            reasoning TEXT NOT NULL,
            source TEXT DEFAULT 'C',
            trace_id TEXT,
            round_seq INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reasoning_lines_new_point "
            "ON reasoning_lines(new_point_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reasoning_lines_basis_point "
            "ON reasoning_lines(basis_point_id)"
        )
        # V2: reasoning_lines 加 source 列（存量DB兼容）
        try:
            conn.execute("ALTER TABLE reasoning_lines ADD COLUMN source TEXT DEFAULT 'C'")
        except sqlite3.OperationalError:
            pass  # 列已存在
        conn.commit()

    def _migrate_old_data(self):
        """兼容旧版 schema（带 machine_payload 列的非常老的版本）"""
        conn = self._conn
        with conn:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(knowledge_nodes)").fetchall()]
            if 'machine_payload' in cols and 'title' not in cols:
                logger.info("NodeVault: Migrating old schema → new dual-layer schema...")
                # Rename old table
                conn.execute("ALTER TABLE knowledge_nodes RENAME TO _old_nodes")
                # Create new schema
                conn.execute('''
                CREATE TABLE knowledge_nodes (
                    node_id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    human_translation TEXT NOT NULL,
                    tags TEXT,
                    prerequisites TEXT,
                    resolves TEXT,
                    metadata_signature TEXT,
                    embedding TEXT,
                    usage_count INTEGER DEFAULT 0,
                    confidence_score REAL DEFAULT 0.55,
                    last_verified_at TIMESTAMP,
                    verification_source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                conn.execute('''
                CREATE TABLE IF NOT EXISTS node_contents (
                    node_id TEXT PRIMARY KEY,
                    full_content TEXT NOT NULL,
                    source TEXT DEFAULT 'system',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (node_id) REFERENCES knowledge_nodes(node_id)
                )
                ''')
                # Migrate data: extract a short title from machine_payload
                rows = conn.execute("SELECT node_id, type, machine_payload, human_translation, tags, usage_count FROM _old_nodes").fetchall()
                for r in rows:
                    try:
                        payload = json.loads(r[2])
                        title = payload.get("name", r[0])
                    except:
                        title = r[0]
                    conn.execute(
                        "INSERT OR IGNORE INTO knowledge_nodes (node_id, type, title, human_translation, tags, usage_count) VALUES (?,?,?,?,?,?)",
                        (r[0], r[1], title, r[3], r[4], r[5])
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO node_contents (node_id, full_content, source) VALUES (?,?,?)",
                        (r[0], r[2], "migrated_from_v4.0")
                    )
                conn.execute("DROP TABLE _old_nodes")
                conn.commit()
                logger.info(f"NodeVault: Migrated {len(rows)} nodes to dual-layer schema.")

    # ─── Environment Epoch methods → environment_mixin.py ───
    # ─── Confidence/Reliability/Arena methods → arena_mixin.py ───

    def patch_node_metadata(self, node_id: str, **kwargs) -> bool:
        """统一的节点元数据补丁接口（daemon/工具共用）。
        
        支持的字段：trust_tier, verification_source,
        metadata_signature, last_verified_at。
        签名自动经过 normalize_metadata_signature 标准化。
        """
        allowed = {"trust_tier", "verification_source",
                    "metadata_signature", "last_verified_at"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return False
        if "metadata_signature" in updates:
            verification_source = str(updates.get("verification_source") or "").strip()
            if not verification_source:
                row = self._conn.execute(
                    "SELECT verification_source FROM knowledge_nodes WHERE node_id = ?",
                    (node_id,)
                ).fetchone()
                verification_source = str(row["verification_source"] if row else "").strip()
            sig = updates["metadata_signature"]
            if isinstance(sig, str):
                try:
                    sig = json.loads(sig)
                except Exception:
                    sig = {}
            if isinstance(sig, dict):
                inferred_reason = self.signature.infer_invalidation_reason(sig, verification_source=verification_source)
                if inferred_reason and not self.signature.resolve_invalidation_reason(sig):
                    sig = dict(sig)
                    sig["invalidation_reason"] = inferred_reason
            sig = self.signature.normalize(sig)
            updates["metadata_signature"] = json.dumps(sig, ensure_ascii=False)
        if "trust_tier" in updates:
            valid_tiers = {"HUMAN", "REFLECTION", "FERMENTED", "SCAVENGED", "CONVERSATION"}
            if updates["trust_tier"] not in valid_tiers:
                logger.warning(f"patch_node_metadata: invalid trust_tier '{updates['trust_tier']}', ignoring")
                del updates["trust_tier"]
        if not updates:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [node_id]
        try:
            self._conn.execute(f"UPDATE knowledge_nodes SET {set_clause} WHERE node_id = ?", values)
            self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"patch_node_metadata failed for {node_id}: {e}")
            return False

    VERSION_KEEP_LIMIT = 5

    def _snapshot_if_exists(self, node_id: str):
        """如果节点已存在，保存当前版本到 node_versions，并 GC 超限旧版本"""
        try:
            row = self._conn.execute(
                "SELECT k.title, c.full_content, k.metadata_signature, k.confidence_score, k.trust_tier, c.source, k.epistemic_status "
                "FROM knowledge_nodes k LEFT JOIN node_contents c ON k.node_id = c.node_id "
                "WHERE k.node_id = ?", (node_id,)
            ).fetchone()
            if row:
                self._conn.execute(
                    "INSERT INTO node_versions (node_id, title, full_content, metadata_signature, confidence_score, trust_tier, source, epistemic_status) VALUES (?,?,?,?,?,?,?,?)",
                    (node_id, row["title"], row["full_content"], row["metadata_signature"], row["confidence_score"], row["trust_tier"], row["source"], row["epistemic_status"])
                )
                self._conn.execute(
                    "DELETE FROM node_versions WHERE node_id = ? AND version_id NOT IN "
                    "(SELECT version_id FROM node_versions WHERE node_id = ? ORDER BY snapshot_at DESC LIMIT ?)",
                    (node_id, node_id, self.VERSION_KEEP_LIMIT)
                )
        except Exception as e:
            logger.debug(f"Version snapshot skipped for {node_id}: {e}")

    def get_node_versions(self, node_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取节点的编辑历史（最新在前）"""
        rows = self._conn.execute(
            "SELECT version_id, node_id, title, confidence_score, trust_tier, source, epistemic_status, snapshot_at FROM node_versions WHERE node_id = ? ORDER BY snapshot_at DESC LIMIT ?",
            (node_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def load_persona_stats(self) -> Dict[str, Dict[str, Any]]:
        """启动时加载 persona 学习数据。返回两个 dict: global_stats, task_stats"""
        global_stats = {}
        task_stats = {}
        try:
            rows = self._conn.execute(
                "SELECT persona, task_kind, wins, losses FROM persona_stats"
            ).fetchall()
            for r in rows:
                persona, tk, wins, losses = r['persona'], r['task_kind'], r['wins'], r['losses']
                if not tk:
                    global_stats[persona] = {"wins": wins, "losses": losses}
                else:
                    task_stats[f"{persona}:{tk}"] = {"wins": wins, "losses": losses}
            if global_stats:
                logger.info(f"PersonaStats: loaded {len(global_stats)} personas, {len(task_stats)} task entries")
        except Exception as e:
            logger.debug(f"PersonaStats: load failed (table may not exist yet): {e}")
        return global_stats, task_stats

    def save_persona_stats(self, global_stats: Dict[str, Dict[str, int]], task_stats: Dict[str, Dict[str, int]]):
        """持久化 persona 学习数据（增量 upsert）"""
        try:
            for persona, s in global_stats.items():
                self._conn.execute(
                    "INSERT OR REPLACE INTO persona_stats (persona, task_kind, wins, losses, updated_at) VALUES (?, '', ?, ?, CURRENT_TIMESTAMP)",
                    (persona, s["wins"], s["losses"])
                )
            for key, s in task_stats.items():
                parts = key.split(":", 1)
                if len(parts) == 2:
                    self._conn.execute(
                        "INSERT OR REPLACE INTO persona_stats (persona, task_kind, wins, losses, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                        (parts[0], parts[1], s["wins"], s["losses"])
                    )
            self._conn.commit()
        except Exception as e:
            logger.error(f"PersonaStats: save failed: {e}")

    def add_void_task(self, void_id: str, query: str, source: str = "search_miss",
                      persona: str = None, task_signature: Dict[str, Any] = None) -> bool:
        """写入一个 VOID 任务（知识缺口）。返回 True 表示新增，False 表示已存在。"""
        sig_json = json.dumps(task_signature, ensure_ascii=False) if task_signature else None
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO void_tasks (void_id, query, source, persona, task_signature) VALUES (?,?,?,?,?)",
                (void_id, query, source, persona, sig_json)
            )
            self._conn.commit()
            return self._conn.total_changes > 0
        except Exception as e:
            logger.debug(f"add_void_task failed for {void_id}: {e}")
            return False

    def get_open_voids(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取待处理的 VOID 任务（open 状态，最旧优先）"""
        rows = self._conn.execute(
            "SELECT void_id, query, source, persona, task_signature, created_at FROM void_tasks WHERE status = 'open' ORDER BY created_at ASC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_voids(self, limit: int = 5) -> List[Dict[str, Any]]:
        """最近 VOID → 委托给 KnowledgeQuery"""
        return self.query.get_recent_voids(limit)

    def resolve_void(self, void_id: str, resolution_node_id: str = None):
        """标记 VOID 已解决（被升格为 LESSON 或已过时）"""
        self._conn.execute(
            "UPDATE void_tasks SET status = 'resolved', resolution_node_id = ?, resolved_at = CURRENT_TIMESTAMP WHERE void_id = ?",
            (resolution_node_id, void_id)
        )
        self._conn.commit()

    def stale_void(self, void_id: str):
        """标记 VOID 已过时（不再需要追踪）"""
        self._conn.execute(
            "UPDATE void_tasks SET status = 'stale' WHERE void_id = ?",
            (void_id,)
        )
        self._conn.commit()

    def void_exists(self, void_id: str) -> bool:
        """检查 VOID 是否已存在（任何状态）"""
        row = self._conn.execute(
            "SELECT 1 FROM void_tasks WHERE void_id = ?", (void_id,)
        ).fetchone()
        return row is not None

    def get_void_stats(self) -> Dict[str, int]:
        """VOID 统计（供 digest/heartbeat）"""
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM void_tasks GROUP BY status"
        ).fetchall()
        return {r['status']: r['cnt'] for r in rows}

    def heartbeat(self, process_name: str, status: str = "running", summary: str = "", extra: Dict[str, Any] = None):
        """写入当前进程心跳"""
        import os
        extra_json = json.dumps(extra, ensure_ascii=False) if extra else None
        self._conn.execute(
            "INSERT OR REPLACE INTO process_heartbeat (process_name, status, last_heartbeat, last_summary, pid, extra) VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?, ?)",
            (process_name, status, summary, os.getpid(), extra_json)
        )
        self._conn.commit()

    def get_heartbeats(self) -> List[Dict[str, Any]]:
        """心跳状态 → 委托给 KnowledgeQuery"""
        return self.query.get_heartbeats()

    def get_daemon_status_summary(self) -> str:
        """守护进程摘要 → 委托给 KnowledgeQuery"""
        return self.query.get_daemon_status_summary()

    def touch_node(self, node_id: str):
        """标记节点为近期活跃（更新 updated_at），用于去重合并、PATTERN 累积等场景。"""
        try:
            self._conn.execute(
                "UPDATE knowledge_nodes SET updated_at = CURRENT_TIMESTAMP WHERE node_id = ?",
                (node_id,)
            )
            self._conn.commit()
        except Exception as e:
            logger.warning(f"touch_node failed for {node_id}: {e}")

    def add_edge(self, source_id: str, target_id: str, relation: str, weight: float = 1.0):
        """添加一条图谱边 (Idempotent)"""
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO node_edges (source_id, target_id, relation, weight) VALUES (?,?,?,?)",
                (source_id, target_id, relation, weight)
            )
            self._conn.commit()
            logger.debug(f"Graph: Added edge {source_id} --[{relation}]--> {target_id}")
        except Exception as e:
            logger.error(f"Failed to add edge: {e}")

    # ── 推理线（点线面架构）────────────────────────────────────────

    def add_reasoning_line(self, new_point_id: str, basis_point_id: str,
                           reasoning: str, source: str = 'C',
                           trace_id: str = None,
                           round_seq: int = 0) -> str:
        """写入一条推理线：new_point 基于 basis_point 产生，reasoning 是判断依据。
        source: 'GP' 或 'C'，标记线的产出者。
        返回 line_id。"""
        import hashlib as _hl
        raw = f"{new_point_id}|{basis_point_id}|{reasoning[:80]}"
        line_id = f"LINE_{_hl.md5(raw.encode()).hexdigest()[:10].upper()}"
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO reasoning_lines "
                "(line_id, new_point_id, basis_point_id, reasoning, source, trace_id, round_seq) "
                "VALUES (?,?,?,?,?,?,?)",
                (line_id, new_point_id, basis_point_id, reasoning, source, trace_id, round_seq)
            )
            self._conn.commit()
            logger.debug(f"Line: {new_point_id} ← {basis_point_id} ({reasoning[:60]}) [source={source}]")
        except Exception as e:
            logger.error(f"Failed to add reasoning line: {e}")
        return line_id

    def get_incoming_line_count(self, point_id: str) -> int:
        """获取一个点的入线数（被多少新点基于它产生）。后台价值信号，GP不可见。"""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM reasoning_lines WHERE basis_point_id = ?",
            (point_id,)
        ).fetchone()
        return row[0] if row else 0

    def get_outgoing_lines(self, point_id: str) -> List[Dict[str, Any]]:
        """获取一个点产生的所有出线（它基于哪些旧点产生）。因果部分，GP可见。"""
        rows = self._conn.execute(
            "SELECT line_id, basis_point_id, reasoning, trace_id, round_seq, created_at "
            "FROM reasoning_lines WHERE new_point_id = ? ORDER BY created_at",
            (point_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_incoming_lines(self, point_id: str) -> List[Dict[str, Any]]:
        """获取一个点的所有入线（哪些新点基于它产生）。因果部分，GP可见。"""
        rows = self._conn.execute(
            "SELECT line_id, new_point_id, reasoning, trace_id, round_seq, created_at "
            "FROM reasoning_lines WHERE basis_point_id = ? ORDER BY created_at",
            (point_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def expand_surface(self, seed_ids: List[str], context_budget: int = 25000) -> Dict[str, Any]:
        """面扩散：从种子点沿推导链BFS扩散，到context_budget时摸石头过河替换。

        返回:
          - points: 面中的点列表 [{node_id, title, type, depth, is_frontier}]
          - frontiers: 边缘点（面最外层，下一步可替换入面的候选）
          - voids: 扩散过程中遇到的空洞（无出线的方向）
        """
        from collections import deque

        # BFS 扩散
        visited = {}  # node_id → depth
        frontier = deque()  # (node_id, depth)
        voids = []

        # 初始化种子点
        for sid in seed_ids:
            visited[sid] = 0
            frontier.append((sid, 0))

        # 估算每个点占用的token数（标题+类型≈50, 内容≈500）
        TOKENS_PER_BRIEF = 50
        TOKENS_PER_CONTENT = 500
        used_tokens = 0
        phase = "expand"  # expand → replace

        while frontier and used_tokens < context_budget:
            current_id, depth = frontier.popleft()

            # 获取节点简要信息
            brief = self.get_node_briefs([current_id]).get(current_id)
            if not brief:
                continue

            if phase == "expand":
                used_tokens += TOKENS_PER_BRIEF
            else:
                # 替换阶段：用内容替换标题
                used_tokens += TOKENS_PER_CONTENT

            # 沿推导链扩散：找出 current_id 作为 basis 的出线
            # 即：哪些新点是基于 current_id 产生的
            # V2: 过滤 INSIGHT_ 虚拟标记（不在 knowledge_nodes 中的死胡同）
            outgoing = self._conn.execute(
                "SELECT rl.new_point_id FROM reasoning_lines rl "
                "WHERE rl.basis_point_id = ? "
                "AND (rl.new_point_id NOT LIKE 'INSIGHT_%' OR rl.new_point_id IN (SELECT node_id FROM knowledge_nodes))",
                (current_id,)
            ).fetchall()

            # 也沿现有边扩散（REQUIRES/TRIGGERS/RESOLVES 为强边）
            edge_neighbors = self._conn.execute(
                "SELECT target_id FROM node_edges WHERE source_id = ? "
                "AND relation IN ('REQUIRES', 'TRIGGERS', 'RESOLVES')",
                (current_id,)
            ).fetchall()

            neighbors = set(r[0] for r in outgoing) | set(r[0] for r in edge_neighbors)

            if not neighbors and depth > 0:
                voids.append(current_id)

            for nid in neighbors:
                if nid not in visited:
                    visited[nid] = depth + 1
                    frontier.append((nid, depth + 1))

            # 到达预算 60% 时切换到替换阶段
            if phase == "expand" and used_tokens > context_budget * 0.6:
                phase = "replace"
                # 摸石头过河：把深度0的种子点标记为可替换
                break

        # 构建结果
        briefs = self.get_node_briefs(list(visited.keys()))
        points = []
        frontiers = []
        for nid, depth in visited.items():
            b = briefs.get(nid, {})
            entry = {
                "node_id": nid,
                "title": b.get("title", nid),
                "type": b.get("type", "?"),
                "depth": depth,
                "is_frontier": False,
            }
            points.append(entry)
            # 边缘点：深度最大且有未访问邻居的
            if depth == max(visited.values()) if visited else 0:
                entry["is_frontier"] = True
                frontiers.append(entry)

        return {
            "points": points,
            "frontiers": frontiers,
            "voids": voids,
            "used_tokens": used_tokens,
            "phase": phase,
        }

    def delete_node(self, node_id: str) -> bool:
        """物理删除一个节点及其所有关联数据（统一删除入口）"""
        try:
            self._conn.execute("DELETE FROM node_edges WHERE source_id = ? OR target_id = ?", (node_id, node_id))
            self._conn.execute("DELETE FROM node_versions WHERE node_id = ?", (node_id,))
            self._conn.execute("DELETE FROM node_contents WHERE node_id = ?", (node_id,))
            self._conn.execute("DELETE FROM reasoning_lines WHERE new_point_id = ? OR basis_point_id = ?", (node_id, node_id))
            self._conn.execute("DELETE FROM knowledge_nodes WHERE node_id = ?", (node_id,))
            self._conn.commit()
            if self.vector_engine and node_id in getattr(self.vector_engine, 'node_ids', []):
                try:
                    idx = self.vector_engine.node_ids.index(node_id)
                    self.vector_engine.node_ids.pop(idx)
                    if self.vector_engine.matrix is not None and len(self.vector_engine.matrix) > idx:
                        import numpy as np
                        self.vector_engine.matrix = np.delete(self.vector_engine.matrix, idx, axis=0)
                except (ValueError, IndexError):
                    pass
            return True
        except Exception as e:
            logger.error(f"Failed to delete node {node_id}: {e}")
            return False

    def purge_forgotten_knowledge(self, days_threshold: int = 7) -> int:
        """
        垃圾回收 (GC)：
        清理未使用过且超过 `days_threshold` 天的节点（排除 HUMAN tier）。
        返回清理的节点数量。
        """
        query = f"""
            SELECT node_id FROM knowledge_nodes
            WHERE usage_count = 0
            AND trust_tier NOT IN ('HUMAN')
            AND created_at < datetime('now', '-{days_threshold} days')
            AND node_id NOT LIKE 'MEM_CONV%'
        """
        rows = self._conn.execute(query).fetchall()

        deleted_count = 0
        for r in rows:
            node_id = r['node_id']
            if self.delete_node(node_id):
                deleted_count += 1

        if deleted_count > 0:
            logger.info(f"NodeVault GC: Purged {deleted_count} forgotten/unused low-confidence nodes.")

        return deleted_count

    def update_node_content(self, node_id: str, full_content: str, source: str = "reflection_merged") -> bool:
        """统一的节点内容更新接口（含版本快照 + 向量重嵌入）。

        用于 LESSON 合并等需要覆写节点完整内容的场景。
        自动调用 _snapshot_if_exists 保存旧版本，更新后重新生成向量嵌入。
        """
        try:
            self._snapshot_if_exists(node_id)
            self._conn.execute(
                "UPDATE node_contents SET full_content = ?, source = ? WHERE node_id = ?",
                (full_content, source, node_id)
            )
            self._conn.commit()
            if self.vector_engine.is_ready:
                row = self._conn.execute(
                    "SELECT title, tags FROM knowledge_nodes WHERE node_id = ?", (node_id,)
                ).fetchone()
                if row:
                    embed_text = f"{row['title']} {row['tags']} {full_content}"
                    vec = self.vector_engine.encode(embed_text)
                    if vec is not None:
                        self._conn.execute(
                            "UPDATE knowledge_nodes SET embedding = ? WHERE node_id = ?",
                            (json.dumps(vec.tolist()), node_id)
                        )
                        self._conn.commit()
                        self.vector_engine.add_to_matrix(node_id, vec.tolist())
            return True
        except Exception as e:
            logger.error(f"update_node_content failed for {node_id}: {e}")
            return False

    def create_node_edge(self, source_id: str, target_id: str, relation: str, weight: float = 0.5) -> bool:
        """统一的边创建接口（daemon/工具共用）。"""
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO node_edges (source_id, target_id, relation, weight) VALUES (?,?,?,?)",
                (source_id, target_id, relation, weight)
            )
            self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"create_node_edge failed ({source_id} -> {target_id}): {e}")
            return False

    def query_nodes(self, where_clause: str, params: tuple = (), limit: int = 10) -> list:
        """通用节点查询接口。自动排除 MEM_CONV，返回 dict 列表。

        where_clause 可包含 ORDER BY，会被自动拆分到正确位置。
        """
        order_by = ""
        upper = where_clause.upper()
        order_idx = upper.find("ORDER BY")
        if order_idx != -1:
            order_by = " " + where_clause[order_idx:]
            where_clause = where_clause[:order_idx].strip()
        if not where_clause:
            where_clause = "1=1"
        sql = (f"SELECT node_id, type, title, tags, resolves, confidence_score, trust_tier, "
               f"metadata_signature, created_at, last_verified_at, verification_source, "
               f"usage_count, usage_success_count, usage_fail_count "
               f"FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%' AND ({where_clause})"
               f"{order_by} LIMIT ?")
        rows = self._conn.execute(sql, (*params, limit)).fetchall()
        return [normalize_node_dict(dict(r)) for r in rows]

    def get_related_nodes(self, node_id: str, relation: str = None, direction: str = "out") -> List[Dict[str, Any]]:
        """获取与指定节点相连的节点 (1-hop)
        direction: 'out' (source=node_id), 'in' (target=node_id), 'both'
        """
        conn = self._conn
        query = ""
        params = []

        if direction == "out":
            query = """
                SELECT ne.relation, ne.weight, kn.node_id, kn.type AS ntype, kn.title, kn.tags,
                       kn.confidence_score, kn.trust_tier, kn.usage_count
                FROM node_edges ne
                JOIN knowledge_nodes kn ON ne.target_id = kn.node_id
                WHERE ne.source_id = ?
            """
            params.append(node_id)
        elif direction == "in":
            query = """
                SELECT ne.relation, ne.weight, kn.node_id, kn.type AS ntype, kn.title, kn.tags,
                       kn.confidence_score, kn.trust_tier, kn.usage_count
                FROM node_edges ne
                JOIN knowledge_nodes kn ON ne.source_id = kn.node_id
                WHERE ne.target_id = ?
            """
            params.append(node_id)
        
        if relation:
            query += " AND ne.relation = ?"
            params.append(relation)
            
        rows = conn.execute(query, tuple(params)).fetchall()
        return [normalize_node_dict(dict(r)) for r in rows]

    # ─── G 侧接口 ───

    def get_digest(self, top_k: int = 4) -> str:
        """精简认知目录 → 委托给 KnowledgeQuery"""
        return self.query.get_digest(top_k)

    def generate_map(self, max_clusters_per_type: int = 8, titles_per_cluster: int = 3) -> str:
        """分层标签地图 → 委托给 KnowledgeQuery"""
        return self.query.generate_map(max_clusters_per_type, titles_per_cluster)

    def generate_l1_digest(self, max_nodes: int = 20) -> str:
        """L1 压缩知识摘要（freshness-aware）→ 委托给 KnowledgeQuery"""
        return self.query.generate_l1_digest(max_nodes)

    def get_all_titles(self) -> str:
        """给 G 看的极轻量目录卡片（排除对话记忆节点，记忆走单独通道）"""
        rows = self._conn.execute(
            "SELECT node_id, type, title, tags, prerequisites, resolves, metadata_signature, confidence_score, last_verified_at, verification_source, updated_at FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%' ORDER BY usage_count DESC"
        ).fetchall()
        lines = ["[元信息节点目录]"]
        for r in rows:
            reqs = f" | reqs:[{r['prerequisites']}]" if r['prerequisites'] else ""
            res = f" | resolves:[{r['resolves']}]" if r['resolves'] else ""
            sig = self.signature.render(r['metadata_signature'])
            sig_text = f" | sig:{sig}" if sig else ""
            reliability = self.build_reliability_profile(dict(r))
            trust_text = f" | trust:{reliability['confidence_score']:.2f}/{reliability['freshness_label']}"
            lines.append(f"<{r['type']}> [{r['node_id']}] {r['title']} | tags:{r['tags']}{reqs}{res}{sig_text}{trust_text}")
        return "\n".join(lines)

    def get_recent_memory(self, limit: int = 5) -> str:
        """短期记忆 → 委托给 KnowledgeQuery"""
        return self.query.get_recent_memory(limit)

    def get_conversation_digest(self, limit: int = 10) -> str:
        """对话摘要 digest → 委托给 KnowledgeQuery"""
        return self.query.get_conversation_digest(limit)

    @staticmethod
    def _extract_conversation_topic(content: str, max_chars: int = 250) -> str:
        """话题摘要提取 → 委托给 KnowledgeQuery"""
        return KnowledgeQuery._extract_conversation_topic(content, max_chars)

    def translate_nodes(self, node_ids: List[str]) -> Dict[str, str]:
        """B 面翻译 → 委托给 KnowledgeQuery"""
        return self.query.translate_nodes(node_ids)

    def get_node_briefs(self, node_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """节点元数据 → 委托给 KnowledgeQuery"""
        return self.query.get_node_briefs(node_ids)

    # ─── Op 侧接口（拉取完整内容） ───

    def get_node_content(self, node_id: str) -> Optional[str]:
        """Op 执行时按需拉取节点完整内容"""
        row = self._conn.execute(
            "SELECT full_content FROM node_contents WHERE node_id = ?", (node_id,)
        ).fetchone()
        return row[0] if row else None

    def get_multiple_contents(self, node_ids: List[str]) -> Dict[str, str]:
        """批量拉取多个节点的完整内容"""
        if not node_ids:
            return {}
        placeholders = ','.join('?' * len(node_ids))
        rows = self._conn.execute(
            f"SELECT node_id, full_content FROM node_contents WHERE node_id IN ({placeholders})",
            tuple(node_ids)
        ).fetchall()
        return {r['node_id']: r['full_content'] for r in rows}

    # ─── 写入接口 ───

    def create_node(self, node_id: str, ntype: str, title: str, 
                    human_translation: str, tags: str,
                    full_content: str, source: str = "sedimenter",
                    prerequisites: str = None, resolves: str = None,
                    parent_node_id: str = None,
                    metadata_signature: Optional[Dict[str, Any]] = None,
                    confidence_score: Optional[float] = None,
                    last_verified_at: Optional[str] = None,
                    verification_source: Optional[str] = None,
                    trust_tier: str = "REFLECTION",
                    epistemic_status: str = "BELIEF"):
        # NOTE: confidence_score, parent_node_id, epistemic_status params kept for API compat but ignored.
        # Quality is derived from usage stats. Epistemic status derived from verification.
        """创建一个新的双层节点（索引 + 内容），支持注入因果属性和自动向量化"""
        # 如果是知识类节点，自动计算其向量
        embedding_json = None
        normalized_signature = self.bind_environment_signature(
            metadata_signature,
            ntype,
            context_text=f"{title}\n{full_content[:500]}" if full_content else title,
        )
        resolved_validation_status = self.signature.resolve_validation_status(normalized_signature)
        if resolved_validation_status:
            normalized_signature["validation_status"] = resolved_validation_status
        normalized_signature["knowledge_state"] = self.signature.resolve_knowledge_state(normalized_signature, ntype)
        # Temporal metadata: auto-set valid_from if not already present
        if "valid_from" not in normalized_signature:
            normalized_signature["valid_from"] = datetime.utcnow().strftime("%Y-%m-%d")
        signature_json = json.dumps(normalized_signature, ensure_ascii=False) if normalized_signature else None
        signature_text = self.signature.render(normalized_signature)
        validated_tier = trust_tier if trust_tier in TRUST_TIERS else "REFLECTION"
        normalized_last_verified = last_verified_at
        if not normalized_last_verified and normalized_signature.get("validation_status") == "validated":
            normalized_last_verified = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        normalized_verification_source = verification_source or (source if normalized_last_verified else None)
        # V4.3: 支持 ENTITY/EVENT/ACTION 进行向量化
        embeddable_types = ["LESSON", "CONTEXT", "ASSET", "EPISODE", "ENTITY", "EVENT", "ACTION", "TOOL", "DISCOVERY", "PATTERN", "POINT"]
        if ntype in embeddable_types and self.vector_engine.is_ready:
            text_to_encode = f"{title} {tags} {resolves or ''} {signature_text}".strip()
            vec = self.vector_engine.encode(text_to_encode)
            if vec:
                embedding_json = json.dumps(vec)
                self.vector_engine.add_to_matrix(node_id, vec)

        # 版本链：如果节点已存在，先快照旧版本
        self._snapshot_if_exists(node_id)

        self._conn.execute(
            """INSERT INTO knowledge_nodes
               (node_id, type, title, human_translation, tags, prerequisites, resolves,
                metadata_signature, embedding,
                last_verified_at, verification_source, trust_tier)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(node_id) DO UPDATE SET
                 type=excluded.type, title=excluded.title,
                 human_translation=excluded.human_translation, tags=excluded.tags,
                 prerequisites=excluded.prerequisites, resolves=excluded.resolves,
                 metadata_signature=excluded.metadata_signature,
                 embedding=excluded.embedding,
                 last_verified_at=excluded.last_verified_at,
                 verification_source=excluded.verification_source,
                 trust_tier=excluded.trust_tier,
                 updated_at=CURRENT_TIMESTAMP
            """,
            (node_id, ntype, title, human_translation, tags, prerequisites, resolves, signature_json, embedding_json, normalized_last_verified, normalized_verification_source, validated_tier)
        )
        self._conn.execute(
            """INSERT INTO node_contents (node_id, full_content, source) VALUES (?,?,?)
               ON CONFLICT(node_id) DO UPDATE SET
                 full_content=excluded.full_content, source=excluded.source
            """,
            (node_id, full_content, source)
        )
        self._conn.commit()
        logger.info(f"NodeVault: Created node [{node_id}] ({ntype}) — {title}")

    def backfill_embeddings(self) -> Dict[str, int]:
        """
        一次性回填：为所有缺少向量的知识节点生成 embedding。
        返回 {total_missing, success, failed} 统计。
        """
        if not self.vector_engine.is_ready:
            logger.warning("VectorEngine not ready, cannot backfill embeddings.")
            return {"total_missing": 0, "success": 0, "failed": 0, "skipped": 0}

        embeddable_types = ["LESSON", "CONTEXT", "ASSET", "EPISODE", "ENTITY", "EVENT", "ACTION", "TOOL", "DISCOVERY", "PATTERN", "POINT"]
        placeholders = ','.join('?' * len(embeddable_types))
        rows = self._conn.execute(
            f"SELECT node_id, type, title, tags, resolves, metadata_signature "
            f"FROM knowledge_nodes "
            f"WHERE (embedding IS NULL OR embedding = '') "
            f"AND type IN ({placeholders}) "
            f"AND node_id NOT LIKE 'MEM_CONV%'",
            tuple(embeddable_types)
        ).fetchall()

        total = len(rows)
        success = 0
        failed = 0
        skipped = 0

        for r in rows:
            sig_text = self.signature.render(r['metadata_signature'])
            text_to_encode = f"{r['title']} {r['tags'] or ''} {r['resolves'] or ''} {sig_text}".strip()
            if not text_to_encode:
                skipped += 1
                continue
            vec = self.vector_engine.encode(text_to_encode)
            if vec:
                embedding_json = json.dumps(vec)
                self._conn.execute(
                    "UPDATE knowledge_nodes SET embedding = ? WHERE node_id = ?",
                    (embedding_json, r['node_id'])
                )
                self.vector_engine.add_to_matrix(r['node_id'], vec)
                success += 1
            else:
                failed += 1

        self._conn.commit()
        # 重新加载内存矩阵以确保一致性
        self._load_embeddings_to_memory()
        logger.info(f"NodeVault: Backfill complete. total={total}, success={success}, failed={failed}, skipped={skipped}")
        return {"total_missing": total, "success": success, "failed": failed, "skipped": skipped}

    # ─── TOOL 节点激活桥 ─────────────────────────────────────────

    def get_tool_nodes(self, min_tier: str = "REFLECTION") -> List[Dict[str, Any]]:
        """查询所有可激活的 TOOL 节点（含源码）。

        Returns:
            List of dicts: {node_id, tool_name, title, source_code, trust_tier}
        """
        min_rank = TRUST_TIER_RANK.get(min_tier, 3)
        rows = self._conn.execute(
            "SELECT n.node_id, n.title, n.human_translation, n.trust_tier, "
            "       nc.full_content "
            "FROM knowledge_nodes n "
            "JOIN node_contents nc ON n.node_id = nc.node_id "
            "WHERE n.type = 'TOOL' AND nc.full_content IS NOT NULL "
            "  AND length(nc.full_content) > 20"
        ).fetchall()
        results = []
        for r in rows:
            tier = r["trust_tier"] or "REFLECTION"
            if TRUST_TIER_RANK.get(tier, 0) < min_rank:
                continue
            # 从 human_translation 提取 tool_name（格式: "Python工具: xxx"）
            ht = r["human_translation"] or ""
            if ht.startswith("Python工具: "):
                tool_name = ht[len("Python工具: "):].strip()
            else:
                # fallback: 从 node_id 推导（TOOL_xxx → xxx）
                nid = r["node_id"] or ""
                tool_name = nid[5:].lower() if nid.startswith("TOOL_") else nid.lower()
            results.append({
                "node_id": r["node_id"],
                "tool_name": tool_name,
                "title": r["title"],
                "source_code": r["full_content"],
                "trust_tier": tier,
            })
        logger.info(f"NodeVault: found {len(results)} activatable TOOL nodes (min_tier={min_tier})")
        return results

    # ─── promote/decay/record_usage_outcome/_try_promote_epistemic → arena_mixin.py ───

    def increment_usage(self, node_ids: List[str]):
        """增加节点使用权重"""
        if not node_ids:
            return
        placeholders = ','.join('?' * len(node_ids))
        self._conn.execute(
            f"UPDATE knowledge_nodes SET usage_count = usage_count + 1, updated_at = CURRENT_TIMESTAMP WHERE node_id IN ({placeholders})",
            tuple(node_ids)
        )


# ─── Multi-G 人格激活映射 ─────────────────────────────────────
# ── FactoryManager / NodeManagementTools / Persona 常量已迁移至 prompt_factory.py ──
# 下方 re-export 保证已有 `from genesis.v4.manager import FactoryManager` 不崩
from genesis.v4.prompt_factory import (  # noqa: E402, F401
    PERSONA_ACTIVATION_MAP,
    PERSONA_LENS_PROFILES,
    FactoryManager,
    NodeManagementTools,
)

