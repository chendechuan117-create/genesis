"""
Genesis V4 - 认知装配师 (The Factory Manager G)
核心：节点是标题，内容用链接联通。G 看标题，Op 看内容。
"""

import json
import sqlite3
import functools
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
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

# ── Schema 退役登记簿 ──────────────────────────────────────
# 以下字段仍存在于 knowledge_nodes 表中（保持旧 DB 兼容），
# 但已不再被生产逻辑消费。新代码不应写入或依赖这些字段。
# 迁移策略：保留列定义不删除，渲染时忽略，未来大版本迁移时统一清理。
SCHEMA_DEPRECATED_FIELDS = {
    "epistemic_status": {
        "deprecated_since": "2026-04",
        "replaced_by": "validation_status + knowledge_state (signature_engine)",
        "migration": "现有值 BELIEF/FACT 无迁移路径；新节点由 signature.resolve_validation_status() 推导",
        "render_strategy": "ignore",
    },
    "confidence_score": {
        "deprecated_since": "2026-04",
        "replaced_by": "effective_confidence() (arena_mixin, 基于 usage stats + freshness)",
        "migration": "旧值保留在 DB 中不读取；新节点默认 0.55 仅占位",
        "render_strategy": "ignore",
    },
    "parent_node_id": {
        "deprecated_since": "2026-04",
        "replaced_by": "node_edges (RELATED_TO / REQUIRES 边)",
        "migration": "无自动迁移；旧树形父子关系已由图谱边替代",
        "render_strategy": "ignore",
    },
}

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
    HARD_EVIDENCE_REF_TYPES = {
        "file",
        "command",
        "db_query",
        "trace",
        "runtime_observation",
        "runtime_test",
        "code_reading",
        "database_query",
        "shell",
        "read_file",
    }
    PLS_PROPOSAL_PAYLOAD_SCHEMA_VERSION = 1
    PERSONA_STATS_STALE_AFTER_DAYS = 7
    PLS_PROPOSAL_ALLOWED_POINT_TYPES = {"LESSON", "CONTEXT"}
    PLS_PROPOSAL_FORBIDDEN_PAYLOAD_KEYS = {
        "incoming",
        "incoming_count",
        "rl_out",
        "usage",
        "usage_count",
        "links",
        "link_count",
        "score",
        "fusion_score",
        "win_rate",
        "basis_set_score",
    }
    
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
        conn.execute('''
        CREATE TABLE IF NOT EXISTS point_creation_context (
            node_id TEXT PRIMARY KEY,
            trace_id TEXT,
            round_seq INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (node_id) REFERENCES knowledge_nodes(node_id)
        )
        ''')
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pcc_trace_round ON point_creation_context(trace_id, round_seq)")
        conn.execute('''
        CREATE TABLE IF NOT EXISTS potential_samples (
            sample_id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT,
            round_seq INTEGER,
            source TEXT DEFAULT 'surface',
            potential_type TEXT NOT NULL,
            triage_category TEXT DEFAULT 'structural',
            target_basin TEXT,
            title TEXT NOT NULL,
            detail TEXT,
            node_ids TEXT,
            evidence TEXT,
            triage_note TEXT,
            status TEXT DEFAULT 'open',
            dedupe_key TEXT,
            occurrence_count INTEGER DEFAULT 1,
            last_seen_at TIMESTAMP,
            last_seen_trace_id TEXT,
            last_seen_round_seq INTEGER,
            last_seen_source TEXT,
            resolution_node_id TEXT,
            resolution_note TEXT,
            resolved_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        conn.execute("CREATE INDEX IF NOT EXISTS idx_potential_trace_round ON potential_samples(trace_id, round_seq)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_potential_type_created ON potential_samples(potential_type, created_at)")
        try:
            potential_cols = [r[1] for r in conn.execute("PRAGMA table_info(potential_samples)").fetchall()]
            for col_name, col_def in [
                ("status", "TEXT DEFAULT 'open'"),
                ("resolution_node_id", "TEXT"),
                ("resolution_note", "TEXT"),
                ("resolved_at", "TIMESTAMP"),
                ("triage_category", "TEXT DEFAULT 'structural'"),
                ("target_basin", "TEXT"),
                ("triage_note", "TEXT"),
                ("dedupe_key", "TEXT"),
                ("occurrence_count", "INTEGER DEFAULT 1"),
                ("last_seen_at", "TIMESTAMP"),
                ("last_seen_trace_id", "TEXT"),
                ("last_seen_round_seq", "INTEGER"),
                ("last_seen_source", "TEXT"),
            ]:
                if col_name not in potential_cols:
                    conn.execute(f"ALTER TABLE potential_samples ADD COLUMN {col_name} {col_def}")
            conn.execute("UPDATE potential_samples SET occurrence_count = 1 WHERE occurrence_count IS NULL OR occurrence_count < 1")
            conn.execute("UPDATE potential_samples SET last_seen_at = created_at WHERE last_seen_at IS NULL")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_potential_status_created ON potential_samples(status, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_potential_triage_created ON potential_samples(triage_category, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_potential_dedupe_status ON potential_samples(dedupe_key, status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_potential_last_seen ON potential_samples(last_seen_at)")
        except Exception as e:
            logger.warning(f"Schema migration for potential_samples lifecycle skipped: {e}")
        conn.execute('''
        CREATE TABLE IF NOT EXISTS pls_proposals (
            proposal_id TEXT PRIMARY KEY,
            parent_trace_id TEXT,
            parent_round_seq INTEGER,
            branch_id TEXT,
            proposal_type TEXT NOT NULL,
            source TEXT DEFAULT 'async_branch',
            payload_json TEXT NOT NULL,
            basis_ids_json TEXT,
            status TEXT DEFAULT 'pending',
            merge_result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        try:
            proposal_cols = [r[1] for r in conn.execute("PRAGMA table_info(pls_proposals)").fetchall()]
            for col_name, col_def in [
                ("parent_trace_id", "TEXT"),
                ("parent_round_seq", "INTEGER"),
                ("branch_id", "TEXT"),
                ("source", "TEXT DEFAULT 'async_branch'"),
                ("basis_ids_json", "TEXT"),
                ("status", "TEXT DEFAULT 'pending'"),
                ("merge_result", "TEXT"),
            ]:
                if col_name not in proposal_cols:
                    conn.execute(f"ALTER TABLE pls_proposals ADD COLUMN {col_name} {col_def}")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pls_proposals_status_created ON pls_proposals(status, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pls_proposals_branch_created ON pls_proposals(branch_id, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pls_proposals_parent ON pls_proposals(parent_trace_id, parent_round_seq)")
        except Exception as e:
            logger.warning(f"Schema migration for pls_proposals skipped: {e}")
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rl_trace_round ON reasoning_lines(trace_id, round_seq)")
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
            for seed in seeds:
                node_id = seed.get("id", "")
                if not node_id or not node_id.startswith("SEED_CTX_"):
                    continue
                for related_id in seed.get("related", []):
                    self.add_edge(node_id, related_id, "RELATED_TO")
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

    def audit_signatures(self, limit: int = 50) -> Dict[str, Any]:
        """
        签名质量审计（算法层）：
        1. 内容重推断对比：用 signature.infer 重推断，与存储签名比较
        2. 黑名单清洗：删除自定义维度中的运营垃圾字段
        3. 规范化修复：确保 sort/dedup/cap 一致性
        4. invalidation_reason 补填：对已过时节点补填缺失的 reason

        自动修复可修的问题，返回审计统计。
        供 BackgroundDaemon 定期调用。
        """
        rows = self._conn.execute(
            """SELECT k.node_id, k.metadata_signature, k.type, k.title,
                      nc.full_content
               FROM knowledge_nodes k
               LEFT JOIN node_contents nc ON k.node_id = nc.node_id
               WHERE k.node_id NOT LIKE 'MEM_CONV%'
                 AND k.metadata_signature IS NOT NULL
                 AND k.metadata_signature != '{}'
               ORDER BY k.updated_at ASC
               LIMIT ?""",
            (limit,)
        ).fetchall()

        stats = {"audited": 0, "fixed_normalize": 0, "fixed_blacklist": 0,
                 "fixed_contradiction": 0, "fixed_invalidation_reason": 0,
                 "unchanged": 0}

        for row in rows:
            node_id = row["node_id"]
            content = row["full_content"] or row["title"] or ""
            try:
                stored_sig = json.loads(row["metadata_signature"]) if isinstance(
                    row["metadata_signature"], str) else row["metadata_signature"]
            except Exception:
                continue
            if not isinstance(stored_sig, dict):
                continue

            stats["audited"] += 1
            new_sig = dict(stored_sig)
            changed = False

            # 1. 规范化修复（sort/dedup/cap）
            normalized = self.signature.normalize(stored_sig)
            if json.dumps(normalized, sort_keys=True) != json.dumps(stored_sig, sort_keys=True):
                new_sig = normalized
                changed = True
                stats["fixed_normalize"] += 1

            # 2. 黑名单清洗
            blacklist_hits = [k for k in new_sig if k in _DIM_OPERATIONAL_BLACKLIST]
            if blacklist_hits:
                for k in blacklist_hits:
                    del new_sig[k]
                changed = True
                stats["fixed_blacklist"] += 1

            # 3. 内容重推断对比（仅核心字段）
            if content and len(content) > 20:
                re_inferred = self.signature.infer(content[:2000])
                for key in ["language", "runtime", "os_family", "framework"]:
                    stored_val = new_sig.get(key)
                    inferred_val = re_inferred.get(key)
                    if not stored_val or not inferred_val:
                        continue
                    stored_set = set(stored_val if isinstance(stored_val, list) else [stored_val])
                    inferred_set = set(inferred_val if isinstance(inferred_val, list) else [inferred_val])
                    if stored_set and inferred_set and not (stored_set & inferred_set):
                        merged = sorted(stored_set | inferred_set)[:3]
                        new_sig[key] = merged if len(merged) > 1 else merged[0]
                        changed = True
                        stats["fixed_contradiction"] += 1
                        logger.info(f"SigAudit [{node_id}] {key}: {stored_val} ⊕ {inferred_val} → {new_sig[key]}")

            # 4. invalidation_reason 补填
            if new_sig.get("validation_status") in ("outdated", "superseded") and "invalidation_reason" not in new_sig:
                inferred_reason = self.signature.infer_invalidation_reason(new_sig)
                if inferred_reason:
                    new_sig["invalidation_reason"] = inferred_reason
                    changed = True
                    stats["fixed_invalidation_reason"] += 1

            if changed:
                self._conn.execute(
                    "UPDATE knowledge_nodes SET metadata_signature = ?, updated_at = CURRENT_TIMESTAMP WHERE node_id = ?",
                    (json.dumps(new_sig, ensure_ascii=False), node_id)
                )
            else:
                stats["unchanged"] += 1

        if stats["audited"] > 0:
            self._conn.commit()
            fixed = stats["fixed_normalize"] + stats["fixed_blacklist"] + stats["fixed_contradiction"] + stats["fixed_invalidation_reason"]
            if fixed > 0:
                logger.info(f"SigAudit: {stats['audited']} audited, {fixed} fixed "
                            f"(norm={stats['fixed_normalize']}, blacklist={stats['fixed_blacklist']}, "
                            f"contradict={stats['fixed_contradiction']}, inv_reason={stats['fixed_invalidation_reason']})")
        return stats

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
                "SELECT persona, task_kind, wins, losses, updated_at FROM persona_stats"
            ).fetchall()
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            skipped_stale = 0
            for r in rows:
                persona, tk, wins, losses = r['persona'], r['task_kind'], r['wins'], r['losses']
                updated_at = self._parse_db_timestamp(r['updated_at'])
                age_days = (now - updated_at).days if updated_at else None
                if age_days is None or age_days > self.PERSONA_STATS_STALE_AFTER_DAYS:
                    skipped_stale += 1
                    continue
                if not tk:
                    global_stats[persona] = {"wins": wins, "losses": losses}
                else:
                    task_stats[f"{persona}:{tk}"] = {"wins": wins, "losses": losses}
            if global_stats:
                logger.info(f"PersonaStats: loaded {len(global_stats)} personas, {len(task_stats)} task entries")
            if skipped_stale:
                logger.info(f"PersonaStats: skipped {skipped_stale} stale snapshot rows")
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
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO void_tasks (void_id, query, source, persona, task_signature) VALUES (?,?,?,?,?)",
                (void_id, query, source, persona, sig_json)
            )
            self._conn.commit()
            return cur.rowcount > 0
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

    def resolve_void(self, void_id: str, resolution_node_id: str = None) -> bool:
        """标记 VOID 已解决（被升格为 LESSON 或已过时）"""
        if resolution_node_id and not self._node_existence_map([resolution_node_id]).get(resolution_node_id):
            logger.warning(f"resolve_void refused missing resolution node {resolution_node_id} for {void_id}")
            return False
        cur = self._conn.execute(
            "UPDATE void_tasks SET status = 'resolved', resolution_node_id = ?, resolved_at = CURRENT_TIMESTAMP WHERE void_id = ? AND status = 'open'",
            (resolution_node_id, void_id)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def stale_void(self, void_id: str) -> bool:
        """标记 VOID 已过时（不再需要追踪）"""
        cur = self._conn.execute(
            "UPDATE void_tasks SET status = 'stale', resolved_at = CURRENT_TIMESTAMP WHERE void_id = ? AND status = 'open'",
            (void_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def resolve_matching_voids_for_node(self, node_id: str, title: str = "", full_content: str = "", limit: int = 5) -> int:
        try:
            if not node_id or not title:
                return 0
            text = f"{title}\n{full_content or ''}".lower()
            rows = self._conn.execute(
                "SELECT void_id, query FROM void_tasks WHERE status = 'open' ORDER BY created_at ASC LIMIT 200"
            ).fetchall()
            resolved = 0
            for row in rows:
                query = str(row["query"] or "").strip()
                q = query.lower()
                if len(q) < 4:
                    continue
                matched = q in text or (len(title) >= 4 and str(title).lower() in q)
                if matched and self.resolve_void(row["void_id"], node_id):
                    resolved += 1
                    if resolved >= limit:
                        break
            return resolved
        except Exception as e:
            logger.debug(f"resolve_matching_voids_for_node failed for {node_id}: {e}")
            return 0

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

    def void_maintenance_report(self, stale_days: int = 14) -> Dict[str, Any]:
        """VOID 干跑维护报告（只读，不修改数据）。

        返回:
        - stale_candidates: 超过 stale_days 天仍 open 的 VOID
        - duplicate_queries: 相似查询的重复 VOID
        - potentially_resolved: 可能已被现有知识覆盖的 VOID
        - summary: 各类计数
        """
        import logging
        _log = logging.getLogger(__name__)
        stale_candidates = []
        duplicate_queries = []
        potentially_resolved = []

        # 1. Stale VOIDs: open 超过 N 天
        rows = self._conn.execute(
            "SELECT void_id, query, source, created_at FROM void_tasks "
            "WHERE status = 'open' AND created_at < datetime('now', ?) "
            "ORDER BY created_at ASC LIMIT 50",
            (f'-{stale_days} days',)
        ).fetchall()
        for r in rows:
            stale_candidates.append({"void_id": r["void_id"], "query": r["query"][:80], "created_at": r["created_at"]})

        # 2. Duplicate queries: 相似查询的重复 VOID
        dup_rows = self._conn.execute(
            "SELECT query, COUNT(*) as cnt, GROUP_CONCAT(void_id) as ids FROM void_tasks "
            "WHERE status = 'open' GROUP BY LOWER(query) HAVING cnt > 1 LIMIT 20"
        ).fetchall()
        for r in dup_rows:
            duplicate_queries.append({"query": r["query"][:80], "count": r["cnt"], "void_ids": r["ids"][:200]})

        # 3. Potentially resolved: VOID query 匹配已有知识节点标题
        for row in stale_candidates[:10]:
            match = self._conn.execute(
                "SELECT node_id, title FROM knowledge_nodes WHERE title LIKE ? LIMIT 1",
                (f"%{row['query'][:30]}%",)
            ).fetchone()
            if match:
                potentially_resolved.append({
                    "void_id": row["void_id"],
                    "query": row["query"],
                    "matched_node": match["node_id"],
                    "matched_title": match["title"][:80],
                })

        return {
            "stale_candidates": stale_candidates,
            "stale_count": len(stale_candidates),
            "duplicate_queries": duplicate_queries,
            "duplicate_count": len(duplicate_queries),
            "potentially_resolved": potentially_resolved,
            "resolvable_count": len(potentially_resolved),
        }

    def topology_audit_report(self) -> Dict[str, Any]:
        """拓扑干跑审计报告（只读，不修改数据）。

        返回:
        - orphan_edges: 指向不存在节点的边
        - zero_incoming_nodes: 入线数为 0 的非 LESSON 节点
        - virtual_nodes: 虚拟节点统计
        - contradicts_edges: CONTRADICTS 边统计
        - schema_issues: metadata_signature 格式问题
        """
        orphan_edges = []
        zero_incoming = []
        schema_issues = []

        # 1. Orphan edges: source 或 target 不存在
        orphan_rows = self._conn.execute(
            "SELECT ne.edge_id, ne.source_id, ne.target_id, ne.relation FROM node_edges ne "
            "WHERE ne.source_id NOT IN (SELECT node_id FROM knowledge_nodes) "
            "   OR ne.target_id NOT IN (SELECT node_id FROM knowledge_nodes) "
            "LIMIT 50"
        ).fetchall()
        for r in orphan_rows:
            orphan_edges.append({
                "edge_id": r["edge_id"], "source_id": r["source_id"],
                "target_id": r["target_id"], "relation": r["relation"],
            })

        # 2. Zero incoming: 入线数为 0 的节点（排除 LESSON/CONTEXT/DISCOVERY/EPISODE）
        zi_rows = self._conn.execute(
            "SELECT kn.node_id, kn.type, kn.title FROM knowledge_nodes kn "
            "WHERE kn.node_id NOT IN (SELECT target_id FROM node_edges) "
            "AND kn.type NOT IN ('LESSON', 'CONTEXT', 'DISCOVERY', 'EPISODE') "
            "AND kn.is_virtual = 0 AND COALESCE(kn.ablation_active, 0) = 0 "
            "LIMIT 30"
        ).fetchall()
        for r in zi_rows:
            zero_incoming.append({"node_id": r["node_id"], "type": r["type"], "title": r["title"][:80]})

        # 3. Virtual nodes: 虚拟节点统计
        virtual_total = self._conn.execute(
            "SELECT COUNT(*) FROM knowledge_nodes WHERE is_virtual = 1"
        ).fetchone()[0]
        virtual_by_type = self._conn.execute(
            "SELECT type, COUNT(*) as cnt FROM knowledge_nodes WHERE is_virtual = 1 GROUP BY type"
        ).fetchall()
        virtual_nodes = {
            "total": virtual_total,
            "by_type": {r["type"]: r["cnt"] for r in virtual_by_type},
        }

        # 4. CONTRADICTS edges: 矛盾边统计
        contradicts_total = self._conn.execute(
            "SELECT COUNT(*) FROM node_edges WHERE relation = 'CONTRADICTS'"
        ).fetchone()[0]
        contradicts_recent = self._conn.execute(
            "SELECT COUNT(*) FROM node_edges WHERE relation = 'CONTRADICTS' "
            "AND created_at > datetime('now', '-30 days')"
        ).fetchone()[0]
        contradicts_info = {
            "total": contradicts_total,
            "recent_30d": contradicts_recent,
        }

        # 5. Schema issues: metadata_signature 缺少关键字段
        schema_rows = self._conn.execute(
            "SELECT node_id, type, metadata_signature FROM knowledge_nodes "
            "WHERE metadata_signature IS NOT NULL AND metadata_signature != '' "
            "AND (metadata_signature NOT LIKE '%validation_status%' "
            "  OR metadata_signature NOT LIKE '%knowledge_state%') "
            "LIMIT 20"
        ).fetchall()
        for r in schema_rows:
            schema_issues.append({"node_id": r["node_id"], "type": r["type"]})

        return {
            "orphan_edges": orphan_edges,
            "orphan_count": len(orphan_edges),
            "zero_incoming_nodes": zero_incoming,
            "zero_incoming_count": len(zero_incoming),
            "virtual_nodes": virtual_nodes,
            "contradicts_edges": contradicts_info,
            "schema_issues": schema_issues,
            "schema_issue_count": len(schema_issues),
        }

    def heartbeat(self, process_name: str, status: str = "running", summary: str = "", extra: Dict[str, Any] = None):
        """写入当前进程心跳"""
        import os
        extra_json = json.dumps(extra, ensure_ascii=False) if extra else None
        self._conn.execute(
            "INSERT OR REPLACE INTO process_heartbeat (process_name, status, last_heartbeat, last_summary, pid, extra) VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?, ?)",
            (process_name, status, summary, os.getpid(), extra_json)
        )
        self._conn.commit()

    def cleanup_stale_heartbeats(self, cutoff_iso: str) -> int:
        """清理超过 cutoff_iso 的旧心跳（保留 daemon 自身）。返回删除数。"""
        result = self._conn.execute(
            "DELETE FROM process_heartbeat WHERE last_heartbeat < ? AND process_name != 'daemon'",
            (cutoff_iso,)
        )
        deleted = result.rowcount
        if deleted:
            self._conn.commit()
        return deleted

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

    def _normalize_edge_relation(self, relation: str) -> str:
        rel = str(relation or "").strip().upper().replace(" ", "_").replace("-", "_")
        aliases = {
            "CONTRADICT": "CONTRADICTS",
            "CONTRADICTED_BY": "CONTRADICTS",
            "FALSIFY": "CONTRADICTS",
            "FALSIFIES": "CONTRADICTS",
            "REQUIRE": "REQUIRES",
            "REQUIRED_BY": "REQUIRES",
        }
        return aliases.get(rel, rel)

    def _node_existence_map(self, node_ids: List[str]) -> Dict[str, bool]:
        clean_ids = list(dict.fromkeys(str(nid or "").strip() for nid in node_ids if str(nid or "").strip()))
        if not clean_ids:
            return {}
        placeholders = ",".join("?" * len(clean_ids))
        rows = self._conn.execute(
            f"SELECT node_id FROM knowledge_nodes WHERE node_id IN ({placeholders})",
            clean_ids
        ).fetchall()
        found = {row[0] for row in rows}
        return {nid: nid in found for nid in clean_ids}

    def _node_visibility_map(self, node_ids: List[str]) -> Dict[str, Dict[str, bool]]:
        clean_ids = list(dict.fromkeys(str(nid or "").strip() for nid in node_ids if str(nid or "").strip()))
        result = {nid: {"exists": False, "hidden": False, "virtual": False} for nid in clean_ids}
        if not clean_ids:
            return result
        placeholders = ",".join("?" * len(clean_ids))
        rows = self._conn.execute(
            f"SELECT node_id, COALESCE(ablation_active, 0) hidden, COALESCE(is_virtual, 0) virtual FROM knowledge_nodes WHERE node_id IN ({placeholders})",
            clean_ids
        ).fetchall()
        for row in rows:
            result[row["node_id"]] = {
                "exists": True,
                "hidden": int(row["hidden"] or 0) > 0,
                "virtual": int(row["virtual"] or 0) == 1,
            }
        return result

    def _active_node_filter(self, alias: str, include_hidden: bool = False, include_virtual: bool = False) -> str:
        clauses = []
        if not include_hidden:
            clauses.append(f"COALESCE({alias}.ablation_active, 0) = 0")
        if not include_virtual:
            clauses.append(f"COALESCE({alias}.is_virtual, 0) = 0")
        return " AND ".join(clauses) if clauses else "1=1"

    def _validate_node_edge(self, source_id: str, target_id: str, relation: str, allow_hidden: bool = False, allow_virtual: bool = False) -> tuple[bool, str, str, str, str]:
        source = str(source_id or "").strip()
        target = str(target_id or "").strip()
        rel = self._normalize_edge_relation(relation)
        if not source or not target or not rel:
            return False, source, target, rel, "missing endpoint or relation"
        if source == target:
            return False, source, target, rel, "self edge refused"
        visibility = self._node_visibility_map([source, target])
        if not visibility.get(source, {}).get("exists") or not visibility.get(target, {}).get("exists"):
            return False, source, target, rel, f"missing endpoint source_ok={visibility.get(source, {}).get('exists', False)} target_ok={visibility.get(target, {}).get('exists', False)}"
        blocked = []
        for role, nid in (("source", source), ("target", target)):
            info = visibility.get(nid, {})
            if info.get("hidden") and not allow_hidden:
                blocked.append(f"{role}_hidden")
            if info.get("virtual") and not allow_virtual:
                blocked.append(f"{role}_virtual")
        if blocked:
            return False, source, target, rel, "inactive endpoint " + ",".join(blocked)
        return True, source, target, rel, ""

    def add_edge(self, source_id: str, target_id: str, relation: str, weight: float = 1.0, allow_hidden: bool = False, allow_virtual: bool = False) -> bool:
        """添加一条图谱边 (Idempotent)"""
        try:
            ok, source_id, target_id, relation, reason = self._validate_node_edge(source_id, target_id, relation, allow_hidden=allow_hidden, allow_virtual=allow_virtual)
            if not ok:
                logger.warning(f"Graph: Refused edge {source_id} --[{relation}]--> {target_id}: {reason}")
                return False
            self._conn.execute(
                "INSERT OR REPLACE INTO node_edges (source_id, target_id, relation, weight) VALUES (?,?,?,?)",
                (source_id, target_id, relation, float(weight))
            )
            self._conn.commit()
            logger.debug(f"Graph: Added edge {source_id} --[{relation}]--> {target_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add edge: {e}")
            return False

    # ── 推理线接口（点线面架构）──

    def record_node_creation_context(self, node_id: str, trace_id: str = None, round_seq: int = None):
        try:
            if not node_id:
                return
            self._conn.execute(
                "INSERT OR REPLACE INTO point_creation_context (node_id, trace_id, round_seq, created_at) VALUES (?,?,?,CURRENT_TIMESTAMP)",
                (node_id, trace_id, round_seq)
            )
            self._conn.commit()
        except Exception as e:
            logger.debug(f"record_node_creation_context failed: {e}")

    def _json_dumps_potential_value(self, value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            return json.dumps(str(value), ensure_ascii=False)

    def _normalize_potential_node_ids(self, node_ids: Any) -> List[str]:
        return list(dict.fromkeys(self._parse_potential_node_ids(node_ids)))

    def _initial_potential_status(self, triage_category: str, sample: Dict[str, Any]) -> str:
        explicit = str(sample.get("status") or "").strip().lower()
        if explicit in {"open", "actionable", "observed", "noise"}:
            return explicit
        if triage_category == "actionable":
            return "open"
        if triage_category == "noise":
            return "noise"
        return "observed"

    def _potential_dedupe_key(self, potential_type: str, title: str, target_basin: str, node_ids: List[str], evidence: Any) -> str:
        clean_type = str(potential_type or "unknown").strip().lower() or "unknown"
        clean_title = " ".join(str(title or clean_type).strip().lower().split())
        clean_basin = " ".join(str(target_basin or "").strip().lower().split())
        sorted_nodes = sorted(dict.fromkeys(node_ids or []))
        if clean_type == "saturation":
            basis = {
                "v": 1,
                "type": clean_type,
                "basin": clean_basin or clean_title.replace("饱和势：", "").strip(),
            }
        elif clean_type in {"missing_basis", "co_presence", "frontier_pressure"}:
            basis = {
                "v": 1,
                "type": clean_type,
                "title": clean_title,
                "basin": clean_basin,
                "nodes": sorted_nodes,
            }
        else:
            basis = {
                "v": 1,
                "type": clean_type,
                "title": clean_title,
                "basin": clean_basin,
                "nodes": sorted_nodes,
                "evidence": evidence,
            }
        return hashlib.sha256(self._json_dumps_potential_value(basis).encode("utf-8")).hexdigest()

    def record_potential_samples(self, samples: List[Dict[str, Any]], trace_id: str = None, round_seq: int = None, source: str = "surface") -> int:
        try:
            if not samples:
                return 0
            inserted = 0
            for sample in samples:
                if not isinstance(sample, dict):
                    continue
                potential_type = str(sample.get("type") or "unknown").strip() or "unknown"
                title = str(sample.get("title") or potential_type).strip()
                detail = str(sample.get("detail") or "").strip()
                node_ids = self._normalize_potential_node_ids(sample.get("node_ids") or [])
                evidence = sample.get("evidence") or {}
                triage_category, target_basin, triage_note = self._triage_potential_sample(
                    potential_type,
                    title,
                    detail,
                    evidence,
                    sample,
                )
                dedupe_key = self._potential_dedupe_key(potential_type, title, target_basin, node_ids, evidence)
                node_ids_json = self._json_dumps_potential_value(node_ids)
                evidence_json = self._json_dumps_potential_value(evidence)
                status = self._initial_potential_status(triage_category, sample)
                existing = self._conn.execute(
                    "SELECT sample_id FROM potential_samples WHERE dedupe_key = ? "
                    "AND COALESCE(status, 'open') IN ('open', 'actionable', 'observed', 'noise') "
                    "ORDER BY created_at ASC, sample_id ASC LIMIT 1",
                    (dedupe_key,)
                ).fetchone()
                if existing:
                    self._conn.execute(
                        "UPDATE potential_samples SET occurrence_count = COALESCE(occurrence_count, 1) + 1, "
                        "last_seen_at = CURRENT_TIMESTAMP, last_seen_trace_id = ?, last_seen_round_seq = ?, last_seen_source = ?, "
                        "target_basin = COALESCE(?, target_basin), detail = ?, evidence = ?, triage_note = ? "
                        "WHERE sample_id = ?",
                        (trace_id, round_seq, source, target_basin, detail, evidence_json, triage_note, existing["sample_id"])
                    )
                    continue
                self._conn.execute(
                    "INSERT INTO potential_samples "
                    "(trace_id, round_seq, source, potential_type, triage_category, target_basin, title, detail, node_ids, evidence, triage_note, status, dedupe_key, occurrence_count, last_seen_at, last_seen_trace_id, last_seen_round_seq, last_seen_source) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,?,?,?)",
                    (
                        trace_id,
                        round_seq,
                        source,
                        potential_type,
                        triage_category,
                        target_basin,
                        title,
                        detail,
                        node_ids_json,
                        evidence_json,
                        triage_note,
                        status,
                        dedupe_key,
                        1,
                        trace_id,
                        round_seq,
                        source,
                    )
                )
                inserted += 1
            if inserted == 0:
                self._conn.commit()
                return 0
            self._conn.commit()
            return inserted
        except Exception as e:
            logger.debug(f"record_potential_samples failed: {e}")
            return 0

    def _triage_potential_sample(self, potential_type: str, title: str, detail: str, evidence: Any, sample: Dict[str, Any]) -> tuple:
        category = str(sample.get("triage_category") or "").strip().lower()
        allowed = {"actionable", "structural", "exit", "noise"}
        text = f"{potential_type} {title} {detail}".lower()
        if category not in allowed:
            if potential_type == "missing_basis":
                category = "actionable"
            elif potential_type == "saturation":
                category = "structural"
            elif potential_type in {"frontier_pressure", "co_presence"}:
                category = "exit"
            elif any(token in text for token in ("出口", "转向", "下一缺口", "escape", "frontier")):
                category = "exit"
            elif any(token in text for token in ("验证", "补足", "复查", "actionable", "check")):
                category = "actionable"
            elif any(token in text for token in ("噪声", "不可验证", "noise")):
                category = "noise"
            else:
                category = "structural"
        target_basin = str(sample.get("target_basin") or "").strip()
        if not target_basin and isinstance(evidence, dict):
            target_basin = str(evidence.get("area_hint") or evidence.get("target_basin") or "").strip()
        if not target_basin and potential_type == "saturation":
            target_basin = title.replace("饱和势：", "").strip()
        notes = {
            "actionable": "可验证势：保留为下一轮可检查线索，不自动转点或任务。",
            "structural": "结构势：仅提示地形状态，不代表事实成立。",
            "exit": "出口势：提示离开当前盆地或转向前沿，不强制执行。",
            "noise": "噪声势：保留审计痕迹，默认不进入主要上下文。",
        }
        triage_note = str(sample.get("triage_note") or notes.get(category, "")).strip()
        return category, target_basin or None, triage_note

    def count_potential_samples(self, trace_id: str = None) -> int:
        try:
            if trace_id:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM potential_samples WHERE trace_id = ?",
                    (trace_id,)
                ).fetchone()
            else:
                row = self._conn.execute("SELECT COUNT(*) FROM potential_samples").fetchone()
            return int(row[0] or 0) if row else 0
        except Exception as e:
            logger.debug(f"count_potential_samples failed: {e}")
            return 0

    def get_open_potential_samples(self, limit: int = 20, potential_type: str = None, triage_category: str = None) -> List[Dict[str, Any]]:
        try:
            params: List[Any] = []
            type_clause = ""
            if potential_type:
                type_clause = " AND potential_type = ?"
                params.append(potential_type)
            triage_clause = ""
            if triage_category:
                triage_clause = " AND COALESCE(triage_category, 'structural') = ?"
                params.append(str(triage_category).strip().lower())
            params.append(limit)
            rows = self._conn.execute(
                "SELECT sample_id, trace_id, round_seq, source, potential_type, COALESCE(triage_category, 'structural') triage_category, target_basin, title, detail, node_ids, evidence, triage_note, created_at "
                "FROM potential_samples WHERE COALESCE(status, 'open') IN ('open', 'actionable')" + type_clause + triage_clause +
                " ORDER BY created_at ASC, sample_id ASC LIMIT ?",
                params
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.debug(f"get_open_potential_samples failed: {e}")
            return []

    def resolve_potential_sample(self, sample_id: int, status: str, resolution_node_id: str = None, resolution_note: str = "") -> bool:
        try:
            resolved_status = str(status or "").strip().lower()
            allowed = {"open", "actionable", "observed", "resolved", "ignored", "rejected", "stale", "noise", "crystallized"}
            if resolved_status not in allowed:
                logger.warning(f"resolve_potential_sample refused invalid status {status}")
                return False
            if resolution_node_id and not self._node_existence_map([resolution_node_id]).get(resolution_node_id):
                logger.warning(f"resolve_potential_sample refused missing resolution node {resolution_node_id}")
                return False
            resolved_at_expr = "CURRENT_TIMESTAMP" if resolved_status not in {"open", "actionable", "observed", "noise"} else "NULL"
            cur = self._conn.execute(
                f"UPDATE potential_samples SET status = ?, resolution_node_id = ?, resolution_note = ?, resolved_at = {resolved_at_expr} "
                "WHERE sample_id = ?",
                (resolved_status, resolution_node_id, resolution_note, sample_id)
            )
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            logger.debug(f"resolve_potential_sample failed: {e}")
            return False

    def get_potential_triage_report(self, limit: int = 12, since: str = None) -> Dict[str, Any]:
        try:
            since_clause = ""
            params: List[Any] = []
            if since:
                since_clause = " AND created_at >= ?"
                params.append(str(since).strip())
            distribution = self._conn.execute(
                "SELECT COALESCE(triage_category, 'structural') triage_category, COALESCE(status, 'open') status, potential_type, COUNT(*) count "
                "FROM potential_samples WHERE 1=1" + since_clause +
                " GROUP BY COALESCE(triage_category, 'structural'), COALESCE(status, 'open'), potential_type "
                "ORDER BY count DESC LIMIT ?",
                params + [limit],
            ).fetchall()
            recent = self._conn.execute(
                "SELECT sample_id, created_at, source, potential_type, COALESCE(triage_category, 'structural') triage_category, target_basin, COALESCE(status, 'open') status, title, detail, triage_note "
                "FROM potential_samples WHERE 1=1" + since_clause +
                " ORDER BY created_at DESC, sample_id DESC LIMIT ?",
                params + [limit],
            ).fetchall()
            return {
                "distribution": [dict(r) for r in distribution],
                "recent": [dict(r) for r in recent],
            }
        except Exception as e:
            logger.debug(f"get_potential_triage_report failed: {e}")
            return {"distribution": [], "recent": []}

    def preview_potential_sample_maintenance(self, limit: int = 12, since: str = None) -> Dict[str, Any]:
        try:
            since_clause = ""
            params: List[Any] = []
            if since:
                since_clause = " AND created_at >= ?"
                params.append(str(since).strip())

            def scalar(sql: str) -> int:
                row = self._conn.execute(sql, params).fetchone()
                return int(row[0] or 0) if row else 0

            total_rows = scalar("SELECT COUNT(*) FROM potential_samples WHERE 1=1" + since_clause)
            missing_dedupe_total = scalar(
                "SELECT COUNT(*) FROM potential_samples WHERE (dedupe_key IS NULL OR dedupe_key = '')" + since_clause
            )
            active_open_total = scalar(
                "SELECT COUNT(*) FROM potential_samples WHERE COALESCE(status, 'open') IN ('open', 'actionable')" + since_clause
            )
            active_open_actionable = scalar(
                "SELECT COUNT(*) FROM potential_samples WHERE COALESCE(status, 'open') IN ('open', 'actionable') "
                "AND COALESCE(triage_category, 'structural') = 'actionable'" + since_clause
            )
            active_open_non_actionable = scalar(
                "SELECT COUNT(*) FROM potential_samples WHERE COALESCE(status, 'open') IN ('open', 'actionable') "
                "AND COALESCE(triage_category, 'structural') <> 'actionable'" + since_clause
            )
            status_distribution = self._conn.execute(
                "SELECT COALESCE(triage_category, 'structural') triage_category, COALESCE(status, 'open') status, "
                "potential_type, COUNT(*) rows, SUM(COALESCE(occurrence_count, 1)) seen, "
                "SUM(CASE WHEN dedupe_key IS NULL OR dedupe_key = '' THEN 1 ELSE 0 END) missing_dedupe "
                "FROM potential_samples WHERE 1=1" + since_clause +
                " GROUP BY COALESCE(triage_category, 'structural'), COALESCE(status, 'open'), potential_type "
                "ORDER BY rows DESC LIMIT ?",
                params + [limit],
            ).fetchall()
            non_actionable_open = self._conn.execute(
                "SELECT COALESCE(triage_category, 'structural') triage_category, potential_type, COUNT(*) rows, "
                "SUM(CASE WHEN dedupe_key IS NULL OR dedupe_key = '' THEN 1 ELSE 0 END) missing_dedupe, "
                "MIN(created_at) first_created, MAX(COALESCE(last_seen_at, created_at)) last_seen "
                "FROM potential_samples WHERE COALESCE(status, 'open') IN ('open', 'actionable') "
                "AND COALESCE(triage_category, 'structural') <> 'actionable'" + since_clause +
                " GROUP BY COALESCE(triage_category, 'structural'), potential_type "
                "ORDER BY rows DESC LIMIT ?",
                params + [limit],
            ).fetchall()
            duplicate_hotspots = self._conn.execute(
                "SELECT potential_type, COALESCE(triage_category, 'structural') triage_category, "
                "COALESCE(status, 'open') status, title, COALESCE(target_basin, '') target_basin, node_ids, "
                "COUNT(*) rows, SUM(COALESCE(occurrence_count, 1)) seen, "
                "SUM(CASE WHEN dedupe_key IS NULL OR dedupe_key = '' THEN 1 ELSE 0 END) missing_dedupe, "
                "MIN(created_at) first_created, MAX(created_at) last_created "
                "FROM potential_samples WHERE (dedupe_key IS NULL OR dedupe_key = '')" + since_clause +
                " GROUP BY potential_type, COALESCE(triage_category, 'structural'), COALESCE(status, 'open'), "
                "title, COALESCE(target_basin, ''), node_ids HAVING COUNT(*) > 1 "
                "ORDER BY rows DESC, last_created DESC LIMIT ?",
                params + [limit],
            ).fetchall()
            actionable_open_recent = self._conn.execute(
                "SELECT sample_id, created_at, source, potential_type, title, detail, node_ids, evidence, "
                "COALESCE(occurrence_count, 1) occurrence_count, dedupe_key "
                "FROM potential_samples WHERE COALESCE(status, 'open') IN ('open', 'actionable') "
                "AND COALESCE(triage_category, 'structural') = 'actionable'" + since_clause +
                " ORDER BY COALESCE(last_seen_at, created_at) DESC, sample_id DESC LIMIT ?",
                params + [limit],
            ).fetchall()
            return {
                "summary": {
                    "total_rows": total_rows,
                    "missing_dedupe_total": missing_dedupe_total,
                    "active_open_total": active_open_total,
                    "active_open_actionable": active_open_actionable,
                    "active_open_non_actionable": active_open_non_actionable,
                },
                "status_distribution": [dict(r) for r in status_distribution],
                "non_actionable_open": [dict(r) for r in non_actionable_open],
                "duplicate_hotspots": [dict(r) for r in duplicate_hotspots],
                "actionable_open_recent": [dict(r) for r in actionable_open_recent],
            }
        except Exception as e:
            logger.debug(f"preview_potential_sample_maintenance failed: {e}")
            return {
                "summary": {},
                "status_distribution": [],
                "non_actionable_open": [],
                "duplicate_hotspots": [],
                "actionable_open_recent": [],
            }

    def _parse_potential_node_ids(self, raw_node_ids: Any) -> List[str]:
        try:
            parsed = json.loads(raw_node_ids) if isinstance(raw_node_ids, str) else raw_node_ids
        except Exception:
            parsed = []
        if isinstance(parsed, str):
            parsed = [parsed]
        if not isinstance(parsed, list):
            return []
        return [str(item).strip() for item in parsed if str(item or "").strip()]

    def crystallize_potential_samples_for_node(self, node_id: str, title: str = "", limit: int = 10) -> int:
        try:
            if not node_id:
                return 0
            like_node = f"%{node_id}%"
            rows = self._conn.execute(
                "SELECT sample_id, node_ids FROM potential_samples WHERE COALESCE(status, 'open') IN ('open', 'actionable') "
                "AND COALESCE(triage_category, 'structural') = 'actionable' "
                "AND node_ids LIKE ? ORDER BY created_at ASC, sample_id ASC LIMIT ?",
                (like_node, max(limit * 3, limit))
            ).fetchall()
            resolved = 0
            for row in rows:
                if node_id not in self._parse_potential_node_ids(row["node_ids"]):
                    continue
                if self.resolve_potential_sample(row["sample_id"], "crystallized", resolution_node_id=node_id, resolution_note="node_created"):
                    resolved += 1
                    if resolved >= limit:
                        break
            return resolved
        except Exception as e:
            logger.debug(f"crystallize_potential_samples_for_node failed for {node_id}: {e}")
            return 0

    def _clean_pls_proposal_basis_ids(self, basis_ids: Any) -> List[str]:
        if isinstance(basis_ids, str):
            raw_items = [basis_ids]
        elif isinstance(basis_ids, list):
            raw_items = basis_ids
        elif isinstance(basis_ids, tuple):
            raw_items = list(basis_ids)
        else:
            raw_items = []
        return list(dict.fromkeys(str(nid or "").strip() for nid in raw_items if str(nid or "").strip()))

    def _json_safe_pls_proposal_value(self, value: Any) -> Any:
        try:
            json.dumps(value, ensure_ascii=False)
            return value
        except Exception:
            return str(value)

    def _normalize_pls_proposal_payload(
        self,
        payload: Dict[str, Any],
        basis_ids: Any = None,
        branch_id: str = "",
        parent_trace_id: str = None,
        parent_round_seq: int = None,
        source: str = "async_branch",
    ) -> tuple[Dict[str, Any], List[str], List[str]]:
        issues: List[str] = []
        if not isinstance(payload, dict):
            return {}, [], ["invalid_payload_type"]
        forbidden = sorted(k for k in payload if str(k).strip() in self.PLS_PROPOSAL_FORBIDDEN_PAYLOAD_KEYS)
        issues.extend(f"forbidden_payload_key:{key}" for key in forbidden)
        raw_basis = basis_ids if basis_ids is not None else payload.get("basis_ids")
        clean_basis = self._clean_pls_proposal_basis_ids(raw_basis)
        point_type = str(payload.get("point_type") or "CONTEXT").strip().upper()
        if point_type not in self.PLS_PROPOSAL_ALLOWED_POINT_TYPES:
            issues.append("invalid_point_type")
            point_type = "CONTEXT"
        consumed = {
            "schema_version",
            "node_id",
            "new_point_id",
            "target_node_id",
            "title",
            "name",
            "summary",
            "content",
            "detail",
            "description",
            "point_type",
            "tags",
            "resolves",
            "target_basin",
            "reasoning",
            "line_reasoning",
            "basis_reasoning",
            "basis_ids",
            "origin",
        }
        extra = {
            str(k): self._json_safe_pls_proposal_value(v)
            for k, v in payload.items()
            if str(k) not in consumed and str(k) not in self.PLS_PROPOSAL_FORBIDDEN_PAYLOAD_KEYS
        }
        origin = payload.get("origin") if isinstance(payload.get("origin"), dict) else {}
        origin = {str(k): self._json_safe_pls_proposal_value(v) for k, v in origin.items()}
        if branch_id:
            origin["branch_id"] = str(branch_id).strip()
        if parent_trace_id is not None:
            origin["parent_trace_id"] = parent_trace_id
        if parent_round_seq is not None:
            origin["parent_round_seq"] = parent_round_seq
        if source:
            origin["source"] = str(source).strip()
        normalized = {
            "schema_version": self.PLS_PROPOSAL_PAYLOAD_SCHEMA_VERSION,
            "node_id": str(payload.get("node_id") or payload.get("new_point_id") or payload.get("target_node_id") or "").strip(),
            "title": str(payload.get("title") or payload.get("name") or payload.get("summary") or "").strip(),
            "content": str(payload.get("content") or payload.get("detail") or payload.get("description") or "").strip(),
            "point_type": point_type,
            "tags": str(payload.get("tags") or "async_proposal").strip(),
            "resolves": str(payload.get("resolves") or payload.get("target_basin") or "").strip(),
            "reasoning": str(payload.get("reasoning") or payload.get("line_reasoning") or payload.get("basis_reasoning") or "").strip(),
            "basis_ids": clean_basis,
            "origin": origin,
            "extra": extra,
        }
        return normalized, clean_basis, issues

    def record_pls_proposal(
        self,
        proposal_id: str,
        proposal_type: str,
        payload: Dict[str, Any],
        basis_ids: List[str] = None,
        parent_trace_id: str = None,
        parent_round_seq: int = None,
        branch_id: str = "",
        source: str = "async_branch",
    ) -> bool:
        try:
            proposal_id = str(proposal_id or "").strip()
            proposal_type = str(proposal_type or "").strip()
            branch_id = str(branch_id or "").strip()
            source = str(source or "async_branch").strip() or "async_branch"
            if not proposal_id or not proposal_type or not isinstance(payload, dict):
                logger.warning(f"record_pls_proposal refused invalid proposal {proposal_id} type={proposal_type}")
                return False
            normalized_payload, clean_basis, schema_issues = self._normalize_pls_proposal_payload(
                payload,
                basis_ids=basis_ids,
                branch_id=branch_id,
                parent_trace_id=parent_trace_id,
                parent_round_seq=parent_round_seq,
                source=source,
            )
            if schema_issues:
                logger.warning(f"record_pls_proposal refused schema issues for {proposal_id}: {schema_issues}")
                return False
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO pls_proposals "
                "(proposal_id, parent_trace_id, parent_round_seq, branch_id, proposal_type, source, payload_json, basis_ids_json) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    proposal_id,
                    parent_trace_id,
                    parent_round_seq,
                    branch_id,
                    proposal_type,
                    source,
                    json.dumps(normalized_payload, ensure_ascii=False),
                    json.dumps(clean_basis, ensure_ascii=False),
                ),
            )
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            logger.debug(f"record_pls_proposal failed: {e}")
            return False

    def get_pls_proposals(self, status: str = "pending", limit: int = 20, branch_id: str = "") -> List[Dict[str, Any]]:
        try:
            resolved_status = str(status or "pending").strip().lower()
            params: List[Any] = []
            where = []
            if resolved_status:
                where.append("COALESCE(status, 'pending') = ?")
                params.append(resolved_status)
            if branch_id:
                where.append("branch_id = ?")
                params.append(str(branch_id).strip())
            clause = ("WHERE " + " AND ".join(where)) if where else ""
            params.append(max(1, min(int(limit or 20), 100)))
            rows = self._conn.execute(
                "SELECT proposal_id, parent_trace_id, parent_round_seq, branch_id, proposal_type, source, "
                "payload_json, basis_ids_json, status, merge_result, created_at FROM pls_proposals "
                + clause +
                " ORDER BY created_at ASC LIMIT ?",
                params,
            ).fetchall()
            proposals = []
            for row in rows:
                item = dict(row)
                try:
                    item["payload"] = json.loads(item.get("payload_json") or "{}")
                except Exception:
                    item["payload"] = {}
                try:
                    item["basis_ids"] = json.loads(item.get("basis_ids_json") or "[]")
                except Exception:
                    item["basis_ids"] = []
                normalized_payload, clean_basis, schema_issues = self._normalize_pls_proposal_payload(
                    item["payload"],
                    basis_ids=item["basis_ids"],
                    branch_id=item.get("branch_id") or "",
                    parent_trace_id=item.get("parent_trace_id"),
                    parent_round_seq=item.get("parent_round_seq"),
                    source=item.get("source") or "async_branch",
                )
                item["payload"] = normalized_payload
                item["basis_ids"] = clean_basis
                item["schema_issues"] = schema_issues
                proposals.append(item)
            return proposals
        except Exception as e:
            logger.debug(f"get_pls_proposals failed: {e}")
            return []

    def update_pls_proposal_status(self, proposal_id: str, status: str, merge_result: str = "") -> bool:
        try:
            proposal_id = str(proposal_id or "").strip()
            resolved_status = str(status or "").strip().lower()
            allowed = {"pending", "validated", "accepted", "rejected", "stale", "needs_rebase", "duplicate", "unsafe_same_generation"}
            if not proposal_id or resolved_status not in allowed:
                logger.warning(f"update_pls_proposal_status refused {proposal_id} status={status}")
                return False
            cur = self._conn.execute(
                "UPDATE pls_proposals SET status = ?, merge_result = ? WHERE proposal_id = ?",
                (resolved_status, merge_result, proposal_id),
            )
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            logger.debug(f"update_pls_proposal_status failed: {e}")
            return False

    def validate_pls_proposal(self, proposal_id: str, update_status: bool = False) -> Dict[str, Any]:
        report = {
            "proposal_id": str(proposal_id or "").strip(),
            "ok": False,
            "recommended_status": "rejected",
            "reasons": [],
            "basis_state": {},
        }
        try:
            pid = report["proposal_id"]
            if not pid:
                report["reasons"].append("missing_proposal_id")
                return report
            row = self._conn.execute(
                "SELECT proposal_id, parent_trace_id, parent_round_seq, branch_id, proposal_type, payload_json, basis_ids_json, status "
                "FROM pls_proposals WHERE proposal_id = ?",
                (pid,),
            ).fetchone()
            if not row:
                report["reasons"].append("proposal_not_found")
                return report
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except Exception:
                payload = {}
            try:
                basis_ids = json.loads(row["basis_ids_json"] or "[]")
            except Exception:
                basis_ids = []
            payload, clean_basis, schema_issues = self._normalize_pls_proposal_payload(
                payload,
                basis_ids=basis_ids,
                branch_id=row["branch_id"] or "",
                parent_trace_id=row["parent_trace_id"],
                parent_round_seq=row["parent_round_seq"],
            )
            report.update({
                "branch_id": row["branch_id"],
                "proposal_type": row["proposal_type"],
                "status": row["status"],
                "basis_ids": clean_basis,
                "payload_schema_version": payload.get("schema_version"),
            })
            if schema_issues:
                report["reasons"].extend(schema_issues)
            candidate_node_id = str(payload.get("node_id") or "").strip()
            if candidate_node_id and self._node_existence_map([candidate_node_id]).get(candidate_node_id):
                report["reasons"].append("candidate_node_already_exists")
                report["recommended_status"] = "duplicate"
            if not clean_basis:
                report["reasons"].append("missing_basis_ids")
            else:
                placeholders = ",".join("?" * len(clean_basis))
                rows = self._conn.execute(
                    f"SELECT node_id, COALESCE(is_virtual,0) is_virtual, COALESCE(ablation_active,0) ablation_active "
                    f"FROM knowledge_nodes WHERE node_id IN ({placeholders})",
                    clean_basis,
                ).fetchall()
                states = {r["node_id"]: {"exists": True, "is_virtual": int(r["is_virtual"] or 0), "ablation_active": int(r["ablation_active"] or 0)} for r in rows}
                for bid in clean_basis:
                    state = states.get(bid) or {"exists": False, "is_virtual": 0, "ablation_active": 0}
                    report["basis_state"][bid] = state
                    if not state["exists"]:
                        report["reasons"].append(f"missing_basis:{bid}")
                    if state["is_virtual"]:
                        report["reasons"].append(f"virtual_basis:{bid}")
                    if state["ablation_active"]:
                        report["reasons"].append(f"hidden_basis:{bid}")
                parent_trace_id = row["parent_trace_id"]
                parent_round_seq = row["parent_round_seq"]
                existing_basis = [bid for bid in clean_basis if report["basis_state"].get(bid, {}).get("exists")]
                if parent_trace_id is not None and parent_round_seq is not None and existing_basis:
                    existing_placeholders = ",".join("?" * len(existing_basis))
                    same_rows = self._conn.execute(
                        f"SELECT node_id FROM point_creation_context WHERE trace_id = ? AND round_seq = ? AND node_id IN ({existing_placeholders})",
                        [parent_trace_id, parent_round_seq] + existing_basis,
                    ).fetchall()
                    same_generation = [r["node_id"] for r in same_rows]
                    if same_generation:
                        report["same_generation_basis"] = same_generation
                        report["reasons"].append("basis_from_same_generation")
                        report["recommended_status"] = "unsafe_same_generation"
            if report["reasons"]:
                if report["recommended_status"] not in {"duplicate", "unsafe_same_generation"}:
                    report["recommended_status"] = "needs_rebase"
            else:
                report["ok"] = True
                report["recommended_status"] = "validated"
            if update_status:
                self.update_pls_proposal_status(
                    pid,
                    report["recommended_status"],
                    json.dumps({"ok": report["ok"], "reasons": report["reasons"]}, ensure_ascii=False),
                )
            return report
        except Exception as e:
            report["reasons"].append(f"validation_error:{str(e)[:120]}")
            return report

    def preview_pls_proposal_merge(self, proposal_id: str) -> Dict[str, Any]:
        preview = {
            "proposal_id": str(proposal_id or "").strip(),
            "ok": False,
            "mode": "dry_run",
            "blockers": [],
            "operations": [],
            "notes": ["preview_only_no_topology_writes"],
        }
        try:
            pid = preview["proposal_id"]
            if not pid:
                preview["blockers"].append("missing_proposal_id")
                return preview
            row = self._conn.execute(
                "SELECT proposal_id, parent_trace_id, parent_round_seq, branch_id, proposal_type, payload_json, basis_ids_json, status "
                "FROM pls_proposals WHERE proposal_id = ?",
                (pid,),
            ).fetchone()
            if not row:
                preview["blockers"].append("proposal_not_found")
                return preview
            validation = self.validate_pls_proposal(pid, update_status=False)
            preview["validation"] = validation
            if not validation.get("ok"):
                preview["blockers"].extend(validation.get("reasons") or ["validation_not_ok"])
                return preview
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except Exception:
                payload = {}
            try:
                basis_ids = json.loads(row["basis_ids_json"] or "[]")
            except Exception:
                basis_ids = []
            payload, clean_basis, schema_issues = self._normalize_pls_proposal_payload(
                payload,
                basis_ids=basis_ids,
                branch_id=row["branch_id"] or "",
                parent_trace_id=row["parent_trace_id"],
                parent_round_seq=row["parent_round_seq"],
            )
            if schema_issues:
                preview["blockers"].extend(schema_issues)
            node_id = str(payload.get("node_id") or "").strip()
            title = str(payload.get("title") or "").strip()
            content = str(payload.get("content") or "").strip()
            point_type = str(payload.get("point_type") or "CONTEXT").strip().upper()
            tags = str(payload.get("tags") or "async_proposal").strip()
            resolves = str(payload.get("resolves") or "").strip()
            reasoning = str(payload.get("reasoning") or "").strip()
            if not node_id:
                preview["blockers"].append("missing_node_id")
            if not title:
                preview["blockers"].append("missing_title")
            if not content:
                preview["blockers"].append("missing_content")
            if point_type not in {"LESSON", "CONTEXT"}:
                preview["blockers"].append("invalid_point_type")
            if not clean_basis:
                preview["blockers"].append("missing_basis_ids")
            if not reasoning:
                preview["blockers"].append("missing_line_reasoning")
            if preview["blockers"]:
                return preview
            preview["operations"] = [
                {
                    "op": "planned_point_write",
                    "node_id": node_id,
                    "point_type": point_type,
                    "title": title,
                    "content": content,
                    "tags": tags,
                    "resolves": resolves,
                    "source": "proposal_merge",
                }
            ]
            for basis_id in clean_basis:
                preview["operations"].append({
                    "op": "planned_line_write",
                    "new_point_id": node_id,
                    "basis_point_id": basis_id,
                    "reasoning": reasoning,
                    "same_round": 0,
                    "source": "proposal_merge",
                })
            preview["ok"] = True
            return preview
        except Exception as e:
            preview["blockers"].append(f"preview_error:{str(e)[:120]}")
            return preview

    def create_reasoning_line(self, new_point_id: str, basis_point_id: str, reasoning: str = "", source: str = "GP", same_round: int = 0, trace_id: str = None, round_seq: int = None, allow_hidden: bool = False, allow_virtual: bool = False) -> bool:
        """创建一条推理线：新点基于旧点产生"""
        try:
            new_point_id = str(new_point_id or "").strip()
            basis_point_id = str(basis_point_id or "").strip()
            if not new_point_id or not basis_point_id:
                logger.warning(f"Line: Refused missing endpoint {new_point_id} -> {basis_point_id}")
                return False
            if new_point_id == basis_point_id:
                logger.warning(f"Line: Refused self line {new_point_id} -> {basis_point_id}")
                return False
            visibility = self._node_visibility_map([new_point_id, basis_point_id])
            if not visibility.get(new_point_id, {}).get("exists") or not visibility.get(basis_point_id, {}).get("exists"):
                logger.warning(
                    f"Line: Refused orphan line {new_point_id} -> {basis_point_id} "
                    f"(new_ok={visibility.get(new_point_id, {}).get('exists', False)}, basis_ok={visibility.get(basis_point_id, {}).get('exists', False)})"
                )
                return False
            blocked = []
            for role, nid in (("new", new_point_id), ("basis", basis_point_id)):
                info = visibility.get(nid, {})
                if info.get("hidden") and not allow_hidden:
                    blocked.append(f"{role}_hidden")
                if info.get("virtual") and not allow_virtual:
                    blocked.append(f"{role}_virtual")
            if blocked:
                logger.warning(f"Line: Refused inactive endpoint {new_point_id} -> {basis_point_id}: {','.join(blocked)}")
                return False
            self._conn.execute(
                "INSERT INTO reasoning_lines (new_point_id, basis_point_id, reasoning, source, same_round, trace_id, round_seq) VALUES (?,?,?,?,?,?,?)",
                (new_point_id, basis_point_id, reasoning, source, same_round, trace_id, round_seq)
            )
            self._conn.commit()
            logger.debug(f"Line: {new_point_id} --[based_on]--> {basis_point_id} (source={source})")
            return True
        except Exception as e:
            logger.error(f"Failed to create reasoning line: {e}")
            return False

    def get_reasoning_basis_ids(self, new_point_id: str, include_same_round: bool = True) -> set:
        try:
            same_round_clause = "" if include_same_round else " AND same_round = 0"
            rows = self._conn.execute(
                "SELECT DISTINCT basis_point_id FROM reasoning_lines WHERE new_point_id = ?" + same_round_clause,
                (new_point_id,)
            ).fetchall()
            return {r[0] for r in rows}
        except Exception:
            return set()

    def get_incoming_line_count(self, node_id: str, include_hidden: bool = False, include_virtual: bool = False) -> int:
        """获取节点的入线数（被多少新点基于它产生）"""
        try:
            new_filter = self._active_node_filter("new_node", include_hidden, include_virtual)
            basis_filter = self._active_node_filter("basis_node", include_hidden, include_virtual)
            row = self._conn.execute(
                f"""SELECT COUNT(*)
                    FROM reasoning_lines rl
                    JOIN knowledge_nodes new_node ON new_node.node_id = rl.new_point_id
                    JOIN knowledge_nodes basis_node ON basis_node.node_id = rl.basis_point_id
                    WHERE rl.basis_point_id = ?
                      AND COALESCE(rl.same_round, 0) = 0
                      AND {new_filter}
                      AND {basis_filter}""",
                (node_id,)
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def get_incoming_count_percentile(self, percentile: int = 75, include_hidden: bool = False, include_virtual: bool = False) -> int:
        """获取入线数分布的指定百分位数（自适应阈值用）。
        返回值：入线数 >= 此值的节点为"基础"。
        空库或无数据时返回 0。"""
        try:
            new_filter = self._active_node_filter("new_node", include_hidden, include_virtual)
            basis_filter = self._active_node_filter("basis_node", include_hidden, include_virtual)
            incoming_subquery = f"""SELECT COUNT(*) as incoming
                    FROM reasoning_lines rl
                    JOIN knowledge_nodes new_node ON new_node.node_id = rl.new_point_id
                    JOIN knowledge_nodes basis_node ON basis_node.node_id = rl.basis_point_id
                    WHERE COALESCE(rl.same_round, 0) = 0
                      AND {new_filter}
                      AND {basis_filter}
                    GROUP BY rl.basis_point_id"""
            row = self._conn.execute(
                f"""SELECT incoming FROM (
                    {incoming_subquery}
                ) ORDER BY incoming LIMIT 1 OFFSET (
                    SELECT CAST(COUNT(*) * ? / 100 AS INTEGER) FROM (
                        {incoming_subquery}
                    )
                )""",
                (percentile,)
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def get_incoming_line_counts_batch(self, node_ids: list, include_hidden: bool = False, include_virtual: bool = False) -> dict:
        """批量获取入线数，避免 N+1 查询"""
        if not node_ids:
            return {}
        try:
            placeholders = ",".join("?" * len(node_ids))
            new_filter = self._active_node_filter("new_node", include_hidden, include_virtual)
            basis_filter = self._active_node_filter("basis_node", include_hidden, include_virtual)
            rows = self._conn.execute(
                f"""SELECT rl.basis_point_id, COUNT(*) as cnt
                    FROM reasoning_lines rl
                    JOIN knowledge_nodes new_node ON new_node.node_id = rl.new_point_id
                    JOIN knowledge_nodes basis_node ON basis_node.node_id = rl.basis_point_id
                    WHERE rl.basis_point_id IN ({placeholders})
                      AND COALESCE(rl.same_round, 0) = 0
                      AND {new_filter}
                      AND {basis_filter}
                    GROUP BY rl.basis_point_id""",
                node_ids
            ).fetchall()
            result = {nid: 0 for nid in node_ids}
            result.update({row[0]: row[1] for row in rows})
            return result
        except Exception:
            return {nid: 0 for nid in node_ids}

    def get_dependency_impact_report(self, node_id: str, max_depth: int = 3, limit: int = 80) -> Dict[str, Any]:
        try:
            node_id = str(node_id or "").strip()
            if not node_id:
                return {"root": "", "title": "", "impacts": [], "summary": {}}
            root = self._conn.execute(
                "SELECT node_id, title FROM knowledge_nodes WHERE node_id = ?",
                (node_id,)
            ).fetchone()
            if not root:
                return {"root": node_id, "title": "", "impacts": [], "summary": {"missing_root": 1}}
            max_depth = max(1, min(6, int(max_depth or 3)))
            limit = max(1, min(200, int(limit or 80)))
            frontier = [(node_id, 0)]
            visited = {node_id}
            impacts: List[Dict[str, Any]] = []
            while frontier and len(impacts) < limit:
                current, depth = frontier.pop(0)
                if depth >= max_depth:
                    continue
                rows = self._conn.execute(
                    """SELECT rl.new_point_id, rl.reasoning, k.title,
                              (SELECT COUNT(*) FROM reasoning_lines rb WHERE rb.new_point_id = rl.new_point_id AND COALESCE(rb.same_round,0)=0) basis_count,
                              (SELECT COUNT(*) FROM node_edges e WHERE e.target_id = rl.new_point_id AND LOWER(e.relation) IN ('contradicts','falsifies','falsify','contradict','rebuts','undercuts','supersedes','narrows_scope')) incoming_decay
                       FROM reasoning_lines rl
                       LEFT JOIN knowledge_nodes k ON k.node_id = rl.new_point_id
                       WHERE rl.basis_point_id = ? AND COALESCE(rl.same_round,0)=0
                       ORDER BY rl.created_at DESC""",
                    (current,)
                ).fetchall()
                for row in rows:
                    child = row["new_point_id"]
                    if not child or child in visited:
                        continue
                    visited.add(child)
                    child_depth = depth + 1
                    basis_count = int(row["basis_count"] or 0)
                    incoming_decay = int(row["incoming_decay"] or 0)
                    if child_depth == 1 and basis_count <= 1:
                        status = "needs_recheck"
                    elif basis_count <= child_depth:
                        status = "dependency_risk"
                    elif incoming_decay > 0:
                        status = "already_under_decay"
                    else:
                        status = "still_supported"
                    impacts.append({
                        "node_id": child,
                        "title": row["title"],
                        "depth": child_depth,
                        "basis_count": basis_count,
                        "status": status,
                        "reasoning": row["reasoning"],
                    })
                    if len(impacts) >= limit:
                        break
                    frontier.append((child, child_depth))
            summary: Dict[str, int] = {}
            for item in impacts:
                key = item.get("status") or "unknown"
                summary[key] = summary.get(key, 0) + 1
            return {
                "root": root["node_id"],
                "title": root["title"],
                "impacts": impacts,
                "summary": summary,
            }
        except Exception as e:
            logger.debug(f"get_dependency_impact_report failed for {node_id}: {e}")
            return {"root": node_id, "title": "", "impacts": [], "summary": {"error": 1}}

    def get_basis_set_for_node(self, new_point_id: str, include_same_round: bool = False, include_hidden: bool = False, include_virtual: bool = False) -> set:
        """获取某新点连线指向的所有 basis_point_id 集合（碰撞检测用）"""
        try:
            same_round_clause = "" if include_same_round else " AND same_round = 0"
            new_filter = self._active_node_filter("new_node", include_hidden, include_virtual)
            basis_filter = self._active_node_filter("basis_node", include_hidden, include_virtual)
            rows = self._conn.execute(
                f"""SELECT rl.basis_point_id
                FROM reasoning_lines rl
                JOIN knowledge_nodes new_node ON new_node.node_id = rl.new_point_id
                JOIN knowledge_nodes basis_node ON basis_node.node_id = rl.basis_point_id
                WHERE rl.new_point_id = ?{same_round_clause}
                  AND {new_filter}
                  AND {basis_filter}""",
                (new_point_id,)
            ).fetchall()
            return {row[0] for row in rows}
        except Exception:
            return set()

    def find_collision_candidates(self, basis_ids: list, min_overlap: int = 2, exclude_ids: list = None) -> list:
        """碰撞检测：查找与给定 basis_ids 有重叠的已有节点。
        返回 [(new_point_id, overlap_count, title), ...] 按重叠数降序"""
        if not basis_ids:
            return []
        try:
            exclude_ids = list(exclude_ids or [])
            placeholders = ",".join("?" * len(basis_ids))
            exclude_clause = ""
            params = list(basis_ids)
            if exclude_ids:
                exclude_placeholders = ",".join("?" * len(exclude_ids))
                exclude_clause = f" AND rl.new_point_id NOT IN ({exclude_placeholders})"
                params.extend(exclude_ids)
            params.append(min_overlap)
            rows = self._conn.execute(
                f"""SELECT rl.new_point_id, COUNT(*) as overlap
                FROM reasoning_lines rl
                JOIN knowledge_nodes k ON k.node_id = rl.new_point_id
                JOIN knowledge_nodes b ON b.node_id = rl.basis_point_id
                WHERE rl.basis_point_id IN ({placeholders})
                  AND rl.same_round = 0
                  AND COALESCE(k.is_virtual, 0) = 0
                  AND COALESCE(k.ablation_active, 0) = 0
                  {exclude_clause}
                GROUP BY rl.new_point_id
                HAVING overlap >= ?
                ORDER BY overlap DESC
                LIMIT 5""",
                params
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
                if basis_overlap_ids:
                    for bid in basis_overlap_ids[:3]:
                        self.add_edge(vid, bid, "RELATED_TO", allow_virtual=True)
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
                        self.add_edge(vid, bid, "RELATED_TO", allow_virtual=True)
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
                f"""SELECT node_id, title, COALESCE(usage_count, 1) as usage_count FROM knowledge_nodes
                WHERE node_id IN ({nh_placeholders}) AND is_virtual = 1""",
                neighbor_ids
            ).fetchall()
            if not virtual_rows:
                return []
            # 按区域聚合（取 title 前4字符作为区域标识，兼容中文）
            from collections import Counter
            area_counts = Counter()
            for vid, vtitle, usage_count in virtual_rows:
                area = vtitle[3:] if vtitle.startswith("饱和:") else vtitle
                area_counts[area] += max(1, int(usage_count or 1))
            return [(area, count) for area, count in area_counts.most_common(5)]
        except Exception as e:
            logger.error(f"get_virtual_saturation failed: {e}")
            return []

    def get_saturation_penalty_counts(self, node_ids: list, min_usage: int = 3) -> dict:
        if not node_ids:
            return {}
        try:
            node_set = set(node_ids)
            placeholders = ",".join("?" * len(node_ids))
            rows = self._conn.execute(
                f"""SELECT e.source_id, e.target_id, v.node_id, COALESCE(v.usage_count, 1) as usage_count
                FROM node_edges e
                JOIN knowledge_nodes v ON v.node_id = e.source_id OR v.node_id = e.target_id
                WHERE (e.source_id IN ({placeholders}) OR e.target_id IN ({placeholders}))
                  AND COALESCE(v.is_virtual, 0) = 1""",
                node_ids + node_ids
            ).fetchall()
            counts = {}
            for source_id, target_id, virtual_id, usage_count in rows:
                usage = int(usage_count or 1)
                if usage < min_usage:
                    continue
                node_id = target_id if source_id == virtual_id else source_id
                if node_id in node_set:
                    counts[node_id] = counts.get(node_id, 0) + usage
            return counts
        except Exception as e:
            logger.error(f"get_saturation_penalty_counts failed: {e}")
            return {}

    # ── 面组装辅助查询（供 SurfaceExpander 使用）──

    def get_neighbor_map(self, node_ids: list, include_reverse_reasoning: bool = True, weighted: bool = False, include_hidden: bool = False, include_virtual: bool = False) -> dict:
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
            src_filter = self._active_node_filter("src", include_hidden, include_virtual)
            dst_filter = self._active_node_filter("dst", include_hidden, include_virtual)
            new_filter = self._active_node_filter("new_node", include_hidden, include_virtual)
            basis_filter = self._active_node_filter("basis_node", include_hidden, include_virtual)
            
            # node_edges（始终双向，RELATED_TO边权重提升）
            for row in self._conn.execute(
                f"""SELECT e.source_id, e.target_id, e.relation
                    FROM node_edges e
                    JOIN knowledge_nodes src ON src.node_id = e.source_id
                    JOIN knowledge_nodes dst ON dst.node_id = e.target_id
                    WHERE e.source_id != e.target_id
                      AND {src_filter}
                      AND {dst_filter}
                      AND (e.source_id IN ({placeholders}) OR e.target_id IN ({placeholders}))""",
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
                f"""SELECT rl.new_point_id, rl.basis_point_id
                    FROM reasoning_lines rl
                    JOIN knowledge_nodes new_node ON new_node.node_id = rl.new_point_id
                    JOIN knowledge_nodes basis_node ON basis_node.node_id = rl.basis_point_id
                    WHERE rl.same_round = 0
                      AND rl.new_point_id != rl.basis_point_id
                      AND {new_filter}
                      AND {basis_filter}
                      AND (rl.new_point_id IN ({placeholders}) OR rl.basis_point_id IN ({placeholders}))""",
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
        """获取不参与面扩散的节点 ID 集合（消融节点 + 虚点）"""
        if not candidate_ids:
            return set()
        try:
            placeholders = ",".join("?" * len(candidate_ids))
            rows = self._conn.execute(
                f"SELECT node_id FROM knowledge_nodes WHERE node_id IN ({placeholders}) AND (ablation_active > 0 OR COALESCE(is_virtual, 0) = 1)",
                list(candidate_ids)
            ).fetchall()
            return {r[0] for r in rows}
        except Exception:
            return set()

    def get_gardener_ablation_candidates(self, candidate_ids: list, limit: int = 10) -> list:
        """园丁协同：识别高入线+有矛盾边的节点，优先消融
        
        PLS 版：消融信号来自拓扑（入线数 + CONTRADICTS 边），不是 usage win_rate。
        - 高入线数：被很多节点引用（曾经重要）
        - 有 CONTRADICTS 边：已被新知识否定（拓扑衰减信号）
        
        Returns:
            [(node_id, incoming_count, has_contradiction, title), ...] 按优先级降序
        """
        if not candidate_ids:
            return []
        
        try:
            placeholders = ",".join("?" * len(candidate_ids))
            rows = self._conn.execute(
                f"""SELECT kn.node_id, kn.title,
                          COALESCE(inc.incoming, 0) as incoming_count,
                          CASE WHEN ce.source_id IS NOT NULL THEN 1 ELSE 0 END as has_contradiction
                   FROM knowledge_nodes kn
                   LEFT JOIN (
                       SELECT basis_point_id, COUNT(*) as incoming
                       FROM reasoning_lines
                       WHERE same_round = 0 AND basis_point_id IN ({placeholders})
                       GROUP BY basis_point_id
                   ) inc ON kn.node_id = inc.basis_point_id
                   LEFT JOIN node_edges ce ON kn.node_id = ce.target_id AND ce.relation = 'CONTRADICTS'
                   WHERE kn.node_id IN ({placeholders})
                     AND kn.ablation_active = 0  -- 未被消融
                   ORDER BY has_contradiction DESC, incoming_count DESC
                   LIMIT ?""",
                candidate_ids + candidate_ids + [limit]
            ).fetchall()
            
            candidates = []
            for row in rows:
                node_id, title, incoming, has_contradiction = row
                
                # PLS 园丁评分：有矛盾边 + 高入线 = 优先消融
                # 矛盾边是拓扑衰减信号（比 win_rate 更可靠）
                gardener_score = incoming * (2.0 if has_contradiction else 1.0)
                
                candidates.append({
                    'node_id': node_id,
                    'title': title,
                    'incoming_count': incoming,
                    'has_contradiction': bool(has_contradiction),
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
                if not self.activate_ablation(node_id):
                    continue
                
                logger.info(
                    f"Gardener ablated {node_id}: incoming={candidate['incoming_count']}, "
                    f"has_contradiction={candidate.get('has_contradiction')}, title='{candidate['title'][:50]}...'"
                )
                ablated_count += 1
                
            except Exception as e:
                logger.error(f"Failed to ablate {node_id}: {e}")
        
        if ablated_count > 0:
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
                creation_rows = self._conn.execute(
                    f"SELECT node_id FROM point_creation_context WHERE node_id IN ({placeholders}) AND trace_id = ? AND round_seq = ?",
                    node_ids + [trace_id, round_seq]
                ).fetchall()
                same_round = {r[0] for r in creation_rows}
                line_rows = self._conn.execute(
                    f"SELECT DISTINCT new_point_id FROM reasoning_lines WHERE new_point_id IN ({placeholders}) AND trace_id = ? AND round_seq = ?",
                    node_ids + [trace_id, round_seq]
                ).fetchall()
                same_round.update(r[0] for r in line_rows)
                return same_round
            return set()
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

    def get_ablation_observing_nodes(self, min_duration_seconds: int = 300, ablation_states: list = None) -> list:
        """获取正在消融观察中的节点（已观察超过 min_duration_seconds 秒）。
        返回 [(node_id, title, baseline_env_ratio), ...]"""
        try:
            states = [1] if ablation_states is None else [int(s) for s in ablation_states]
            if not states:
                return []
            placeholders = ",".join("?" * len(states))
            rows = self._conn.execute(
                f"""SELECT kn.node_id, kn.title, ab.baseline_env_ratio
                FROM knowledge_nodes kn JOIN ablation_baselines ab ON kn.node_id = ab.node_id
                WHERE kn.ablation_active IN ({placeholders}) AND ab.activated_at <= strftime('%s','now') - ?""",
                states + [min_duration_seconds]
            ).fetchall()
            return [(r[0], r[1], r[2]) for r in rows]
        except Exception as e:
            logger.error(f"get_ablation_observing_nodes failed: {e}")
            return []

    def get_ablation_integrity_report(self, limit: int = 20) -> Dict[str, Any]:
        try:
            active_without_baseline = self._conn.execute(
                """SELECT k.node_id, k.ablation_active, k.title
                   FROM knowledge_nodes k
                   LEFT JOIN ablation_baselines a ON a.node_id = k.node_id
                   WHERE COALESCE(k.ablation_active,0) > 0 AND a.node_id IS NULL
                   ORDER BY k.updated_at DESC LIMIT ?""",
                (limit,)
            ).fetchall()
            baseline_without_active = self._conn.execute(
                """SELECT a.node_id, k.ablation_active, k.title
                   FROM ablation_baselines a
                   LEFT JOIN knowledge_nodes k ON k.node_id = a.node_id
                   WHERE k.node_id IS NULL OR COALESCE(k.ablation_active,0) = 0
                   ORDER BY a.activated_at DESC LIMIT ?""",
                (limit,)
            ).fetchall()
            return {
                "active_without_baseline": [dict(r) for r in active_without_baseline],
                "baseline_without_active": [dict(r) for r in baseline_without_active],
            }
        except Exception as e:
            logger.error(f"get_ablation_integrity_report failed: {e}")
            return {"active_without_baseline": [], "baseline_without_active": []}

    def repair_ablation_baseline_gaps(self, baseline_env_ratio: float = None, limit: int = 20) -> int:
        try:
            import time
            rows = self._conn.execute(
                """SELECT k.node_id
                   FROM knowledge_nodes k
                   LEFT JOIN ablation_baselines a ON a.node_id = k.node_id
                   WHERE COALESCE(k.ablation_active,0) > 0 AND a.node_id IS NULL
                   ORDER BY k.updated_at DESC LIMIT ?""",
                (limit,)
            ).fetchall()
            now = int(time.time())
            repaired = 0
            for row in rows:
                self._conn.execute(
                    "INSERT OR IGNORE INTO ablation_baselines (node_id, activated_at, baseline_env_ratio) VALUES (?,?,?)",
                    (row["node_id"], now, baseline_env_ratio)
                )
                repaired += 1
            if repaired:
                self._conn.commit()
            return repaired
        except Exception as e:
            logger.error(f"repair_ablation_baseline_gaps failed: {e}")
            return 0

    def activate_ablation(self, node_id: str, baseline_env_ratio: float = None) -> bool:
        """激活消融：从面和搜索中隐藏该节点，观察 N 轮。
        baseline_env_ratio: 消融前的环境成功率，用于后续评估向前/向后判定。"""
        try:
            if not self._node_existence_map([node_id]).get(node_id):
                logger.warning(f"activate_ablation refused missing node {node_id}")
                return False
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
            recent_threshold = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")  # 最近1小时内创建
            new_count = 0
            if neighbors:
                ph = ",".join("?" * len(neighbors))
                new_count = self._conn.execute(
                    f"SELECT COUNT(*) FROM knowledge_nodes WHERE node_id IN ({ph}) AND created_at >= ? AND COALESCE(ablation_active,0) = 0",
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

    def create_node_edge(self, source_id: str, target_id: str, relation: str, weight: float = 0.5, allow_hidden: bool = False, allow_virtual: bool = False) -> bool:
        """统一的边创建接口（daemon/工具共用）。"""
        try:
            return self.add_edge(source_id, target_id, relation, weight, allow_hidden=allow_hidden, allow_virtual=allow_virtual)
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

    def get_related_nodes(self, node_id: str, relation: str = None, direction: str = "out", include_virtual: bool = False, include_ablation: bool = False) -> List[Dict[str, Any]]:
        """获取与指定节点相连的节点 (1-hop)
        direction: 'out' (source=node_id), 'in' (target=node_id), 'both'
        """
        conn = self._conn
        query = ""
        params = []

        if direction == "out":
            query = """
                SELECT ne.relation, ne.weight, kn.node_id, kn.type AS ntype, kn.title, kn.tags,
                       kn.confidence_score, kn.trust_tier, kn.usage_count, kn.is_virtual, kn.ablation_active
                FROM node_edges ne
                JOIN knowledge_nodes kn ON ne.target_id = kn.node_id
                WHERE ne.source_id = ?
            """
            params.append(node_id)
        elif direction == "in":
            query = """
                SELECT ne.relation, ne.weight, kn.node_id, kn.type AS ntype, kn.title, kn.tags,
                       kn.confidence_score, kn.trust_tier, kn.usage_count, kn.is_virtual, kn.ablation_active
                FROM node_edges ne
                JOIN knowledge_nodes kn ON ne.source_id = kn.node_id
                WHERE ne.target_id = ?
            """
            params.append(node_id)
        
        if relation:
            query += " AND ne.relation = ?"
            params.append(relation)
        if not include_virtual:
            query += " AND COALESCE(kn.is_virtual, 0) = 0"
        if not include_ablation:
            query += " AND COALESCE(kn.ablation_active, 0) = 0"
            
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
        """DEPRECATED: 泄露 confidence_score 数字，且无活跃调用路径。用 generate_l1_digest() 替代。"""
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

    def _normalize_evidence_refs(self, evidence_refs: Any) -> List[Dict[str, str]]:
        if not evidence_refs:
            return []
        raw_refs = evidence_refs
        if isinstance(raw_refs, str):
            try:
                raw_refs = json.loads(raw_refs)
            except Exception:
                return []
        if isinstance(raw_refs, dict):
            raw_refs = [raw_refs]
        if not isinstance(raw_refs, list):
            return []
        normalized_refs: List[Dict[str, str]] = []
        for raw_ref in raw_refs:
            if not isinstance(raw_ref, dict):
                continue
            ref_type = str(raw_ref.get("type") or raw_ref.get("kind") or "").strip()
            ref_value = str(
                raw_ref.get("ref")
                or raw_ref.get("path")
                or raw_ref.get("command")
                or raw_ref.get("query")
                or raw_ref.get("trace_id")
                or raw_ref.get("source")
                or ""
            ).strip()
            excerpt = str(
                raw_ref.get("excerpt")
                or raw_ref.get("output")
                or raw_ref.get("result")
                or raw_ref.get("observation")
                or ""
            ).strip()
            observed_at = str(raw_ref.get("observed_at") or raw_ref.get("timestamp") or "").strip()
            if not ref_type or not (ref_value or excerpt):
                continue
            normalized_ref = {"type": ref_type[:80]}
            if ref_value:
                normalized_ref["ref"] = ref_value[:300]
            if excerpt:
                normalized_ref["excerpt"] = excerpt[:500]
            if observed_at:
                normalized_ref["observed_at"] = observed_at[:80]
            normalized_refs.append(normalized_ref)
            if len(normalized_refs) >= 10:
                break
        return normalized_refs

    def _has_hard_evidence(self, verification_source: str, evidence_refs: List[Dict[str, str]], trust_tier: str = "") -> bool:
        if str(trust_tier or "").strip().upper() == "HUMAN":
            return True
        for evidence_ref in evidence_refs:
            ref_type = str((evidence_ref or {}).get("type") or "").strip().lower()
            if ref_type in self.HARD_EVIDENCE_REF_TYPES:
                return True
        return False

    def create_node(self, node_id: str, ntype: str, title: str,
                    human_translation: str, tags: str,
                    full_content: str, source: str = "sedimenter",
                    prerequisites: str = None, resolves: str = None,
                    parent_node_id: str = None,
                    metadata_signature: Optional[Dict[str, Any]] = None,
                    evidence_refs: Optional[List[Dict[str, Any]]] = None,
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
        signature_input = metadata_signature
        signature_evidence_refs = None
        if isinstance(metadata_signature, dict):
            signature_input = dict(metadata_signature)
            signature_evidence_refs = signature_input.pop("evidence_refs", None)
            if signature_evidence_refs is None:
                signature_evidence_refs = signature_input.pop("evidence_ref", None)
        normalized_evidence_refs = self._normalize_evidence_refs(evidence_refs or signature_evidence_refs)
        normalized_signature = self.bind_environment_signature(
            signature_input,
            ntype,
            context_text=f"{title}\n{full_content[:500]}" if full_content else title,
        )
        if normalized_evidence_refs:
            normalized_signature["evidence_refs"] = normalized_evidence_refs
            normalized_signature["evidence_ref_count"] = str(len(normalized_evidence_refs))
            normalized_signature["evidence_ref_types"] = ",".join(sorted({ref["type"] for ref in normalized_evidence_refs}))
        resolved_validation_status = self.signature.resolve_validation_status(normalized_signature)
        if resolved_validation_status:
            normalized_signature["validation_status"] = resolved_validation_status
        downgraded_validation = False
        if normalized_signature.get("validation_status") == "validated" and not self._has_hard_evidence(verification_source or source, normalized_evidence_refs, trust_tier):
            normalized_signature["validation_status"] = "partial"
            normalized_signature["validation_gate"] = "missing_hard_evidence"
            downgraded_validation = True
            try:
                from genesis.v4.diagnostics import PipelineDiagnostics
                PipelineDiagnostics.empty_evidence_validated.record(True)
            except Exception:
                pass
        else:
            try:
                from genesis.v4.diagnostics import PipelineDiagnostics
                PipelineDiagnostics.empty_evidence_validated.record(False)
            except Exception:
                pass
        if downgraded_validation:
            normalized_signature["knowledge_state"] = "unverified"
        else:
            normalized_signature["knowledge_state"] = self.signature.resolve_knowledge_state(normalized_signature, ntype)
        # Temporal metadata: auto-set valid_from if not already present
        if "valid_from" not in normalized_signature:
            normalized_signature["valid_from"] = datetime.utcnow().strftime("%Y-%m-%d")
        signature_json = json.dumps(normalized_signature, ensure_ascii=False) if normalized_signature else None
        signature_text = self.signature.render(normalized_signature)
        validated_tier = trust_tier if trust_tier in TRUST_TIERS else "REFLECTION"
        normalized_last_verified = None if downgraded_validation else last_verified_at
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

        existing_node = self._conn.execute(
            "SELECT 1 FROM knowledge_nodes WHERE node_id = ? LIMIT 1",
            (node_id,)
        ).fetchone()
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
        try:
            resolved_voids = self.resolve_matching_voids_for_node(node_id, title=title, full_content=full_content)
            crystallized = 0 if existing_node else self.crystallize_potential_samples_for_node(node_id, title=title)
            if resolved_voids or crystallized:
                logger.info(f"NodeVault lifecycle: [{node_id}] resolved_voids={resolved_voids}, crystallized_potential={crystallized}")
        except Exception as e:
            logger.debug(f"Node lifecycle hooks skipped for {node_id}: {e}")

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
            f"UPDATE knowledge_nodes SET usage_count = usage_count + 1, updated_at = CURRENT_TIMESTAMP WHERE node_id IN ({placeholders}) AND COALESCE(ablation_active,0) = 0",
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

