"""
Genesis V4 - 认知装配师 (The Factory Manager G)
核心：节点是标题，内容用链接联通。G 看标题，Op 看内容。
"""

import json
import sqlite3
import functools
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
from genesis.v4.vector_engine import VectorEngine

logger = logging.getLogger(__name__)

DB_PATH = Path.home() / '.nanogenesis' / 'workshop_v4.sqlite'

# ── Trust Tier 出生证系统 ──────────────────────────────────
# 每个知识节点携带不可伪造的来源水印，决定其初始信任和执行权限。
TRUST_TIERS = ("HUMAN", "REFLECTION", "FERMENTED", "SCAVENGED", "CONVERSATION")
TRUST_TIER_RANK = {"HUMAN": 4, "REFLECTION": 3, "FERMENTED": 2, "SCAVENGED": 1, "CONVERSATION": 0}
TOOL_EXEC_MIN_TIER = "REFLECTION"  # TOOL 节点 exec() 最低信任等级

METADATA_SIGNATURE_FIELDS = [
    "os_family",
    "runtime",
    "language",
    "framework",
    "task_kind",
    "target_kind",
    "error_kind",
    "environment_scope",
    "validation_status",
]


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
            ('trust_tier', 'TEXT DEFAULT \'REFLECTION\'')
        ]:
            try:
                conn.execute(f"ALTER TABLE knowledge_nodes ADD COLUMN {col[0]} {col[1]}")
            except sqlite3.OperationalError:
                pass
        # 回填 trust_tier：根据 verification_source 推断历史节点的出生证
        try:
            conn.execute("UPDATE knowledge_nodes SET trust_tier = 'SCAVENGED' WHERE trust_tier IS NULL AND verification_source LIKE '%scavenger%'")
            conn.execute("UPDATE knowledge_nodes SET trust_tier = 'FERMENTED' WHERE trust_tier IS NULL AND verification_source LIKE '%ferment%'")
            conn.execute("UPDATE knowledge_nodes SET trust_tier = 'CONVERSATION' WHERE trust_tier IS NULL AND node_id LIKE 'MEM_CONV%'")
            conn.execute("UPDATE knowledge_nodes SET trust_tier = 'REFLECTION' WHERE trust_tier IS NULL")
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

    @functools.lru_cache(maxsize=256)
    def _normalize_metadata_signature_cached(self, dict_str: str) -> Dict[str, Any]:
        """Internal cached worker for normalize_metadata_signature.
        
        Preserves ALL key-value pairs (known + arbitrary).
        Known fields (METADATA_SIGNATURE_FIELDS) get standard normalization.
        Arbitrary fields get basic string normalization.
        """
        try:
            signature = json.loads(dict_str)
        except Exception:
            return {}
            
        normalized: Dict[str, Any] = {}
        for key, value in signature.items():
            if not value:
                continue
            if isinstance(value, list):
                normalized[key] = value if len(value) > 1 else value[0]
            elif isinstance(value, str):
                item_str = value.strip()
                if "," in item_str:
                    split_values = [part.strip() for part in item_str.split(",") if part.strip()]
                    if split_values:
                        normalized[key] = split_values if len(split_values) > 1 else split_values[0]
                else:
                    normalized[key] = item_str
            else:
                normalized[key] = value
        return normalized

    def normalize_metadata_signature(self, signature: Any) -> Dict[str, Any]:
        if not signature:
            return {}
        if isinstance(signature, str):
            try:
                signature = json.loads(signature)
            except Exception:
                return {}
        if not isinstance(signature, dict):
            return {}
            
        # Serialize to string for LRU cache hashability
        dict_str = json.dumps(signature, sort_keys=True)
        return dict(self._normalize_metadata_signature_cached(dict_str))

    def parse_metadata_signature(self, raw_signature: Any) -> Dict[str, Any]:
        return self.normalize_metadata_signature(raw_signature)

    def render_metadata_signature(self, signature: Any) -> str:
        normalized = self.normalize_metadata_signature(signature)
        if not normalized:
            return ""
        parts = []
        rendered_keys = set()
        for key in METADATA_SIGNATURE_FIELDS:
            value = normalized.get(key)
            if not value:
                continue
            rendered_keys.add(key)
            if isinstance(value, list):
                parts.append(f"{key}={','.join(str(v) for v in value)}")
            else:
                parts.append(f"{key}={value}")
        for key in sorted(normalized.keys()):
            if key in rendered_keys:
                continue
            value = normalized[key]
            if isinstance(value, list):
                parts.append(f"{key}={','.join(str(v) for v in value)}")
            else:
                parts.append(f"{key}={value}")
        return " | ".join(parts)

    def merge_metadata_signatures(self, *signatures: Any) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for raw_signature in signatures:
            signature = self.normalize_metadata_signature(raw_signature)
            if not signature:
                continue
            for key, value in signature.items():
                if not value:
                    continue
                values = value if isinstance(value, list) else [value]
                existing = merged.get(key)
                existing_values = existing if isinstance(existing, list) else ([existing] if existing else [])
                for item in values:
                    if item not in existing_values:
                        existing_values.append(item)
                if existing_values:
                    merged[key] = existing_values if len(existing_values) > 1 else existing_values[0]
        return merged

    @functools.lru_cache(maxsize=128)
    def infer_metadata_signature(self, text: str) -> Dict[str, Any]:
        source = (text or "").lower()
        if not source.strip():
            return {}

        inferred: Dict[str, Any] = {}

        def add(key: str, value: str):
            if not value:
                return
            current = inferred.get(key)
            if not current:
                inferred[key] = value
                return
            values = current if isinstance(current, list) else [current]
            if value not in values:
                values.append(value)
            inferred[key] = values if len(values) > 1 else values[0]

        os_markers = {
            "arch": ["endeavouros", "arch linux", "archlinux", "pacman"],
            "debian": ["ubuntu", "debian", "apt-get", "apt "],
            "fedora": ["fedora", "dnf"],
            "rhel": ["centos", "red hat", "redhat", "rhel", "yum"],
            "macos": ["macos", "osx", "homebrew", "brew install"],
            "windows": ["windows", "powershell", "choco", "chocolatey", "scoop"],
        }
        for value, markers in os_markers.items():
            if any(marker in source for marker in markers):
                add("os_family", value)

        runtime_markers = {
            "docker": ["docker", "docker-compose", "compose", "container"],
            "kubernetes": ["kubernetes", "k8s", "kubectl", "helm"],
            "python": ["venv", "virtualenv", "pip", "poetry", "pyproject", "uv ", "python"],
            "node": ["node", "npm", "pnpm", "yarn", "bun"],
            "systemd": ["systemd", "systemctl", ".service"],
        }
        for value, markers in runtime_markers.items():
            if any(marker in source for marker in markers):
                add("runtime", value)

        language_markers = {
            "python": ["python", ".py", "pip", "poetry", "pyproject"],
            "javascript": ["javascript", ".js", "node.js", "npm"],
            "typescript": ["typescript", ".ts", "tsconfig", "tsx"],
            "go": ["golang", " go ", "go.mod"],
            "rust": ["rust", "cargo", "cargo.toml"],
            "java": ["java", "maven", "gradle", ".jar"],
            "shell": ["bash", "shell", ".sh"],
        }
        for value, markers in language_markers.items():
            if any(marker in source for marker in markers):
                add("language", value)

        framework_markers = {
            "fastapi": ["fastapi"],
            "flask": ["flask"],
            "django": ["django"],
            "react": ["react"],
            "nextjs": ["next.js", "nextjs"],
            "vue": ["vue"],
            "nuxt": ["nuxt"],
            "svelte": ["svelte"],
            "remix": ["remix"],
            "n8n": ["n8n"],
        }
        for value, markers in framework_markers.items():
            if any(marker in source for marker in markers):
                add("framework", value)

        task_markers = {
            "install": ["安装", "install", "setup"],
            "deploy": ["部署", "deploy", "上线", "publish"],
            "debug": ["报错", "错误", "debug", "修复", "修一下", "fix", "排查"],
            "configure": ["配置", "configure", "config"],
            "refactor": ["重构", "refactor"],
            "build": ["构建", "build"],
            "test": ["测试", "test", "pytest"],
            "migrate": ["迁移", "migrate"],
        }
        for value, markers in task_markers.items():
            if any(marker in source for marker in markers):
                add("task_kind", value)

        target_markers = {
            "dependency": ["依赖", "package", "module", "import", "pip install", "npm install"],
            "service": ["service", "daemon", "systemd", "server", "进程"],
            "database": ["mysql", "postgres", "sqlite", "redis", "数据库"],
            "api": ["api", "接口", "endpoint"],
            "frontend": ["前端", "ui", "页面", "react", "vue"],
            "backend": ["后端", "fastapi", "flask", "django", "服务端"],
        }
        for value, markers in target_markers.items():
            if any(marker in source for marker in markers):
                add("target_kind", value)

        error_markers = {
            "oom": ["out of memory", "oom", "memoryerror"],
            "timeout": ["timeout", "timed out", "超时"],
            "permission": ["permission denied", "eacces", "unauthorized", "forbidden", "权限"],
            "missing_dependency": ["module not found", "modulenotfounderror", "no module named", "command not found", "not found"],
            "network": ["connection refused", "network", "dns", "ssl", "证书"],
            "syntax": ["syntaxerror", "语法错误"],
        }
        for value, markers in error_markers.items():
            if any(marker in source for marker in markers):
                add("error_kind", value)

        if any(marker in source for marker in ["localhost", "本机", "本地", "/home/", "./", "file://"]):
            add("environment_scope", "local")
        if any(marker in source for marker in ["服务器", "远程", "ssh", "vps", "production", "prod", "staging", "云"]):
            add("environment_scope", "remote")

        if any(marker in source for marker in ["已验证", "验证通过", "works", "worked", "成功"]):
            add("validation_status", "validated")
        if any(marker in source for marker in ["待验证", "未验证", "unknown", "不确定"]):
            add("validation_status", "unverified")

        return inferred

    def infer_metadata_signature_from_artifacts(self, artifacts: List[str]) -> Dict[str, Any]:
        if not artifacts:
            return {}

        signatures: List[Dict[str, Any]] = []
        for artifact in artifacts:
            text = str(artifact or "").strip()
            if not text:
                continue
            lower = text.lower()

            signature = self.infer_metadata_signature(text)

            if lower.endswith(".py") or lower.endswith("requirements.txt") or lower.endswith("pyproject.toml") or lower.endswith("poetry.lock") or lower.endswith("uv.lock"):
                signature = self.merge_metadata_signatures(signature, {"language": "python", "runtime": "python"})
            if lower.endswith(".js") or lower.endswith("package.json") or lower.endswith("yarn.lock") or lower.endswith("pnpm-lock.yaml") or lower.endswith("bun.lockb"):
                signature = self.merge_metadata_signatures(signature, {"language": "javascript", "runtime": "node"})
            if lower.endswith(".ts") or lower.endswith(".tsx") or lower.endswith("tsconfig.json"):
                signature = self.merge_metadata_signatures(signature, {"language": "typescript", "runtime": "node"})
            if lower.endswith("go.mod") or lower.endswith(".go"):
                signature = self.merge_metadata_signatures(signature, {"language": "go"})
            if lower.endswith("cargo.toml") or lower.endswith(".rs"):
                signature = self.merge_metadata_signatures(signature, {"language": "rust"})
            if lower.endswith("pom.xml") or lower.endswith("build.gradle") or lower.endswith("build.gradle.kts"):
                signature = self.merge_metadata_signatures(signature, {"language": "java"})
            if lower.endswith("dockerfile") or "dockerfile" in lower or lower.endswith("docker-compose.yml") or lower.endswith("docker-compose.yaml") or lower.endswith("compose.yml") or lower.endswith("compose.yaml"):
                signature = self.merge_metadata_signatures(signature, {"runtime": "docker"})
            if lower.endswith(".service"):
                signature = self.merge_metadata_signatures(signature, {"runtime": "systemd", "target_kind": "service"})
            if lower.endswith(".sql"):
                signature = self.merge_metadata_signatures(signature, {"target_kind": "database"})
            if lower.endswith(".yaml") or lower.endswith(".yml"):
                if any(marker in lower for marker in ["k8s", "kubernetes", "helm", "deployment", "ingress"]):
                    signature = self.merge_metadata_signatures(signature, {"runtime": "kubernetes"})
            if any(marker in lower for marker in ["/frontend/", "frontend/", "/src/components/", "components/"]):
                signature = self.merge_metadata_signatures(signature, {"target_kind": "frontend"})
            if any(marker in lower for marker in ["/backend/", "backend/", "/api/", "api/"]):
                signature = self.merge_metadata_signatures(signature, {"target_kind": "backend"})

            if signature:
                signatures.append(signature)

        return self.merge_metadata_signatures(*signatures)

    def expand_signature_from_node_ids(self, node_ids: List[str]) -> Dict[str, Any]:
        if not node_ids:
            return {}

        briefs = self.get_node_briefs(node_ids)
        signatures: List[Any] = []
        prereq_ids: List[str] = []

        for nid in node_ids:
            brief = briefs.get(nid)
            if not brief:
                continue
            if brief.get("metadata_signature"):
                signatures.append(brief.get("metadata_signature"))
            prereq_str = (brief.get("prerequisites") or "").strip()
            if prereq_str:
                for prereq in [item.strip() for item in prereq_str.split(",") if item.strip()]:
                    if prereq not in prereq_ids:
                        prereq_ids.append(prereq)

        if prereq_ids:
            prereq_briefs = self.get_node_briefs(prereq_ids)
            for brief in prereq_briefs.values():
                if brief.get("metadata_signature"):
                    signatures.append(brief.get("metadata_signature"))

        return self.merge_metadata_signatures(*signatures)

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
        validation_status = self.normalize_metadata_signature(signature).get("validation_status")
        source_key = (source or "").strip().lower()
        tier = trust_tier if trust_tier in TRUST_TIERS else "REFLECTION"
        # trust_tier 基线
        tier_base = {"HUMAN": 0.85, "REFLECTION": 0.6, "FERMENTED": 0.45, "SCAVENGED": 0.35, "CONVERSATION": 0.5}
        base = tier_base.get(tier, 0.55)
        # validation_status 覆盖
        if validation_status == "validated":
            return max(base, 0.85)
        if validation_status == "unverified":
            return min(base, 0.35)
        # source 微调
        if source_key in ["reflection_meta", "reflection_graph"]:
            return max(base, 0.65)
        return base

    def build_reliability_profile(self, row: Dict[str, Any]) -> Dict[str, Any]:
        row_dict = dict(row or {})
        signature = self.parse_metadata_signature(row_dict.get("metadata_signature"))
        validation_status = signature.get("validation_status") or ""
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
        trust_score = confidence_score * 6.0 + freshness_score + tier_bonus.get(trust_tier, 0.0)
        if validation_status == "validated":
            trust_score += 1.5
        elif validation_status == "unverified":
            trust_score -= 1.0

        return {
            "confidence_score": round(confidence_score, 3),
            "trust_score": round(trust_score, 3),
            "freshness_score": round(freshness_score, 3),
            "freshness_days": freshness_days,
            "freshness_label": freshness_label,
            "trust_tier": trust_tier,
            "validation_status": validation_status,
            "last_verified_at": row_dict.get("last_verified_at") or "",
            "verification_source": row_dict.get("verification_source") or "",
        }

    # ─── 版本链 (Version Chain) ───

    VERSION_KEEP_LIMIT = 5  # 每个节点保留最近 N 个版本

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
                # Version GC：保留最近 N 个版本，删除更早的
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

    # ─── 心跳水位线 (Process Heartbeat) ───

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

    # ─── Graph RAG 接口 ───

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
            # 清理向量引擎内存矩阵
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

    # Trust tier 地板保护：高信任节点的 confidence 不会被 Arena penalty 打到此线以下
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
        # 贝叶斯衰减：成功率越高、使用次数越多，惩罚越轻
        total = success_count + fail_count
        success_ratio = success_count / total if total > 0 else 0.0
        effective_penalty = penalty / (1.0 + success_ratio * math.log1p(usage_count))
        # trust tier 地板保护
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

    def record_usage_outcome(self, node_ids: List[str], success: bool):
        """
        Knowledge Arena 反馈闭环：
        记录节点在实际任务中的使用结果（成功/失败），
        并相应调整置信度。借鉴 Hyperspace AGI 的客观验证思想。
        """
        if not node_ids:
            return
        for node_id in node_ids:
            if node_id.startswith("MEM_CONV"):
                continue
            if success:
                self._conn.execute(
                    "UPDATE knowledge_nodes SET usage_success_count = usage_success_count + 1, updated_at = CURRENT_TIMESTAMP WHERE node_id = ?",
                    (node_id,)
                )
                self.promote_node_confidence(node_id, boost=0.1, max_score=0.95)
            else:
                self._conn.execute(
                    "UPDATE knowledge_nodes SET usage_fail_count = usage_fail_count + 1, updated_at = CURRENT_TIMESTAMP WHERE node_id = ?",
                    (node_id,)
                )
                self.decay_node_confidence(node_id, penalty=0.08, min_score=0.1)
        self._conn.commit()

    def get_related_nodes(self, node_id: str, relation: str = None, direction: str = "out") -> List[Dict[str, Any]]:
        """获取与指定节点相连的节点 (1-hop)
        direction: 'out' (source=node_id), 'in' (target=node_id), 'both'
        """
        conn = self._conn
        query = ""
        params = []

        if direction == "out":
            query = """
                SELECT ne.relation, ne.weight, kn.* 
                FROM node_edges ne
                JOIN knowledge_nodes kn ON ne.target_id = kn.node_id
                WHERE ne.source_id = ?
            """
            params.append(node_id)
        elif direction == "in":
            query = """
                SELECT ne.relation, ne.weight, kn.* 
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
            f"SELECT node_id, type, title, human_translation, tags, prerequisites, resolves, metadata_signature, usage_count, confidence_score, last_verified_at, verification_source, updated_at, trust_tier FROM knowledge_nodes WHERE node_id IN ({placeholders})",
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
        normalized_signature = self.normalize_metadata_signature(metadata_signature)
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

    def increment_usage(self, node_ids: List[str]):
        """增加节点使用权重"""
        if not node_ids:
            return
        placeholders = ','.join('?' * len(node_ids))
        self._conn.execute(
            f"UPDATE knowledge_nodes SET usage_count = usage_count + 1, updated_at = CURRENT_TIMESTAMP WHERE node_id IN ({placeholders})",
            tuple(node_ids)
        )


class FactoryManager:
    """负责组装系统提示词 (G / Op / C)"""
    
    def __init__(self, vault: NodeVault = None):
        self.vault = vault or NodeVault()
        
    def build_g_prompt(self, recent_memory: str = "", available_tools_info: str = "", knowledge_digest: str = "", inferred_signature: str = "", daemon_status: str = "") -> str:
        """为 G (Thinker) 构建系统提示词"""
        
        digest_block = ""
        if knowledge_digest:
            digest_block = f"""[你的认知摘要 DIGEST]
