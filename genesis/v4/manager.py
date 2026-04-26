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
        self.signature = SignatureEngine(self._conn, vault=self)
        self.signature.initialize()
        self.query = KnowledgeQuery(self._conn)
        self.vector_engine = VectorEngine()
        self._last_matrix_sync = "2000-01-01 00:00:00"
        
        # 启动并加载向量引擎（守护进程可跳过以节省内存和启动时间）
        if skip_vector_engine:
            logger.info("NodeVault: skip_vector_engine=True, 跳过嵌入模型加载")
        else:
            self.vector_engine.initialize()
            self._load_embeddings_to_memory()
            self._last_matrix_sync: str = self._get_db_now()
        self._ensure_concept_seeds()
        self._initialized = True

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
            ('epistemic_status', 'TEXT DEFAULT \'BELIEF\''),
            ('is_virtual', 'INTEGER DEFAULT 0'),
            ('ablation_active', 'INTEGER DEFAULT 0')
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
        # 推理线表（点线面架构）：记录新点基于哪些旧点产生
        conn.execute('''
        CREATE TABLE IF NOT EXISTS reasoning_lines (
            line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            new_point_id TEXT NOT NULL,
            basis_point_id TEXT NOT NULL,
            reasoning TEXT,
            source TEXT DEFAULT 'GP',
            same_round INTEGER DEFAULT 0,
            trace_id TEXT,
            round_seq INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (new_point_id) REFERENCES knowledge_nodes(node_id),
            FOREIGN KEY (basis_point_id) REFERENCES knowledge_nodes(node_id)
        )
        ''')
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rl_basis ON reasoning_lines(basis_point_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rl_new ON reasoning_lines(new_point_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rl_trace_round ON reasoning_lines(trace_id, round_seq)")
        # Schema migration: reasoning_lines 可能缺 same_round 列（IF NOT EXISTS 不加列）
        try:
            rl_cols = [r[1] for r in conn.execute("PRAGMA table_info(reasoning_lines)").fetchall()]
            if 'same_round' not in rl_cols:
                conn.execute("ALTER TABLE reasoning_lines ADD COLUMN same_round INTEGER DEFAULT 0")
                logger.info("Schema migration: added same_round column to reasoning_lines")
            if 'trace_id' not in rl_cols:
                conn.execute("ALTER TABLE reasoning_lines ADD COLUMN trace_id TEXT")
                logger.info("Schema migration: added trace_id column to reasoning_lines")
            if 'round_seq' not in rl_cols:
                conn.execute("ALTER TABLE reasoning_lines ADD COLUMN round_seq INTEGER")
                logger.info("Schema migration: added round_seq column to reasoning_lines")
        except Exception as e:
            logger.warning(f"Schema migration for reasoning_lines.same_round skipped: {e}")
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
        # 消融基线表：记录消融激活时的 env_ratio，用于向前/向后判定
        conn.execute('''
        CREATE TABLE IF NOT EXISTS ablation_baselines (
            node_id TEXT PRIMARY KEY,
            activated_at INTEGER NOT NULL,
            baseline_env_ratio REAL,
            FOREIGN KEY (node_id) REFERENCES knowledge_nodes(node_id)
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
        conn.commit()

    def _ensure_concept_seeds(self):
        """首次部署时注入概念地图种子（CONTEXT节点）。
        概念地图 = 领域知识的冷启动注入，让 LLM 第一次面对代码时拥有导航坐标系。
        种子从 YAML 文件读取，用固定前缀 SEED_CTX_ 标识，只注入一次。"""
        try:
            existing = self._conn.execute(
                "SELECT COUNT(*) FROM knowledge_nodes WHERE node_id LIKE 'SEED_CTX_%'"
            ).fetchone()[0]
            if existing > 0:
                return  # 已注入，跳过

            seed_path = Path(__file__).parent / "concept_seeds.yaml"
            if not seed_path.exists():
                return

            import yaml
            seeds = yaml.safe_load(seed_path.read_text(encoding='utf-8'))
            if not seeds or not isinstance(seeds, list):
                return

            for seed in seeds:
                node_id = seed.get("id", "")
                if not node_id or not node_id.startswith("SEED_CTX_"):
                    continue
                # 检查是否已存在（防止重复注入）
                if self._conn.execute("SELECT 1 FROM knowledge_nodes WHERE node_id = ?", (node_id,)).fetchone():
                    continue
                self.create_node(
                    node_id=node_id,
                    title=seed.get("title", ""),
                    ntype="CONTEXT",
                    human_translation=seed.get("title", ""),
                    tags=seed.get("tags", "concept_seed"),
                    full_content=seed.get("content", ""),
                    trust_tier="HUMAN"
                )
                # 建立种子间的边（概念地图骨架）
                for related_id in seed.get("related", []):
                    self._conn.execute(
                        "INSERT OR IGNORE INTO node_edges (source_id, target_id, relation) VALUES (?,?,?)",
                        (node_id, related_id, "RELATED_TO")
                    )
            self._conn.commit()
            logger.info(f"Concept seeds injected: {len(seeds)} nodes from {seed_path}")
        except Exception as e:
            logger.warning(f"Concept seed injection skipped (non-fatal): {e}")

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

    # ── 推理线接口（点线面架构）──

    def create_reasoning_line(self, new_point_id: str, basis_point_id: str, reasoning: str = "", source: str = "GP", same_round: int = 0, trace_id: str = None, round_seq: int = None):
        """创建一条推理线：新点基于旧点产生"""
        try:
            self._conn.execute(
                "INSERT INTO reasoning_lines (new_point_id, basis_point_id, reasoning, source, same_round, trace_id, round_seq) VALUES (?,?,?,?,?,?,?)",
                (new_point_id, basis_point_id, reasoning, source, same_round, trace_id, round_seq)
            )
            self._conn.commit()
            logger.debug(f"Line: {new_point_id} --[based_on]--> {basis_point_id} (source={source})")
        except Exception as e:
            logger.error(f"Failed to create reasoning line: {e}")

    def get_reasoning_basis_ids(self, new_point_id: str) -> set:
        try:
            rows = self._conn.execute(
                "SELECT DISTINCT basis_point_id FROM reasoning_lines WHERE new_point_id = ?",
                (new_point_id,)
            ).fetchall()
            return {r[0] for r in rows}
        except Exception:
            return set()

    def get_incoming_line_count(self, node_id: str) -> int:
        """获取节点的入线数（被多少新点基于它产生）"""
        try:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM reasoning_lines WHERE basis_point_id = ? AND same_round = 0",
                (node_id,)
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def get_incoming_count_percentile(self, percentile: int = 75) -> int:
        """获取入线数分布的指定百分位数（自适应阈值用）。
        返回值：入线数 >= 此值的节点为"基础"。
        空库或无数据时返回 0。"""
        try:
            row = self._conn.execute(
                """SELECT incoming FROM (
                    SELECT COUNT(*) as incoming FROM reasoning_lines
                    WHERE same_round = 0 GROUP BY basis_point_id
                ) ORDER BY incoming LIMIT 1 OFFSET (
                    SELECT CAST(COUNT(*) * ? / 100 AS INTEGER) FROM (
                        SELECT COUNT(*) as incoming FROM reasoning_lines
                        WHERE same_round = 0 GROUP BY basis_point_id
                    )
                )""",
                (percentile,)
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def get_incoming_line_counts_batch(self, node_ids: list) -> dict:
        """批量获取入线数，避免 N+1 查询"""
        if not node_ids:
            return {}
        try:
            placeholders = ",".join("?" * len(node_ids))
            rows = self._conn.execute(
                f"SELECT basis_point_id, COUNT(*) as cnt FROM reasoning_lines WHERE basis_point_id IN ({placeholders}) AND same_round = 0 GROUP BY basis_point_id",
                node_ids
            ).fetchall()
            result = {nid: 0 for nid in node_ids}
            result.update({row[0]: row[1] for row in rows})
            return result
        except Exception:
            return {nid: 0 for nid in node_ids}

    def get_basis_set_for_node(self, new_point_id: str) -> set:
        """获取某新点连线指向的所有 basis_point_id 集合（碰撞检测用）"""
        try:
            rows = self._conn.execute(
                "SELECT basis_point_id FROM reasoning_lines WHERE new_point_id = ?",
                (new_point_id,)
            ).fetchall()
            return {row[0] for row in rows}
        except Exception:
            return set()

    def find_collision_candidates(self, basis_ids: list, min_overlap: int = 2) -> list:
        """碰撞检测：查找与给定 basis_ids 有重叠的已有节点。
        返回 [(new_point_id, overlap_count, title), ...] 按重叠数降序"""
        if not basis_ids:
            return []
        try:
            placeholders = ",".join("?" * len(basis_ids))
            rows = self._conn.execute(
                f"""SELECT new_point_id, COUNT(*) as overlap
                FROM reasoning_lines
                WHERE basis_point_id IN ({placeholders})
                GROUP BY new_point_id
                HAVING overlap >= ?
                ORDER BY overlap DESC
                LIMIT 5""",
                basis_ids + [min_overlap]
            ).fetchall()
            # 补充标题
            result = []
            for row in rows:
                nid, overlap = row[0], row[1]
                title_row = self._conn.execute(
                    "SELECT title FROM knowledge_nodes WHERE node_id = ?", (nid,)
                ).fetchone()
                title = title_row[0] if title_row else nid
                result.append((nid, overlap, title))
            return result
        except Exception as e:
            logger.error(f"find_collision_candidates failed: {e}")
            return []

    def ensure_virtual_point(self, area_hint: str, basis_overlap_ids: list = None) -> str:
        """碰撞检测后自动创建/递增虚点（系统行为，非GP行为）。
        虚点是知识饱和信号：同一区域反复碰撞 = 该区域已被充分探索。
        如果该区域已有虚点，递增 usage_count；否则创建新虚点。
        返回虚点 node_id。"""
        try:
            import hashlib
            # 用 area_hint 生成稳定的虚点 ID（同区域同 ID）
            vid = "VIRT_" + hashlib.md5(area_hint.encode()).hexdigest()[:8].upper()
            existing = self._conn.execute(
                "SELECT node_id, usage_count FROM knowledge_nodes WHERE node_id = ?",
                (vid,)
            ).fetchone()
            if existing:
                # 递增 usage_count（饱和度计数）
                self._conn.execute(
                    "UPDATE knowledge_nodes SET usage_count = usage_count + 1 WHERE node_id = ?",
                    (vid,)
                )
                self._conn.commit()
                logger.debug(f"Virtual point incremented: [{vid}] (area={area_hint}, count={existing[1]+1})")
            else:
                self._conn.execute(
                    "INSERT INTO knowledge_nodes (node_id, type, title, human_translation, tags, is_virtual, usage_count) VALUES (?,?,?,?,?,1,1)",
                    (vid, "CONTEXT", f"饱和:{area_hint}", f"饱和:{area_hint}", "virtual")
                )
                self._conn.execute(
                    "INSERT OR REPLACE INTO node_contents (node_id, full_content, source) VALUES (?,?,?)",
                    (vid, f"饱和:{area_hint}", "system")
                )
                # 连接到碰撞涉及的 basis 节点（1-hop 可见性）
                if basis_overlap_ids:
                    for bid in basis_overlap_ids[:3]:
                        self._conn.execute(
                            "INSERT OR IGNORE INTO node_edges (source_id, target_id, relation) VALUES (?,?,?)",
                            (vid, bid, "RELATED_TO")
                        )
                self._conn.commit()
                logger.info(f"Virtual point created: [{vid}] (area={area_hint}, linked to {len(basis_overlap_ids or [])} basis nodes)")
            return vid
        except Exception as e:
            logger.error(f"ensure_virtual_point failed: {e}")
            return ""

    def get_virtual_saturation(self, node_ids: list) -> list:
        """查询指定节点邻域内的虚点饱和信号。
        返回 [(area_hint, count), ...] 按虚点数降序"""
        if not node_ids:
            return []
        try:
            # 找到 node_ids 的 1-hop 邻居中的虚点
            placeholders = ",".join("?" * len(node_ids))
            # 从 node_edges 找邻居
            neighbor_rows = self._conn.execute(
                f"""SELECT DISTINCT target_id FROM node_edges
                WHERE source_id IN ({placeholders})
                UNION
                SELECT DISTINCT source_id FROM node_edges
                WHERE target_id IN ({placeholders})""",
                node_ids + node_ids
            ).fetchall()
            neighbor_ids = [r[0] for r in neighbor_rows]
            if not neighbor_ids:
                return []
            # 统计虚点
            nh_placeholders = ",".join("?" * len(neighbor_ids))
            virtual_rows = self._conn.execute(
                f"""SELECT node_id, title FROM knowledge_nodes
                WHERE node_id IN ({nh_placeholders}) AND is_virtual = 1""",
                neighbor_ids
            ).fetchall()
            if not virtual_rows:
                return []
            # 按区域聚合（取 title 前4字符作为区域标识，兼容中文）
            from collections import Counter
            area_counts = Counter()
            for vid, vtitle in virtual_rows:
                area = vtitle[:4] if len(vtitle) >= 4 else vtitle
                area_counts[area] += 1
            return [(area, count) for area, count in area_counts.most_common(5)]
        except Exception as e:
            logger.error(f"get_virtual_saturation failed: {e}")
            return []

    # ── 面组装辅助查询（供 SurfaceExpander 使用）──

    def get_neighbor_map(self, node_ids: list, include_reverse_reasoning: bool = True, weighted: bool = False) -> dict:
        """获取节点的 1-hop 邻居映射（node_edges + reasoning_lines 合并）

        Args:
            node_ids: 要查询邻居的节点 ID 列表
            include_reverse_reasoning: True=reasoning_lines双向映射(默认，向后兼容)，
                False=reasoning_lines只做 new→old 单向映射（填充阶段用，防止反向跳到前沿新点）
            weighted: True=返回带权重的邻居 {node_id: [(neighbor_id, weight), ...]}，
                False=返回简单列表 {node_id: [neighbor_id, ...]}（默认，向后兼容）
        """
        if not node_ids:
            return {}
        try:
            placeholders = ",".join("?" * len(node_ids))
            neighbor_map = {} if not weighted else {}
            
            # node_edges（始终双向，RELATED_TO边权重提升）
            for row in self._conn.execute(
                f"SELECT source_id, target_id, relation FROM node_edges WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})",
                node_ids + node_ids
            ).fetchall():
                source, target, relation = row[0], row[1], row[2] or "RELATED_TO"
                # RELATED_TO边权重提升到2.0，其他边保持1.0
                weight = 2.0 if relation == "RELATED_TO" else 1.0
                
                if weighted:
                    neighbor_map.setdefault(source, []).append((target, weight))
                    neighbor_map.setdefault(target, []).append((source, weight))
                else:
                    neighbor_map.setdefault(source, []).append(target)
                    neighbor_map.setdefault(target, []).append(source)
            
            # reasoning_lines（排除同轮线，面BFS只走异轮验证路径）
            # 设计约束：填充阶段只沿 new→old 方向走（踩稳基础），不反向跳到前沿新点
            for row in self._conn.execute(
                f"SELECT new_point_id, basis_point_id FROM reasoning_lines WHERE same_round = 0 AND (new_point_id IN ({placeholders}) OR basis_point_id IN ({placeholders}))",
                node_ids + node_ids
            ).fetchall():
                new_point, basis_point = row[0], row[1]
                # reasoning_lines 权重为1.5（中等优先级）
                weight = 1.5
                
                # 正向：new→old（始终包含——从新点跳到被它引用的旧点=踩稳）
                if weighted:
                    neighbor_map.setdefault(new_point, []).append((basis_point, weight))
                else:
                    neighbor_map.setdefault(new_point, []).append(basis_point)
                
                # 反向：old→new（由 include_reverse_reasoning 控制）
                if include_reverse_reasoning:
                    if weighted:
                        neighbor_map.setdefault(basis_point, []).append((new_point, weight))
                    else:
                        neighbor_map.setdefault(basis_point, []).append(new_point)
            
            # 去重
            for k in neighbor_map:
                if weighted:
                    # 带权重的情况：按邻居ID去重，保留最高权重
                    seen = {}
                    for nid, w in neighbor_map[k]:
                        if nid not in seen or w > seen[nid]:
                            seen[nid] = w
                    neighbor_map[k] = [(nid, w) for nid, w in seen.items()]
                else:
                    neighbor_map[k] = list(dict.fromkeys(neighbor_map[k]))
            return neighbor_map
        except Exception as e:
            logger.error(f"get_neighbor_map failed: {e}")
            return {}

    def get_frontier_node_ids(self, limit: int = 50) -> list:
        """获取最近创建的非虚拟、非消融、非反驳的前沿节点 ID"""
        try:
            rows = self._conn.execute(
                """SELECT node_id FROM knowledge_nodes
                WHERE node_id NOT LIKE 'MEM_CONV%'
                  AND type IN ('LESSON', 'CONTEXT', 'DISCOVERY')
                  AND is_virtual = 0
                  AND ablation_active = 0
                  AND node_id NOT IN (SELECT target_id FROM node_edges WHERE relation = 'CONTRADICTS')
                ORDER BY created_at DESC
                LIMIT ?""",
                (limit,)
            ).fetchall()
            return [r[0] for r in rows]
        except Exception as e:
            logger.error(f"get_frontier_node_ids failed: {e}")
            return []

    def get_excluded_ids(self, candidate_ids: list) -> set:
        """获取消融中的节点 ID 集合（ablation_active > 0）"""
        if not candidate_ids:
            return set()
        try:
            placeholders = ",".join("?" * len(candidate_ids))
            rows = self._conn.execute(
                f"SELECT node_id FROM knowledge_nodes WHERE node_id IN ({placeholders}) AND ablation_active > 0",
                list(candidate_ids)
            ).fetchall()
            return {r[0] for r in rows}
        except Exception:
            return set()

    def get_gardener_ablation_candidates(self, candidate_ids: list, limit: int = 10) -> list:
        """园丁协同：识别高入线+低胜率的节点，优先消融
        
        园丁机制：检测"看起来可靠但实际表现差"的节点
        - 高入线数：被很多节点引用（看起来重要）
        - 低胜率：实际使用成功率低（陷阱节点）
        
        Returns:
            [(node_id, incoming_count, win_rate, title), ...] 按优先级降序
        """
        if not candidate_ids:
            return []
        
        try:
            placeholders = ",".join("?" * len(candidate_ids))
            rows = self._conn.execute(
                f"""SELECT kn.node_id, kn.title, kn.usage_success_count, kn.usage_fail_count, kn.usage_count,
                          COALESCE(inc.incoming, 0) as incoming_count
                   FROM knowledge_nodes kn
                   LEFT JOIN (
                       SELECT basis_point_id, COUNT(*) as incoming
                       FROM reasoning_lines
                       WHERE basis_point_id IN ({placeholders})
                       GROUP BY basis_point_id
                   ) inc ON kn.node_id = inc.basis_point_id
                   WHERE kn.node_id IN ({placeholders})
                     AND kn.usage_count >= 3  -- 至少有3次使用记录
                     AND kn.ablation_active = 0  -- 未被消融
                   ORDER BY incoming_count DESC, (kn.usage_success_count * 1.0 / kn.usage_count) ASC
                   LIMIT ?""",
                candidate_ids + candidate_ids + [limit]
            ).fetchall()
            
            candidates = []
            for row in rows:
                node_id, title, wins, losses, total, incoming = row
                win_rate = wins / total if total > 0 else 0.0
                
                # 园丁评分：入线数越高且胜率越低，优先级越高
                gardener_score = incoming * (1.0 - win_rate)
                
                candidates.append({
                    'node_id': node_id,
                    'title': title,
                    'incoming_count': incoming,
                    'usage_success_count': wins,
                    'usage_fail_count': losses,
                    'usage_count': total,
                    'win_rate': win_rate,
                    'gardener_score': gardener_score
                })
            
            # 按园丁评分降序排列
            candidates.sort(key=lambda x: x['gardener_score'], reverse=True)
            return candidates
            
        except Exception as e:
            logger.error(f"get_gardener_ablation_candidates failed: {e}")
            return []

    def trigger_gardener_ablation(self, candidate_ids: list, max_ablations: int = 3) -> int:
        """触发园丁消融：标记高入线+低胜率的节点为消融状态
        
        Returns:
            实际消融的节点数量
        """
        candidates = self.get_gardener_ablation_candidates(candidate_ids, limit=max_ablations * 2)
        
        if not candidates:
            return 0
        
        ablated_count = 0
        for candidate in candidates[:max_ablations]:
            node_id = candidate['node_id']
            try:
                # 标记为消融状态
                self._conn.execute(
                    "UPDATE knowledge_nodes SET ablation_active = 1 WHERE node_id = ?",
                    (node_id,)
                )
                
                logger.info(
                    f"Gardener ablated {node_id}: incoming={candidate['incoming_count']}, "
                    f"win_rate={candidate['win_rate']:.2f}, title='{candidate['title'][:50]}...'"
                )
                ablated_count += 1
                
            except Exception as e:
                logger.error(f"Failed to ablate {node_id}: {e}")
        
        if ablated_count > 0:
            self._conn.commit()
            logger.info(f"Gardener completed: ablated {ablated_count} trap nodes")
        
        return ablated_count

    def batch_get_titles(self, node_ids: list) -> dict:
        """批量获取节点标题 {node_id: title}"""
        if not node_ids:
            return {}
        try:
            placeholders = ",".join("?" * len(node_ids))
            rows = self._conn.execute(
                f"SELECT node_id, title FROM knowledge_nodes WHERE node_id IN ({placeholders})",
                node_ids
            ).fetchall()
            return {r[0]: r[1] for r in rows}
        except Exception:
            return {}

    def get_same_round_ids(self, node_ids: list, window_seconds: int = 600, trace_id: str = None, round_seq: int = None) -> set:
        """检测哪些节点是最近 window_seconds 秒内创建的（同轮线标记用）"""
        if not node_ids:
            return set()
        try:
            if trace_id and round_seq is not None:
                placeholders = ",".join("?" * len(node_ids))
                rows = self._conn.execute(
                    f"SELECT DISTINCT new_point_id FROM reasoning_lines WHERE new_point_id IN ({placeholders}) AND trace_id = ? AND round_seq = ?",
                    node_ids + [trace_id, round_seq]
                ).fetchall()
                return {r[0] for r in rows}
            import time
            now = time.time()
            placeholders = ",".join("?" * len(node_ids))
            rows = self._conn.execute(
                f"SELECT node_id, created_at FROM knowledge_nodes WHERE node_id IN ({placeholders})",
                node_ids
            ).fetchall()
            same_round = set()
            for row in rows:
                try:
                    ca = row[1]
                    if isinstance(ca, (int, float)) and now - ca < window_seconds:
                        same_round.add(row[0])
                    elif isinstance(ca, str) and ca:
                        from datetime import datetime
                        dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
                        if (now - dt.timestamp()) < window_seconds:
                            same_round.add(row[0])
                except Exception:
                    pass
            return same_round
        except Exception:
            return set()

    # ── 真理区分（RAG消融）──

    def check_ablation_candidates(self, min_incoming: int = 5, min_idle_rounds: int = 3) -> list:
        """查找满足消融触发条件的节点：
        1. 入线数 >= min_incoming（已被足够多新点基于它产生）
        2. 最近 min_idle_rounds 轮无新线连向该点（知识已稳定）
        返回 [(node_id, incoming_count, title), ...]"""
        try:
            rows = self._conn.execute(
                """SELECT rl.basis_point_id, COUNT(*) as incoming, kn.title
                FROM reasoning_lines rl
                JOIN knowledge_nodes kn ON rl.basis_point_id = kn.node_id
                WHERE rl.same_round = 0
                  AND kn.ablation_active = 0
                  AND kn.node_id NOT LIKE 'MEM_CONV%'
                GROUP BY rl.basis_point_id
                HAVING incoming >= ?
                ORDER BY incoming DESC""",
                (min_incoming,)
            ).fetchall()
            # TODO: 检查 idle rounds（需要 trace 数据，MVP 先跳过）
            return [(r[0], r[1], r[2]) for r in rows]
        except Exception as e:
            logger.error(f"check_ablation_candidates failed: {e}")
            return []

    def get_ablation_observing_nodes(self, min_duration_seconds: int = 300) -> list:
        """获取正在消融观察中的节点（已观察超过 min_duration_seconds 秒）。
        返回 [(node_id, title, baseline_env_ratio), ...]"""
        try:
            rows = self._conn.execute(
                """SELECT kn.node_id, kn.title, ab.baseline_env_ratio
                FROM knowledge_nodes kn JOIN ablation_baselines ab ON kn.node_id = ab.node_id
                WHERE kn.ablation_active = 1 AND ab.activated_at <= strftime('%s','now') - ?""",
                (min_duration_seconds,)
            ).fetchall()
            return [(r[0], r[1], r[2]) for r in rows]
        except Exception as e:
            logger.error(f"get_ablation_observing_nodes failed: {e}")
            return []

    def activate_ablation(self, node_id: str, baseline_env_ratio: float = None) -> bool:
        """激活消融：从面和搜索中隐藏该节点，观察 N 轮。
        baseline_env_ratio: 消融前的环境成功率，用于后续评估向前/向后判定。"""
        try:
            import time
            self._conn.execute(
                "UPDATE knowledge_nodes SET ablation_active = 1 WHERE node_id = ?",
                (node_id,)
            )
            # 记录消融基线（用于评估）
            self._conn.execute(
                "INSERT OR REPLACE INTO ablation_baselines (node_id, activated_at, baseline_env_ratio) VALUES (?,?,?)",
                (node_id, int(time.time()), baseline_env_ratio)
            )
            self._conn.commit()
            logger.info(f"Ablation activated for [{node_id}] (baseline_env_ratio={baseline_env_ratio})")
            return True
        except Exception as e:
            logger.error(f"activate_ablation failed: {e}")
            return False

    # ── 主动遗忘与置换（Proactive Pruning）──

    def check_proactive_pruning_candidates(self, min_incoming: int = 8, min_idle_rounds: int = 10, min_neighbor_density: int = 5) -> list:
        """查找满足主动修剪条件的节点（比消融更严格）：
        1. 入线数 >= min_incoming（高度验证，惯性极强——最需要打破）
        2. trust_tier = HUMAN 或 REFLECTION（高信任 = 惯性最强）
        3. 1-hop 邻居数 >= min_neighbor_density（网络足够密，修剪不会导致断裂）
        4. ablation_active = 0（未在消融观察中）
        返回 [(node_id, incoming_count, title, neighbor_count), ...]"""
        try:
            rows = self._conn.execute(
                """SELECT rl.basis_point_id, COUNT(*) as incoming, kn.title, kn.trust_tier
                FROM reasoning_lines rl
                JOIN knowledge_nodes kn ON rl.basis_point_id = kn.node_id
                WHERE rl.same_round = 0
                  AND kn.ablation_active = 0
                  AND kn.is_virtual = 0
                  AND kn.trust_tier IN ('HUMAN', 'REFLECTION')
                  AND kn.node_id NOT LIKE 'SEED_CTX_%'
                  AND kn.node_id NOT LIKE 'VIRT_%'
                GROUP BY rl.basis_point_id
                HAVING incoming >= ?
                ORDER BY incoming DESC""",
                (min_incoming,)
            ).fetchall()
            # 过滤：邻居密度足够（修剪不会导致区域断裂）
            result = []
            for r in rows:
                nid, inc, title, tier = r
                neighbors = self.get_neighbor_map([nid]).get(nid, [])
                if len(neighbors) >= min_neighbor_density:
                    result.append((nid, inc, title, len(neighbors)))
            return result[:5]  # 每轮最多5个
        except Exception as e:
            logger.error(f"check_proactive_pruning_candidates failed: {e}")
            return []

    def activate_proactive_pruning(self, node_id: str, baseline_env_ratio: float = None) -> bool:
        """激活主动修剪（ablation_active=3）：故意移除高惯性节点，诱导新解释涌现。
        与消融(ablation_active=1)的区别：
        - 消融 = 验证必要性（缺了它行不行？）→ 不行就恢复
        - 修剪 = 诱导涌现（故意拿走，逼系统找新路）→ 不恢复，等新东西长出来
        跳过观察期，直接隐藏。5轮后检查是否有新节点覆盖相同问题域。"""
        try:
            import time
            self._conn.execute(
                "UPDATE knowledge_nodes SET ablation_active = 3 WHERE node_id = ?",
                (node_id,)
            )
            # 记录修剪基线（与消融共用 ablation_baselines 表，但 activated_at 前缀标记）
            self._conn.execute(
                "INSERT OR REPLACE INTO ablation_baselines (node_id, activated_at, baseline_env_ratio) VALUES (?,?,?)",
                (node_id, int(time.time()), baseline_env_ratio)
            )
            self._conn.commit()
            logger.info(f"Proactive pruning activated for [{node_id}] (ablation_active=3, baseline_env={baseline_env_ratio})")
            return True
        except Exception as e:
            logger.error(f"activate_proactive_pruning failed: {e}")
            return False

    def evaluate_proactive_pruning(self, node_id: str, current_env_ratio: float = None) -> str:
        """评估主动修剪结果（5轮后检查）：
        - 该区域产生了新节点覆盖相同问题域 → 修剪成功，旧节点永久降级(ablation_active=2)
        - 无新节点且 env_ratio 下降 → 该区域依赖旧模型，恢复(ablation_active=0)
        - 无新节点但 env_ratio 不变 → 继续观察（再等5轮）"""
        try:
            row = self._conn.execute(
                "SELECT baseline_env_ratio FROM ablation_baselines WHERE node_id = ?",
                (node_id,)
            ).fetchone()
            baseline = row[0] if row else None

            # 检查该区域是否有新节点（1-hop邻居中最近创建的）
            neighbors = self.get_neighbor_map([node_id]).get(node_id, [])
            import time
            recent_threshold = int(time.time()) - 3600  # 最近1小时内创建
            new_count = 0
            if neighbors:
                ph = ",".join("?" * len(neighbors))
                new_count = self._conn.execute(
                    f"SELECT COUNT(*) FROM knowledge_nodes WHERE node_id IN ({ph}) AND created_at >= ? AND ablation_active = 0",
                    neighbors + [recent_threshold]
                ).fetchone()[0]

            if new_count > 0:
                # 新解释已涌现：旧节点永久降级
                self._conn.execute(
                    "UPDATE knowledge_nodes SET ablation_active = 2 WHERE node_id = ?",
                    (node_id,)
                )
                self._conn.commit()
                logger.info(f"Proactive pruning SUCCESS: [{node_id}] → demoted, {new_count} new nodes emerged")
                return "emerged_new"
            elif baseline is not None and current_env_ratio is not None and current_env_ratio < baseline - 0.1:
                # env_ratio 下降：该区域依赖旧模型，恢复
                self._conn.execute(
                    "UPDATE knowledge_nodes SET ablation_active = 0 WHERE node_id = ?",
                    (node_id,)
                )
                self._conn.commit()
                logger.info(f"Proactive pruning RESTORE: [{node_id}] → restored (env_ratio dropped)")
                return "restored"
            else:
                # 继续观察
                logger.info(f"Proactive pruning CONTINUE: [{node_id}] → keep observing (no new nodes, env_ratio stable)")
                return "continue_observing"
        except Exception as e:
            logger.error(f"evaluate_proactive_pruning failed: {e}")
            return "error"

    def deactivate_ablation(self, node_id: str, current_env_ratio: float = None) -> str:
        """结束消融观察期，自动判定向前/向后：
        - current_env_ratio 下降 vs baseline → 向后（必要跳板）→ 恢复可见
        - current_env_ratio 不变 vs baseline → 向前（LLM内部已有）→ 降级
        - 无数据时默认向后（保守策略：宁可保留也不丢失跳板）
        """
        try:
            # 读取消融基线
            row = self._conn.execute(
                "SELECT baseline_env_ratio FROM ablation_baselines WHERE node_id = ?",
                (node_id,)
            ).fetchone()
            baseline = row[0] if row else None

            # 自动判定
            confirmed = True  # 默认保守：保留
            if baseline is not None and current_env_ratio is not None:
                # env_ratio 下降 ≥ 0.1 → 向后（必要跳板）
                # env_ratio 不变或上升 → 向前（LLM内部已有）
                if current_env_ratio >= baseline - 0.1:
                    confirmed = False  # 向前：缺了它不影响
                    logger.info(f"Ablation auto-judge: [{node_id}] 向前 (baseline={baseline:.2f}, current={current_env_ratio:.2f})")
                else:
                    logger.info(f"Ablation auto-judge: [{node_id}] 向后 (baseline={baseline:.2f}, current={current_env_ratio:.2f})")

            if confirmed:
                # 确认价值：恢复可见
                self._conn.execute(
                    "UPDATE knowledge_nodes SET ablation_active = 0 WHERE node_id = ?",
                    (node_id,)
                )
                self._conn.commit()
                logger.info(f"Ablation ended: [{node_id}] confirmed valuable (向后)")
                return "confirmed_valuable"
            else:
                # 降级：保持隐藏，标记为 LLM 内部已有知识
                self._conn.execute(
                    "UPDATE knowledge_nodes SET ablation_active = 2 WHERE node_id = ?",
                    (node_id,)
                )
                self._conn.commit()
                logger.info(f"Ablation ended: [{node_id}] demoted (向前: LLM internal)")
                return "demoted"
        except Exception as e:
            logger.error(f"deactivate_ablation failed: {e}")
            return "error"

    def delete_node(self, node_id: str) -> bool:
        """物理删除一个节点及其所有关联数据（统一删除入口）"""
        try:
            self._conn.execute("DELETE FROM node_edges WHERE source_id = ? OR target_id = ?", (node_id, node_id))
            self._conn.execute("DELETE FROM reasoning_lines WHERE new_point_id = ? OR basis_point_id = ?", (node_id, node_id))
            self._conn.execute("DELETE FROM node_versions WHERE node_id = ?", (node_id,))
            self._conn.execute("DELETE FROM node_contents WHERE node_id = ?", (node_id,))
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
        embeddable_types = ["LESSON", "CONTEXT", "ASSET", "EPISODE", "ENTITY", "EVENT", "ACTION", "TOOL", "DISCOVERY", "PATTERN"]
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

        embeddable_types = ["LESSON", "CONTEXT", "ASSET", "EPISODE", "ENTITY", "EVENT", "ACTION", "TOOL", "DISCOVERY", "PATTERN"]
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

