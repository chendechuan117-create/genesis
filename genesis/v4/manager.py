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

class NodeVault:
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
        解决跨进程不同步：Scavenger/Fermentor 写入的新节点向量
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

    # ── 签名方法委托给 SignatureEngine ──────────────────────────────────

    def _build_dimension_registry(self):
        self.signature._build_dimension_registry()

    def _load_learned_markers(self):
        self.signature._load_learned_markers()

    def learn_signature_marker(self, dim_key: str, marker_value: str, source: str = "c_phase"):
        return self.signature.learn_signature_marker(dim_key, marker_value, source)

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
            ('trust_tier', 'TEXT DEFAULT \'REFLECTION\'')
        ]:
            try:
                conn.execute(f"ALTER TABLE knowledge_nodes ADD COLUMN {col[0]} {col[1]}")
            except sqlite3.OperationalError:
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
            snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (node_id) REFERENCES knowledge_nodes(node_id)
        )
        ''')
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

    def _normalize_environment_scope(self, scope: Any) -> str:
        value = str(scope or "").strip().lower()
        if not value:
            return ""
        return _ENVIRONMENT_SCOPE_ALIASES.get(value, value)

    def _generate_environment_epoch_id(self, scope: str) -> str:
        scope_token = "".join(ch if ch.isalnum() else "_" for ch in str(scope or "").upper()).strip("_") or "ENV"
        return f"{scope_token}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"

    def _resolve_observed_environment_scope(self, signature: Dict[str, Any]) -> str:
        return self._normalize_environment_scope((signature or {}).get("observed_environment_scope"))

    def _resolve_observed_environment_epoch(self, signature: Dict[str, Any]) -> str:
        return str((signature or {}).get("observed_environment_epoch") or "").strip()

    def _resolve_applicable_environment_scope(self, signature: Dict[str, Any]) -> str:
        signature = signature or {}
        return self._normalize_environment_scope(
            signature.get("applies_to_environment_scope") or signature.get("environment_scope")
        )

    def _resolve_applicable_environment_epoch(self, signature: Dict[str, Any]) -> str:
        signature = signature or {}
        return str(signature.get("applies_to_environment_epoch") or signature.get("environment_epoch") or "").strip()

    def _bind_environment_aliases(self, signature: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(signature or {})
        observed_scope = self._resolve_observed_environment_scope(normalized)
        observed_epoch = self._resolve_observed_environment_epoch(normalized)
        applicable_scope = self._resolve_applicable_environment_scope(normalized)
        applicable_epoch = self._resolve_applicable_environment_epoch(normalized)

        if observed_scope:
            normalized["observed_environment_scope"] = observed_scope
            if observed_epoch:
                normalized["observed_environment_epoch"] = observed_epoch
            else:
                normalized.pop("observed_environment_epoch", None)
        else:
            normalized.pop("observed_environment_scope", None)
            normalized.pop("observed_environment_epoch", None)

        if applicable_scope:
            normalized["applies_to_environment_scope"] = applicable_scope
            normalized["environment_scope"] = applicable_scope
            if applicable_epoch:
                normalized["applies_to_environment_epoch"] = applicable_epoch
                normalized["environment_epoch"] = applicable_epoch
            else:
                normalized.pop("applies_to_environment_epoch", None)
                normalized.pop("environment_epoch", None)
        else:
            normalized.pop("applies_to_environment_scope", None)
            normalized.pop("applies_to_environment_epoch", None)
            normalized.pop("environment_scope", None)
            normalized.pop("environment_epoch", None)
        return normalized

    def _apply_metadata_contract(self, signature: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(signature or {})
        if not normalized:
            return {}

        normalized[METADATA_SCHEMA_VERSION_FIELD] = METADATA_SCHEMA_VERSION

        if normalized.get("observed_environment_epoch") and not normalized.get("observed_environment_scope"):
            normalized.pop("observed_environment_epoch", None)
        if normalized.get("applies_to_environment_epoch") and not normalized.get("applies_to_environment_scope"):
            normalized.pop("applies_to_environment_epoch", None)
        if normalized.get("environment_epoch") and not normalized.get("environment_scope"):
            normalized.pop("environment_epoch", None)

        explicit_validation_status = self._resolve_validation_status(normalized)
        invalidation_reason = self._resolve_invalidation_reason(normalized)
        superseded_by_epoch = str(normalized.get("superseded_by_epoch") or "").strip()
        if superseded_by_epoch:
            normalized["superseded_by_epoch"] = superseded_by_epoch
            invalidation_reason = "superseded_env"
        elif explicit_validation_status and explicit_validation_status != "outdated":
            invalidation_reason = ""

        if invalidation_reason:
            normalized["invalidation_reason"] = invalidation_reason
            normalized["knowledge_state"] = "historical"
            normalized["validation_status"] = "outdated"
        else:
            normalized.pop("invalidation_reason", None)

        validation_status = self._resolve_validation_status(normalized)
        if validation_status == "unverified" and not normalized.get("knowledge_state"):
            normalized["knowledge_state"] = "unverified"
        elif validation_status == "outdated":
            normalized["knowledge_state"] = "historical"

        if normalized.get("knowledge_state"):
            normalized["knowledge_state"] = self._resolve_knowledge_state(normalized)
        return normalized

    def get_active_environment_epoch(self, scope: str) -> Optional[Dict[str, Any]]:
        normalized_scope = self._normalize_environment_scope(scope)
        if not normalized_scope:
            return None
        row = self._conn.execute(
            "SELECT epoch_id, scope, status, origin, snapshot_summary, created_at, superseded_at "
            "FROM environment_epochs WHERE scope = ? AND status = 'active' "
            "ORDER BY created_at DESC LIMIT 1",
            (normalized_scope,)
        ).fetchone()
        return dict(row) if row else None

    def activate_environment_epoch(self, scope: str, origin: str = "manual", snapshot_summary: str = "") -> Dict[str, Any]:
        normalized_scope = self._normalize_environment_scope(scope)
        if not normalized_scope:
            raise ValueError("environment scope is required")
        previous = self.get_active_environment_epoch(normalized_scope)
        new_epoch_id = self._generate_environment_epoch_id(normalized_scope)
        with self._conn:
            if previous:
                self._conn.execute(
                    "UPDATE environment_epochs SET status = 'superseded', superseded_at = CURRENT_TIMESTAMP WHERE epoch_id = ?",
                    (previous["epoch_id"],)
                )
            self._conn.execute(
                "INSERT INTO environment_epochs (epoch_id, scope, status, origin, snapshot_summary) VALUES (?, ?, 'active', ?, ?)",
                (new_epoch_id, normalized_scope, origin or "manual", snapshot_summary or "")
            )
        invalidated_nodes = 0
        if previous:
            invalidated_nodes = self.soft_invalidate_environment_nodes(
                normalized_scope,
                superseded_epoch_id=previous["epoch_id"],
                active_epoch_id=new_epoch_id,
            )
        else:
            invalidated_nodes = self.soft_invalidate_environment_nodes(
                normalized_scope,
                active_epoch_id=new_epoch_id,
                untagged_only=True,
            )
        return {
            "scope": normalized_scope,
            "epoch_id": new_epoch_id,
            "previous_epoch_id": previous["epoch_id"] if previous else None,
            "invalidated_nodes": invalidated_nodes,
        }

    def soft_invalidate_environment_nodes(self, scope: str, superseded_epoch_id: str = "", active_epoch_id: str = "", untagged_only: bool = False) -> int:
        normalized_scope = self._normalize_environment_scope(scope)
        if not normalized_scope:
            return 0
        rows = self._conn.execute(
            "SELECT node_id, type, metadata_signature FROM knowledge_nodes "
            "WHERE node_id NOT LIKE 'MEM_CONV%' AND metadata_signature IS NOT NULL AND metadata_signature != '{}'"
        ).fetchall()
        changed = 0
        for row in rows:
            signature = self.parse_metadata_signature(row["metadata_signature"])
            applicable_scope = self._resolve_applicable_environment_scope(signature)
            if applicable_scope != normalized_scope:
                continue
            node_epoch = self._resolve_applicable_environment_epoch(signature)
            if untagged_only and node_epoch:
                continue
            if active_epoch_id and signature.get("superseded_by_epoch") == active_epoch_id:
                continue
            if active_epoch_id and node_epoch and node_epoch == active_epoch_id:
                continue
            if superseded_epoch_id and node_epoch and node_epoch != superseded_epoch_id:
                continue
            new_signature = dict(signature)
            new_signature["applies_to_environment_scope"] = normalized_scope
            if superseded_epoch_id and not node_epoch:
                new_signature["applies_to_environment_epoch"] = superseded_epoch_id
            new_signature["knowledge_state"] = "historical"
            new_signature["validation_status"] = "outdated"
            new_signature["invalidation_reason"] = "superseded_env"
            if active_epoch_id:
                new_signature["superseded_by_epoch"] = active_epoch_id
            normalized_signature = self.normalize_metadata_signature(new_signature)
            self._conn.execute(
                "UPDATE knowledge_nodes SET metadata_signature = ?, updated_at = CURRENT_TIMESTAMP WHERE node_id = ?",
                (json.dumps(normalized_signature, ensure_ascii=False), row["node_id"])
            )
            changed += 1
        if changed:
            self._conn.commit()
            self._build_dimension_registry()  # 新节点可能带来新的自定义维度
        return changed

    def bind_environment_signature(self, signature: Any, ntype: str = "", context_text: str = "") -> Dict[str, Any]:
        normalized = self.normalize_metadata_signature(signature)
        applicable_scope = self._resolve_applicable_environment_scope(normalized)
        observed_scope = self._resolve_observed_environment_scope(normalized)
        inferred_scope = ""
        if not observed_scope and (ntype or "").upper() == "CONTEXT":
            merged_text = str(context_text or "").lower()
            if any(marker in merged_text for marker in ("/workspace", "doctor.sh", "doctor sandbox", "doctor workspace", "genesis-doctor", ".doctor-initialized")):
                inferred_scope = "doctor_workspace"
        if not observed_scope and not inferred_scope and (ntype or "").upper() == "EPISODE":
            inferred_scope = "doctor_workspace"
        if inferred_scope:
            observed_scope = observed_scope or inferred_scope
            if not applicable_scope and (ntype or "").upper() in ["CONTEXT", "EPISODE"]:
                applicable_scope = inferred_scope
        if not observed_scope and not applicable_scope:
            return normalized
        if observed_scope:
            normalized["observed_environment_scope"] = observed_scope
            if not normalized.get("observed_environment_epoch"):
                active_observed_epoch = self.get_active_environment_epoch(observed_scope)
                if active_observed_epoch:
                    normalized["observed_environment_epoch"] = active_observed_epoch["epoch_id"]
        if applicable_scope:
            normalized["applies_to_environment_scope"] = applicable_scope
            if not self._resolve_applicable_environment_epoch(normalized):
                active_applicable_epoch = self.get_active_environment_epoch(applicable_scope)
                if active_applicable_epoch:
                    normalized["applies_to_environment_epoch"] = active_applicable_epoch["epoch_id"]
        return self.normalize_metadata_signature(normalized)

    def _normalize_metadata_signature_cached(self, dict_str: str) -> Dict[str, Any]:
        return self.signature._normalize_metadata_signature_cached(dict_str)

    def normalize_metadata_signature(self, signature: Any) -> Dict[str, Any]:
        return self.signature.normalize(signature)

    def parse_metadata_signature(self, raw_signature: Any) -> Dict[str, Any]:
        return self.signature.parse(raw_signature)

    def render_metadata_signature(self, signature: Any) -> str:
        return self.signature.render(signature)

    def merge_metadata_signatures(self, *signatures: Any) -> Dict[str, Any]:
        return self.signature.merge(*signatures)

    def _signature_values(self, signature: Dict[str, Any], key: str) -> List[str]:
        return self.signature.signature_values(signature, key)

    def _resolve_validation_status(self, signature: Dict[str, Any]) -> str:
        return self.signature.resolve_validation_status(signature)

    def _resolve_knowledge_state(self, signature: Dict[str, Any], ntype: str = "") -> str:
        return self.signature.resolve_knowledge_state(signature, ntype)

    def _resolve_invalidation_reason(self, signature: Dict[str, Any]) -> str:
        return self.signature.resolve_invalidation_reason(signature)

    def _infer_invalidation_reason(self, signature: Dict[str, Any], verification_source: str = "", active_environment_epoch: str = "") -> str:
        return self.signature.infer_invalidation_reason(signature, verification_source, active_environment_epoch)

    def infer_metadata_signature(self, text: str) -> Dict[str, Any]:
        return self.signature.infer(text)

    def _infer_core_signature(self, text: str) -> Dict[str, Any]:
        return self.signature._infer_core(text)

    def infer_metadata_signature_from_artifacts(self, artifacts: List[str]) -> Dict[str, Any]:
        return self.signature.infer_from_artifacts(artifacts)

    def expand_signature_from_node_ids(self, node_ids: List[str]) -> Dict[str, Any]:
        return self.signature.expand_from_node_ids(node_ids)

    def _parse_db_timestamp(self, raw_value: Any) -> Optional[datetime]:
        if not raw_value:
            return None
        try:
            return datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
        except Exception:
            return None

    def _clamp_confidence_score(self, value: Any, default: float = 0.55) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
        return max(0.0, min(1.0, parsed))

    def _default_confidence_score(self, signature: Dict[str, Any], source: str = "sedimenter", trust_tier: str = "REFLECTION") -> float:
        validation_status = self._resolve_validation_status(self.normalize_metadata_signature(signature))
        source_key = (source or "").strip().lower()
        tier = trust_tier if trust_tier in TRUST_TIERS else "REFLECTION"
        tier_base = {"HUMAN": 0.85, "REFLECTION": 0.6, "FERMENTED": 0.45, "SCAVENGED": 0.35, "CONVERSATION": 0.5}
        base = tier_base.get(tier, 0.55)
        if validation_status == "validated":
            return max(base, 0.85)
        if validation_status == "unverified":
            return min(base, 0.35)
        if source_key in ["reflection_meta", "reflection_graph"]:
            return max(base, 0.65)
        return base

    def get_kb_entropy(self) -> Optional[Dict[str, Any]]:
        try:
            total_row = self._conn.execute(
                "SELECT COUNT(*), "
                "SUM(CASE WHEN confidence_score < 0.3 THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN confidence_score >= 0.7 THEN 1 ELSE 0 END) "
                "FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%'"
            ).fetchone()
            total_nodes = total_row[0] or 0
            if total_nodes > 0:
                return {
                    "total_nodes": total_nodes,
                    "low_confidence_pct": round((total_row[1] or 0) / total_nodes, 3),
                    "high_confidence_pct": round((total_row[2] or 0) / total_nodes, 3),
                }
        except Exception:
            pass
        return None

    def build_reliability_profile(self, row: Dict[str, Any]) -> Dict[str, Any]:
        row_dict = dict(row or {})
        signature = self.parse_metadata_signature(row_dict.get("metadata_signature"))
        validation_status = self._resolve_validation_status(signature)
        knowledge_state = self._resolve_knowledge_state(signature, row_dict.get("type") or row_dict.get("ntype") or "")
        observed_environment_scope = self._resolve_observed_environment_scope(signature)
        observed_environment_epoch = self._resolve_observed_environment_epoch(signature)
        environment_scope = self._resolve_applicable_environment_scope(signature)
        environment_epoch = self._resolve_applicable_environment_epoch(signature)
        active_environment = self.get_active_environment_epoch(environment_scope) if environment_scope else None
        active_environment_epoch = active_environment["epoch_id"] if active_environment else ""
        invalidation_reason = self._infer_invalidation_reason(
            signature,
            verification_source=row_dict.get("verification_source") or "",
            active_environment_epoch=active_environment_epoch,
        )
        if invalidation_reason:
            validation_status = "outdated"
            knowledge_state = "historical"
        epoch_stale = bool(
            environment_scope == "doctor_workspace"
            and (
                invalidation_reason == "superseded_env"
                or (active_environment_epoch and environment_epoch and environment_epoch != active_environment_epoch)
                or (knowledge_state == "historical" and not environment_epoch and invalidation_reason in ["", "superseded_env"])
            )
        )
        confidence_score = self._clamp_confidence_score(
            row_dict.get("confidence_score"),
            default=self._default_confidence_score(signature, row_dict.get("verification_source") or row_dict.get("source") or "")
        )

        verified_at = self._parse_db_timestamp(row_dict.get("last_verified_at"))
        updated_at = self._parse_db_timestamp(row_dict.get("updated_at"))
        freshness_anchor = verified_at or updated_at
        freshness_days = None
        freshness_score = 0.0
        freshness_label = "unknown"
        if freshness_anchor:
            anchor_naive = freshness_anchor.replace(tzinfo=None) if freshness_anchor.tzinfo else freshness_anchor
            freshness_days = max(0, (datetime.utcnow() - anchor_naive).days)
            if freshness_days <= 7:
                freshness_score = 2.0
                freshness_label = "fresh"
            elif freshness_days <= 30:
                freshness_score = 1.2
                freshness_label = "recent"
            elif freshness_days <= 90:
                freshness_score = 0.5
                freshness_label = "aging"
            else:
                freshness_score = 0.0
                freshness_label = "stale"

        trust_tier = row_dict.get("trust_tier") or "REFLECTION"
        tier_bonus = {"HUMAN": 2.0, "REFLECTION": 0.5, "FERMENTED": -0.5, "SCAVENGED": -1.5, "CONVERSATION": 0.0}
        state_bonus = {"current": 0.3, "unverified": -0.8, "historical": -0.2}
        trust_score = confidence_score * 6.0 + freshness_score + tier_bonus.get(trust_tier, 0.0) + state_bonus.get(knowledge_state, 0.0)
        if validation_status == "validated":
            trust_score += 1.5
        elif validation_status == "unverified":
            trust_score -= 1.0
        elif validation_status == "outdated":
            trust_score -= 1.6
        elif validation_status == "low_quality":
            trust_score -= 1.2
        if epoch_stale:
            trust_score -= 1.4

        return {
            "confidence_score": round(confidence_score, 3),
            "trust_score": round(trust_score, 3),
            "freshness_score": round(freshness_score, 3),
            "freshness_days": freshness_days,
            "freshness_label": freshness_label,
            "trust_tier": trust_tier,
            "validation_status": validation_status,
            "knowledge_state": knowledge_state,
            "invalidation_reason": invalidation_reason,
            "observed_environment_scope": observed_environment_scope,
            "observed_environment_epoch": observed_environment_epoch,
            "applies_to_environment_scope": environment_scope,
            "applies_to_environment_epoch": environment_epoch,
            "environment_scope": environment_scope,
            "environment_epoch": environment_epoch,
            "active_environment_epoch": active_environment_epoch,
            "epoch_stale": epoch_stale,
            "last_verified_at": row_dict.get("last_verified_at") or "",
            "verification_source": row_dict.get("verification_source") or "",
        }

    def patch_node_metadata(self, node_id: str, **kwargs) -> bool:
        """统一的节点元数据补丁接口（daemon/工具共用）。
        
        支持的字段：confidence_score, trust_tier, verification_source,
        metadata_signature, last_verified_at。
        签名自动经过 normalize_metadata_signature 标准化。
        """
        allowed = {"confidence_score", "trust_tier", "verification_source",
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
                inferred_reason = self._infer_invalidation_reason(sig, verification_source=verification_source)
                if inferred_reason and not self._resolve_invalidation_reason(sig):
                    sig = dict(sig)
                    sig["invalidation_reason"] = inferred_reason
            sig = self.normalize_metadata_signature(sig)
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
                "SELECT k.title, c.full_content, k.metadata_signature, k.confidence_score, k.trust_tier, c.source "
                "FROM knowledge_nodes k LEFT JOIN node_contents c ON k.node_id = c.node_id "
                "WHERE k.node_id = ?", (node_id,)
            ).fetchone()
            if row:
                self._conn.execute(
                    "INSERT INTO node_versions (node_id, title, full_content, metadata_signature, confidence_score, trust_tier, source) VALUES (?,?,?,?,?,?,?)",
                    (node_id, row["title"], row["full_content"], row["metadata_signature"], row["confidence_score"], row["trust_tier"], row["source"])
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
            "SELECT version_id, node_id, title, confidence_score, trust_tier, source, snapshot_at FROM node_versions WHERE node_id = ? ORDER BY snapshot_at DESC LIMIT ?",
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
        """获取最近的 VOID 任务（供 digest 展示，最新优先）"""
        rows = self._conn.execute(
            "SELECT void_id, query, status, created_at FROM void_tasks WHERE status = 'open' ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

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
        """读取所有进程心跳状态"""
        rows = self._conn.execute(
            "SELECT process_name, status, last_heartbeat, last_summary, pid FROM process_heartbeat ORDER BY last_heartbeat DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_daemon_status_summary(self) -> str:
        """给 G 的守护进程状态摘要"""
        beats = self.get_heartbeats()
        if not beats:
            return ""
        lines = ["[守护进程状态]"]
        for b in beats:
            ts = b.get("last_heartbeat", "?")
            name = b.get("process_name", "?")
            status = b.get("status", "?")
            summary = b.get("last_summary", "")
            summary_preview = summary[:80] if summary else ""
            lines.append(f"- {name}: {status} (last: {ts}) {summary_preview}")
        return "\n".join(lines)

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

    def delete_node(self, node_id: str) -> bool:
        """物理删除一个节点及其所有关联数据（统一删除入口）"""
        try:
            self._conn.execute("DELETE FROM node_edges WHERE source_id = ? OR target_id = ?", (node_id, node_id))
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
        清理置信度低（< 0.5，如拾荒来的数据），且超过 `days_threshold` 天未使用过的节点。
        返回清理的节点数量。
        """
        query = f"""
            SELECT node_id FROM knowledge_nodes
            WHERE confidence_score < 0.5
            AND usage_count = 0
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
        return [dict(r) for r in rows]

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
        return [dict(r) for r in rows]

    # ─── G 侧接口 ───

    def get_digest(self, top_k: int = 4) -> str:
        """精简认知目录：类别计数 + 战绩节点 + 待探索节点，消除马太效应"""
        type_rows = self._conn.execute(
            "SELECT type, COUNT(*) AS cnt FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%' GROUP BY type ORDER BY cnt DESC"
        ).fetchall()
        type_counts = {r['type']: r['cnt'] for r in type_rows}
        total = sum(type_counts.values())

        # 按战绩排序的 Top 节点（成功率高 + 使用次数多）
        top_rows = self._conn.execute(
            """SELECT node_id, type, title, usage_success_count, usage_fail_count
               FROM knowledge_nodes
               WHERE node_id NOT LIKE 'MEM_CONV%' AND (usage_success_count > 0 OR usage_count > 2)
               ORDER BY CAST(usage_success_count AS REAL) / (usage_success_count + usage_fail_count + 1) DESC,
                        usage_count DESC
               LIMIT ?""",
            (top_k,)
        ).fetchall()

        # 待探索节点：从未使用过、最近创建的高潜力节点（打破马太效应的关键）
        untested_rows = self._conn.execute(
            """SELECT node_id, type, title, confidence_score, tags
               FROM knowledge_nodes
               WHERE node_id NOT LIKE 'MEM_CONV%'
                 AND usage_count = 0
                 AND type IN ('ASSET', 'LESSON', 'CONTEXT')
               ORDER BY created_at DESC
               LIMIT ?""",
            (top_k,)
        ).fetchall()

        # 知识缺口：从 void_tasks 队列读取（不再污染 knowledge_nodes）
        void_rows = self.get_recent_voids(limit=3)

        cats = " | ".join(f"{t}:{c}" for t, c in type_counts.items() if c > 0)
        lines = [f"[认知目录] {total}节点 | {cats}"]
        if top_rows:
            lines.append("PROVEN:")
            for r in top_rows:
                w, l = r['usage_success_count'] or 0, r['usage_fail_count'] or 0
                lines.append(f"- [{r['node_id']}] <{r['type']}> {r['title']} ({w}W/{l}L)")
        if untested_rows:
            lines.append("UNTESTED (从未使用，优先尝试挂载):")
            for r in untested_rows:
                conf = r['confidence_score'] or 0.55
                lines.append(f"- [{r['node_id']}] <{r['type']}> {r['title']} (conf:{conf:.2f})")
        if void_rows:
            lines.append("VOID (已识别的知识缺口，可通过实验验证后升格为 LESSON):")
            for r in void_rows:
                lines.append(f"- [{r['void_id']}] {r['query']}")
        lines.append("需要细节时请使用 search_knowledge_nodes 搜索。")
        return "\n".join(lines)

    def get_all_titles(self) -> str:
        """给 G 看的极轻量目录卡片（排除对话记忆节点，记忆走单独通道）"""
        rows = self._conn.execute(
            "SELECT node_id, type, title, tags, prerequisites, resolves, metadata_signature, confidence_score, last_verified_at, verification_source, updated_at FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%' ORDER BY usage_count DESC"
        ).fetchall()
        lines = ["[元信息节点目录]"]
        for r in rows:
            reqs = f" | reqs:[{r['prerequisites']}]" if r['prerequisites'] else ""
            res = f" | resolves:[{r['resolves']}]" if r['resolves'] else ""
            sig = self.render_metadata_signature(r['metadata_signature'])
            sig_text = f" | sig:{sig}" if sig else ""
            reliability = self.build_reliability_profile(dict(r))
            trust_text = f" | trust:{reliability['confidence_score']:.2f}/{reliability['freshness_label']}"
            lines.append(f"<{r['type']}> [{r['node_id']}] {r['title']} | tags:{r['tags']}{reqs}{res}{sig_text}{trust_text}")
        return "\n".join(lines)

    def get_recent_memory(self, limit: int = 5) -> str:
        """拉取最近 N 条对话记忆 — G 的短期记忆，不压缩"""
        rows = self._conn.execute(
            "SELECT nc.full_content FROM knowledge_nodes kn "
            "JOIN node_contents nc ON kn.node_id = nc.node_id "
            "WHERE kn.node_id LIKE 'MEM_CONV%' "
            "ORDER BY kn.created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        if not rows:
            return ""
        lines = []
        for r in reversed(rows):  # 按时间正序
            lines.append(r['full_content'])
            lines.append("---")
        return "\n".join(lines)

    def get_conversation_digest(self, limit: int = 10) -> str:
        """对话摘要 digest：最近 N 次对话压缩成 1 行/条的话题概览。
        
        给 Multi-G 透镜提供 "似懂非懂" 级别的上下文——
        知道最近在讨论什么话题，但不知道细节，让 cognitive_frame 有素材可发散。
        """
        rows = self._conn.execute(
            "SELECT nc.full_content FROM knowledge_nodes kn "
            "JOIN node_contents nc ON kn.node_id = nc.node_id "
            "WHERE kn.node_id LIKE 'MEM_CONV%' "
            "ORDER BY kn.created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        if not rows:
            return ""
        summaries = []
        for r in reversed(rows):  # 时间正序
            content = r['full_content']
            summary = self._extract_conversation_topic(content)
            if summary:
                summaries.append(f"- {summary}")
        if not summaries:
            return ""
        return "\n".join(summaries)

    @staticmethod
    def _extract_conversation_topic(content: str, max_chars: int = 250) -> str:
        """从单条 MEM_CONV_* 中提取话题摘要（~250字符）。
        
        目标：40-60% 理解度。包含话题标题 + 关键发现/结论。
        """
        gen_part = ""
        if "\nGenesis:" in content:
            segments = content.split("\nGenesis:")
            gen_part = segments[-1].strip()
        
        if not gen_part:
            return ""
        
        # 噪音过滤器
        _noise_prefixes = ("✅", "🟢", "```", "---", "|")
        _transition_prefixes = ("完美", "现在我", "基于Op", "Op已经", "我看到Op", "让我基于", "好的", "我已经")
        
        def _is_noise(line: str) -> bool:
            if not line or len(line) < 6:
                return True
            if any(line.startswith(p) for p in _noise_prefixes):
                return True
            if any(line.startswith(p) for p in _transition_prefixes):
                return True
            return False
        
        def _clean_line(line: str) -> str:
            return line.lstrip("#").strip().strip("*").strip()
        
        # 收集有意义的行（标题 + 内容）
        useful_lines = []
        total_len = 0
        for line in gen_part.split("\n"):
            line = line.strip()
            if _is_noise(line):
                continue
            clean = _clean_line(line)
            if len(clean) < 6:
                continue
            # 截断单行过长内容
            if len(clean) > 80:
                clean = clean[:77] + "..."
            useful_lines.append(clean)
            total_len += len(clean)
            if total_len >= max_chars:
                break
        
        if not useful_lines:
            # fallback：从用户部分提取
            if "用户:" in content:
                user_part = content.split("用户:", 1)[1].split("\nGenesis:", 1)[0].strip()
                if "[GENESIS_USER_REQUEST_START]" in user_part:
                    actual = user_part.split("[GENESIS_USER_REQUEST_START]", 1)[1].strip()
                    if actual:
                        return actual[:max_chars]
            return ""
        
        return "\n  ".join(useful_lines)

    def translate_nodes(self, node_ids: List[str]) -> Dict[str, str]:
        """返回 B 面人类翻译"""
        if not node_ids:
            return {}
        placeholders = ','.join('?' * len(node_ids))
        rows = self._conn.execute(
            f"SELECT node_id, human_translation FROM knowledge_nodes WHERE node_id IN ({placeholders})",
            tuple(node_ids)
        ).fetchall()
        return {r['node_id']: r['human_translation'] for r in rows}

    def get_node_briefs(self, node_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        if not node_ids:
            return {}
        placeholders = ','.join('?' * len(node_ids))
        rows = self._conn.execute(
            f"SELECT node_id, type AS ntype, title, human_translation, tags, prerequisites, resolves, metadata_signature, usage_count, confidence_score, last_verified_at, verification_source, updated_at, trust_tier FROM knowledge_nodes WHERE node_id IN ({placeholders})",
            tuple(node_ids)
        ).fetchall()
        return {r['node_id']: dict(r) for r in rows}

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
                    trust_tier: str = "REFLECTION"):
        """创建一个新的双层节点（索引 + 内容），支持注入因果属性和自动向量化"""
        # 如果是知识类节点，自动计算其向量
        embedding_json = None
        normalized_signature = self.bind_environment_signature(
            metadata_signature,
            ntype,
            context_text=f"{title}\n{full_content[:500]}" if full_content else title,
        )
        resolved_validation_status = self._resolve_validation_status(normalized_signature)
        if resolved_validation_status:
            normalized_signature["validation_status"] = resolved_validation_status
        normalized_signature["knowledge_state"] = self._resolve_knowledge_state(normalized_signature, ntype)
        signature_json = json.dumps(normalized_signature, ensure_ascii=False) if normalized_signature else None
        signature_text = self.render_metadata_signature(normalized_signature)
        validated_tier = trust_tier if trust_tier in TRUST_TIERS else "REFLECTION"
        normalized_confidence = self._clamp_confidence_score(
            confidence_score,
            default=self._default_confidence_score(normalized_signature, source, validated_tier)
        )
        normalized_last_verified = last_verified_at
        if not normalized_last_verified and normalized_signature.get("validation_status") == "validated":
            normalized_last_verified = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        normalized_verification_source = verification_source or (source if normalized_last_verified else None)
        # V4.3: 支持 ENTITY/EVENT/ACTION 进行向量化
        embeddable_types = ["LESSON", "CONTEXT", "ASSET", "EPISODE", "ENTITY", "EVENT", "ACTION"]
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
                parent_node_id, metadata_signature, embedding, confidence_score,
                last_verified_at, verification_source, trust_tier)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(node_id) DO UPDATE SET
                 type=excluded.type, title=excluded.title,
                 human_translation=excluded.human_translation, tags=excluded.tags,
                 prerequisites=excluded.prerequisites, resolves=excluded.resolves,
                 parent_node_id=excluded.parent_node_id,
                 metadata_signature=excluded.metadata_signature,
                 embedding=excluded.embedding,
                 confidence_score=excluded.confidence_score,
                 last_verified_at=excluded.last_verified_at,
                 verification_source=excluded.verification_source,
                 trust_tier=excluded.trust_tier,
                 updated_at=CURRENT_TIMESTAMP
            """,
            (node_id, ntype, title, human_translation, tags, prerequisites, resolves, parent_node_id, signature_json, embedding_json, normalized_confidence, normalized_last_verified, normalized_verification_source, validated_tier)
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

        embeddable_types = ["LESSON", "CONTEXT", "ASSET", "EPISODE", "ENTITY", "EVENT", "ACTION", "TOOL"]
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
            sig_text = self.render_metadata_signature(r['metadata_signature'])
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

    def promote_node_confidence(self, node_id: str, boost: float = 0.4, max_score: float = 0.9) -> float:
        """
        转正晋升：
        当一个节点在实际任务中发挥了正面作用，提升其置信度。
        并移除标题中的 [拾荒] 标记。
        """
        row = self._conn.execute("SELECT confidence_score, title FROM knowledge_nodes WHERE node_id = ?", (node_id,)).fetchone()
        if not row:
            return 0.0

        current_score = row[0] if row[0] is not None else 0.5
        new_score = min(current_score + boost, max_score)

        old_title = row[1] if row[1] is not None else ""
        new_title = old_title.replace("[拾荒] ", "").strip()

        self._conn.execute(
            """
            UPDATE knowledge_nodes 
            SET confidence_score = ?, title = ?, updated_at = CURRENT_TIMESTAMP
            WHERE node_id = ?
            """,
            (new_score, new_title, node_id)
        )
        self._conn.commit()
        logger.info(f"NodeVault: Promoted node [{node_id}]. Confidence {current_score:.2f} -> {new_score:.2f}")
        return new_score

    TIER_MIN_CONFIDENCE = {
        "CORE": 0.6,
        "VERIFIED": 0.55,
        "REFLECTION": 0.1,
        "SCAVENGED": 0.1,
        "CONVERSATION": 0.1,
    }

    def decay_node_confidence(self, node_id: str, penalty: float = 0.15, min_score: float = 0.1) -> float:
        """
        贝叶斯衰减：
        penalty 随节点的历史战绩自动减轻。久经考验的知识天然抗衰减（Long-Term Potentiation）。
        高信任 tier 的节点享有地板保护，永远不会被连坐打到 GC 线以下。
        """
        import math

        row = self._conn.execute(
            "SELECT confidence_score, usage_count, usage_success_count, usage_fail_count, trust_tier FROM knowledge_nodes WHERE node_id = ?",
            (node_id,)
        ).fetchone()
        if not row:
            return 0.0
        current_score = row[0] if row[0] is not None else 0.5
        usage_count = row[1] or 0
        success_count = row[2] or 0
        fail_count = row[3] or 0
        trust_tier = row[4] or "REFLECTION"
        total = success_count + fail_count
        success_ratio = success_count / total if total > 0 else 0.0
        effective_penalty = penalty / (1.0 + success_ratio * math.log1p(usage_count))
        tier_floor = self.TIER_MIN_CONFIDENCE.get(trust_tier, min_score)
        floor = max(min_score, tier_floor)
        new_score = max(current_score - effective_penalty, floor)
        self._conn.execute(
            "UPDATE knowledge_nodes SET confidence_score = ?, updated_at = CURRENT_TIMESTAMP WHERE node_id = ?",
            (new_score, node_id)
        )
        self._conn.commit()
        logger.info(f"NodeVault: Decayed [{node_id}] {current_score:.2f}->{new_score:.2f} (eff_penalty={effective_penalty:.4f}, tier={trust_tier}, usage={usage_count})")
        return new_score

    def audit_signatures(self, limit: int = 50) -> Dict[str, Any]:
        """
        签名质量审计（算法层）：
        1. 内容重推断对比：用 infer_metadata_signature 重推断，与存储签名比较
        2. 黑名单清洗：删除自定义维度中的运营垃圾字段
        3. 规范化修复：确保 sort/dedup/cap 一致性

        自动修复可修的问题，返回审计统计。
        供 Verifier daemon 定期调用。
        """
        rows = self._conn.execute(
            """SELECT k.node_id, k.metadata_signature, k.type, k.title,
                      nc.full_content, k.verification_source
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
                 "fixed_contradiction": 0, "fixed_invalidation_reason": 0, "unchanged": 0}

        for row in rows:
            node_id = row["node_id"]
            content = row["full_content"] or row["title"] or ""
            try:
                stored_sig = json.loads(row["metadata_signature"]) if isinstance(row["metadata_signature"], str) else row["metadata_signature"]
            except Exception:
                continue
            if not isinstance(stored_sig, dict):
                continue

            stats["audited"] += 1
            new_sig = dict(stored_sig)
            changed = False

            normalized = self.normalize_metadata_signature(stored_sig)
            if json.dumps(normalized, sort_keys=True) != json.dumps(stored_sig, sort_keys=True):
                new_sig = normalized
                changed = True
                stats["fixed_normalize"] += 1

            blacklist_hits = [k for k in new_sig if k in _DIM_OPERATIONAL_BLACKLIST and k not in _PROTECTED_METADATA_FIELDS]
            if blacklist_hits:
                for k in blacklist_hits:
                    del new_sig[k]
                changed = True
                stats["fixed_blacklist"] += 1

            if content and len(content) > 20:
                re_inferred = self._infer_core_signature(content[:2000])
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

            inferred_reason = self._infer_invalidation_reason(
                new_sig,
                verification_source=row["verification_source"] or "",
            )
            if inferred_reason and self._resolve_invalidation_reason(new_sig) != inferred_reason:
                new_sig = dict(new_sig)
                new_sig["invalidation_reason"] = inferred_reason
                new_sig = self.normalize_metadata_signature(new_sig)
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
                            f"contradict={stats['fixed_contradiction']}, invalid={stats['fixed_invalidation_reason']})")
        return stats

    def record_usage_outcome(self, node_ids: List[str], success: bool, weights: Dict[str, float] = None):
        """
        Knowledge Arena 反馈闭环：
        记录节点在实际任务中的使用结果（成功/失败），
        并相应调整置信度。借鉴 Hyperspace AGI 的客观验证思想。

        weights: 可选的 {node_id: fusion_score} 权重字典。
                 提供时，boost/decay 按 fusion_score 加权——
                 排名最高的节点拿满额 boost/decay，其余按比例缩小。
                 未提供或节点不在 weights 中时，回退到均匀 boost/decay。
        """
        if not node_ids:
            return
        max_weight = max(weights.values()) if weights else 0.0
        FLOOR = 0.15
        for node_id in node_ids:
            if node_id.startswith("MEM_CONV"):
                continue
            if weights and max_weight > 0:
                raw = weights.get(node_id, 0.0)
                w = max(FLOOR, raw / max_weight)
            else:
                w = 1.0
            if success:
                self._conn.execute(
                    "UPDATE knowledge_nodes SET usage_success_count = usage_success_count + 1, updated_at = CURRENT_TIMESTAMP WHERE node_id = ?",
                    (node_id,)
                )
                self.promote_node_confidence(node_id, boost=round(0.1 * w, 4), max_score=0.95)
            else:
                self._conn.execute(
                    "UPDATE knowledge_nodes SET usage_fail_count = usage_fail_count + 1, updated_at = CURRENT_TIMESTAMP WHERE node_id = ?",
                    (node_id,)
                )
                self.decay_node_confidence(node_id, penalty=round(0.08 * w, 4), min_score=0.1)
        self._conn.commit()

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