以下是当前知识库的固定尺寸摘要。先读它，建立全局判断，再决定是否需要搜索细节：
{knowledge_digest}
"""

        signature_block = ""
        if inferred_signature:
            signature_block = f"""[当前任务推测签名]
以下是系统根据用户输入与上下文推测出的环境/任务特征。它不是绝对真相，但在搜索时可作为默认过滤参考：
{inferred_signature}
"""

        memory_block = ""
        if recent_memory:
            memory_block = f"""[你的近期记忆]
以下是最近几轮临时对话记忆，帮助你理解当前上下文方向：
{recent_memory}
"""
        
        tools_block = ""
        if available_tools_info:
            tools_block = f"""[Op 可用执行工具库]
请注意，除了你在搜索阶段使用的工具外，执行器(Op)在执行阶段可以使用以下工具。
你在向 Op 派发任务时，可以参考这些能力：
{available_tools_info}
"""

        daemon_block = ""
        if daemon_status:
            daemon_block = f"""{daemon_status}
"""

        return f"""你是 Genesis 大脑 (G-Process)。你是缸中之脑——只能思考、搜索知识库、派发任务给执行器 (Op)。
用简体中文回复。用户是 Genesis 创造者，偏好直接简洁。

{digest_block}
{signature_block}
{memory_block}
{tools_block}
{daemon_block}
[工作流]
Op 没有任何历史上下文。流程：你搜索思考 → dispatch_to_op → Op 执行 → 结果回传给你 → 你综合回复用户。

检索：先读 DIGEST 建立全局判断。PROVEN 是久经考验的节点；UNTESTED 是尚未使用的新知识——如果看到与任务相关的 UNTESTED 节点，优先尝试挂载（让它们有机会证明自己）。需要细节时用 search_knowledge_nodes 定向搜索。不要为了形式盲目搜索。
派发：调用 dispatch_to_op(op_intent, active_nodes, instructions)。需要读文件、查日志等侦察任务也必须派发给 Op——你没有任何直接操作现实世界的能力。
综合：收到 Op 结果后，结合用户原始诉求做最终回复（纯文本，不调工具）。Op 已经执行完了，禁止说"将会执行"。还需更多工作则再次 dispatch。

收到 [Dispatch Review] 时优先修正；确认无误则 instructions 首行写 [REVIEW_OVERRIDE] 并说明理由。
最终回复要综合取舍，不要机械复读 Op 原文。
"""

    def build_op_prompt(self, task_payload: dict) -> str:
        """为 Op (Executor) 构建系统提示词"""
        
        op_intent = task_payload.get("op_intent", "未定义目标")
        instructions = task_payload.get("instructions", "无")
        node_ids = task_payload.get("active_nodes", [])
        
        # 注入节点内容
        injection_text = ""
        if node_ids:
            node_contents = self.vault.get_multiple_contents(node_ids)
            if node_contents:
                injection_text = "\n[系统注入：G 为你准备的认知参考节点]\n"
                for nid, text in node_contents.items():
                    injection_text += f"--- NODE: {nid} ---\n{text}\n"

        return f"""你是 Genesis 执行器 (Op-Process)。只管干活，不需要历史背景。
用简体中文回复。

[任务]
目标: {op_intent}

执行建议:
{instructions}
{injection_text}

[规则]
1. 立即用工具（Shell、File、Web 等）执行目标。遇到报错自行调整重试。
2. 你可能是来执行命令的，也可能是来当侦察兵读取文件的——仔细看 G 的指令。
3. 你是 G 调用的子程序，不直接面向用户。侦察任务必须在 FINDINGS 里写出读到的关键内容，否则 G 看不到。
4. 任务完成、阶段性完成、或穷尽方法失败时，输出执行报告：

```op_result
STATUS: SUCCESS | PARTIAL | FAILED
SUMMARY:
<达成了什么、没达成什么>

FINDINGS:
<侦察结果（文件内容/日志/配置），纯执行任务写 NONE>

CHANGES_MADE:
- <实际修改/关键动作，没有写 NONE>

ARTIFACTS:
- <生成或修改的文件路径，没有写 NONE>

OPEN_QUESTIONS:
- <未解决问题/需要 G 决策的点，没有写 NONE>
```
"""

    def render_op_result_for_g(self, op_result: dict) -> str:
        """将 Op 的执行报告压缩成适合注入给 G 的结构化摘要"""
        try:
            status = op_result.get("status", "UNKNOWN")
            summary = op_result.get("summary", "") or "无摘要"
            findings = op_result.get("findings", "") or "无侦察结果"
            changes = op_result.get("changes_made", []) or []
            artifacts = op_result.get("artifacts", []) or []
            open_questions = op_result.get("open_questions", []) or []
            raw_output = (op_result.get("raw_output", "") or "").strip()

            output = [
                "[Op 子程序执行报告]",
                f"STATUS: {status}",
                "SUMMARY:",
                summary,
                "",
                "FINDINGS:",
                findings,
                ""
            ]

            output.append("CHANGES_MADE:")
            if changes:
                output.extend([f"- {item}" for item in changes])
            else:
                output.append("- NONE")

            output.append("ARTIFACTS:")
            if artifacts:
                output.extend([f"- {item}" for item in artifacts])
            else:
                output.append("- NONE")

            output.append("OPEN_QUESTIONS:")
            if open_questions:
                output.extend([f"- {item}" for item in open_questions])
            else:
                output.append("- NONE")

            if raw_output and raw_output != summary:
                preview = raw_output[:500] + ("..." if len(raw_output) > 500 else "")
                output.extend(["RAW_OUTPUT:", preview])

            return "\n".join(output)

        except Exception as e:
            return f"[Op 子程序执行报告]\nSTATUS: UNKNOWN\nSUMMARY:\n渲染 Op 结果失败: {e}"

    def render_dispatch_for_human(self, task_payload: dict) -> str:
        """渲染 G 派发给 Op 的任务书给人类看"""
        try:
            nodes = task_payload.get("active_nodes", [])
            translations = self.vault.translate_nodes(nodes)
            
            output = [
                "🧠 **[大脑 (G) 已完成思考，正在派发任务给执行器 (Op)]**",
                f"**目标：** {task_payload.get('op_intent', '未定义')}",
                "",
            ]
            
            if nodes:
                output.append("**挂载认知节点：**")
                for node_id in nodes:
                    trans = translations.get(node_id, "未知节点")
                    prefix = "🧰" if "ASSET" in node_id else "🔌" if "TOOL" in node_id else "🧠" if "CTX" in node_id or "EP" in node_id else "📖"
                    output.append(f"{prefix} `[{node_id}]` {trans}")
                output.append("")
                
            output.append("**执行建议：**")
            # 缩略显示 instructions
            instr = task_payload.get("instructions", "")
            if len(instr) > 200:
                instr = instr[:200] + "..."
            output.append(f"> {instr.replace(chr(10), chr(10)+'> ')}")
                
            return "\n".join(output)
            
        except Exception as e:
            return f"⚠️ 渲染派发书时发生异常: {e}"


class NodeManagementTools:
    """对话记忆管理器 — 负责短期记忆的写入与滑动窗口清理"""
    
    def __init__(self, vault: NodeVault):
        self.vault = vault

    def store_conversation(self, user_msg: str, agent_response: str):
        """记录 G 的短期记忆（纯时间序列，给 G 起步上下文用的）"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        node_id = f"MEM_CONV_{ts}"
        title = user_msg[:40].replace("\n", " ").strip()
        memory_content = f"用户: {user_msg[:500]}\nGenesis: {agent_response[:800]}"
        
        self.vault.create_node(
            node_id=node_id,
            ntype="EPISODE",
            title=title,
            human_translation=f"对话记忆 ({ts})",
            tags="memory,conversation,episode",
            full_content=memory_content,
            source="conversation",
            trust_tier="CONVERSATION"
        )
        logger.info(f"NodeManagement: Stored conversation → [{node_id}]")
        self._cleanup_old_memories()

    def _cleanup_old_memories(self, limit: int = 10):
        """记忆滑动窗口：清理超出的老旧短期记忆，防止数据库淤积"""
        try:
            conn = self.vault._conn
            cursor = conn.execute(
                "SELECT node_id FROM knowledge_nodes WHERE node_id LIKE 'MEM_CONV_%' ORDER BY created_at DESC LIMIT ?", 
                (limit,)
            )
            keep_ids = [row[0] for row in cursor.fetchall()]
            
            if not keep_ids:
                return

            placeholders = ','.join('?' * len(keep_ids))
            del_cursor = conn.execute(
                f"SELECT node_id FROM knowledge_nodes WHERE node_id LIKE 'MEM_CONV_%' AND node_id NOT IN ({placeholders})",
                tuple(keep_ids)
            )
            to_delete = [row[0] for row in del_cursor.fetchall()]

            if to_delete:
                for nid in to_delete:
                    self.vault.delete_node(nid)
                logger.info(f"NodeManagement: Memory sliding window purged {len(to_delete)} old conversations.")
        except Exception as e:
            logger.error(f"Failed to cleanup old memories: {e}")

