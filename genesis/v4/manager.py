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
    
    def __new__(cls, db_path: Path = DB_PATH):
        if cls._instance is None:
            cls._instance = super(NodeVault, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_path: Path = DB_PATH):
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
        
        # 启动并加载向量引擎
        self.vector_engine = VectorEngine()
        self.vector_engine.initialize()
        self._load_embeddings_to_memory()
        self._initialized = True

    def _load_embeddings_to_memory(self):
        rows = self._conn.execute("SELECT node_id, embedding FROM knowledge_nodes WHERE embedding IS NOT NULL AND node_id NOT LIKE 'MEM_CONV%'").fetchall()
        self.vector_engine.load_matrix([dict(r) for r in rows])
        
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
        for col in [
            ('prerequisites', 'TEXT'),
            ('resolves', 'TEXT'),
            ('metadata_signature', 'TEXT'),
            ('embedding', 'TEXT'),
            ('confidence_score', 'REAL DEFAULT 0.55'),
            ('last_verified_at', 'TIMESTAMP'),
            ('verification_source', 'TEXT')
        ]:
            try:
                conn.execute(f"ALTER TABLE knowledge_nodes ADD COLUMN {col[0]} {col[1]}")
            except sqlite3.OperationalError:
                pass
        conn.execute('''
        CREATE TABLE IF NOT EXISTS node_contents (
            node_id TEXT PRIMARY KEY,
            full_content TEXT NOT NULL,
            source TEXT DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
        """Internal cached worker for normalize_metadata_signature."""
        try:
            signature = json.loads(dict_str)
        except Exception:
            return {}
            
        normalized: Dict[str, Any] = {}
        for key in METADATA_SIGNATURE_FIELDS:
            value = signature.get(key)
            if value:
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
        for key in METADATA_SIGNATURE_FIELDS:
            value = normalized.get(key)
            if not value:
                continue
            if isinstance(value, list):
                parts.append(f"{key}={','.join(value)}")
            else:
                parts.append(f"{key}={value}")
        return " | ".join(parts)

    def merge_metadata_signatures(self, *signatures: Any) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for raw_signature in signatures:
            signature = self.normalize_metadata_signature(raw_signature)
            if not signature:
                continue
            for key in METADATA_SIGNATURE_FIELDS:
                value = signature.get(key)
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

    def _default_confidence_score(self, signature: Dict[str, Any], source: str = "sedimenter") -> float:
        validation_status = self.normalize_metadata_signature(signature).get("validation_status")
        source_key = (source or "").strip().lower()
        if validation_status == "validated":
            return 0.85
        if validation_status == "unverified":
            return 0.35
        if source_key in ["reflection_meta", "reflection_graph"]:
            return 0.65
        if source_key == "reflection":
            return 0.6
        return 0.55

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

        trust_score = confidence_score * 6.0 + freshness_score
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
            "validation_status": validation_status,
            "last_verified_at": row_dict.get("last_verified_at") or "",
            "verification_source": row_dict.get("verification_source") or "",
        }

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
        """物理删除一个节点及其内容和连线"""
        try:
            self._conn.execute("DELETE FROM node_edges WHERE source_id = ? OR target_id = ?", (node_id, node_id))
            self._conn.execute("DELETE FROM node_contents WHERE node_id = ?", (node_id,))
            self._conn.execute("DELETE FROM knowledge_nodes WHERE node_id = ?", (node_id,))
            self._conn.commit()
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
        type_rows = self._conn.execute(
            "SELECT type, COUNT(*) AS cnt FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%' GROUP BY type ORDER BY type ASC"
        ).fetchall()
        type_counts = {r['type']: r['cnt'] for r in type_rows}

        total_nodes = sum(type_counts.values())
        total_edges = self._conn.execute("SELECT COUNT(*) FROM node_edges").fetchone()[0]
        signature_rows = self._conn.execute(
            "SELECT metadata_signature, confidence_score, last_verified_at, verification_source, updated_at FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%'"
        ).fetchall()
        signature_counts: Dict[str, Dict[str, int]] = {}
        high_confidence_count = 0
        validated_count = 0
        recent_verified_count = 0
        for row in signature_rows:
            signature = self.parse_metadata_signature(row['metadata_signature'])
            reliability = self.build_reliability_profile(dict(row))
            if reliability['confidence_score'] >= 0.75:
                high_confidence_count += 1
            if reliability['validation_status'] == 'validated':
                validated_count += 1
            if reliability['last_verified_at'] and (reliability['freshness_days'] is not None and reliability['freshness_days'] <= 30):
                recent_verified_count += 1
            for key in ["os_family", "language", "framework", "task_kind", "error_kind"]:
                value = signature.get(key)
                if not value:
                    continue
                values = value if isinstance(value, list) else [value]
                if key not in signature_counts:
                    signature_counts[key] = {}
                for item in values:
                    signature_counts[key][item] = signature_counts[key].get(item, 0) + 1

        def highlights(ntype: str, limit: int = 2, order_by: str = "usage_count DESC, updated_at DESC"):
            rows = self._conn.execute(
                f"SELECT node_id, title, usage_count FROM knowledge_nodes WHERE type = ? AND node_id NOT LIKE 'MEM_CONV%' ORDER BY {order_by} LIMIT ?",
                (ntype, limit)
            ).fetchall()
            return [dict(r) for r in rows]

        top_contexts = highlights("CONTEXT", limit=2)
        top_lessons = highlights("LESSON", limit=2)
        top_assets = highlights("ASSET", limit=2)
        active_episodes = highlights("EPISODE", limit=2, order_by="updated_at DESC")

        lines = ["[认知摘要 DIGEST]"]
        lines.append(f"CATALOG: nodes={total_nodes} | edges={total_edges}")
        lines.append(
            "KNOWN_INFO: "
            f"context={type_counts.get('CONTEXT', 0)} | "
            f"lesson={type_counts.get('LESSON', 0)} | "
            f"asset={type_counts.get('ASSET', 0)} | "
            f"episode={type_counts.get('EPISODE', 0)}"
        )
        lines.append(
            "GRAPH: "
            f"entity={type_counts.get('ENTITY', 0)} | "
            f"event={type_counts.get('EVENT', 0)} | "
            f"action={type_counts.get('ACTION', 0)}"
        )
        signature_parts = []
        for key in ["os_family", "language", "framework", "task_kind", "error_kind"]:
            values = signature_counts.get(key, {})
            if not values:
                continue
            best = sorted(values.items(), key=lambda item: (-item[1], item[0]))[:2]
            joined = ", ".join([f"{name}({count})" for name, count in best])
            signature_parts.append(f"{key}={joined}")
        if signature_parts:
            lines.append(f"SIGNATURE_HINTS: {' | '.join(signature_parts)}")
        lines.append(
            "TRUST: "
            f"high_conf={high_confidence_count} | "
            f"validated={validated_count} | "
            f"recent_verified={recent_verified_count}"
        )

        lines.append("TOP_CONTEXT:")
        if top_contexts:
            lines.extend([f"- [{r['node_id']}] {r['title']}" for r in top_contexts])
        else:
            lines.append("- NONE")

        lines.append("TOP_LESSONS:")
        if top_lessons:
            lines.extend([f"- [{r['node_id']}] {r['title']}" for r in top_lessons])
        else:
            lines.append("- NONE")

        lines.append("TOP_ASSETS:")
        if top_assets:
            lines.extend([f"- [{r['node_id']}] {r['title']}" for r in top_assets])
        else:
            lines.append("- NONE")

        lines.append("ACTIVE_EPISODES:")
        if active_episodes:
            lines.extend([f"- [{r['node_id']}] {r['title']}" for r in active_episodes])
        else:
            lines.append("- NONE")

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
            f"SELECT node_id, type, title, human_translation, tags, prerequisites, resolves, metadata_signature, usage_count, confidence_score, last_verified_at, verification_source, updated_at FROM knowledge_nodes WHERE node_id IN ({placeholders})",
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
                    metadata_signature: Optional[Dict[str, Any]] = None,
                    confidence_score: Optional[float] = None,
                    last_verified_at: Optional[str] = None,
                    verification_source: Optional[str] = None):
        """创建一个新的双层节点（索引 + 内容），支持注入因果属性和自动向量化"""
        # 如果是知识类节点，自动计算其向量
        embedding_json = None
        normalized_signature = self.normalize_metadata_signature(metadata_signature)
        signature_json = json.dumps(normalized_signature, ensure_ascii=False) if normalized_signature else None
        signature_text = self.render_metadata_signature(normalized_signature)
        normalized_confidence = self._clamp_confidence_score(
            confidence_score,
            default=self._default_confidence_score(normalized_signature, source)
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

        self._conn.execute(
            "INSERT OR REPLACE INTO knowledge_nodes (node_id, type, title, human_translation, tags, prerequisites, resolves, metadata_signature, embedding, confidence_score, last_verified_at, verification_source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (node_id, ntype, title, human_translation, tags, prerequisites, resolves, signature_json, embedding_json, normalized_confidence, normalized_last_verified, normalized_verification_source)
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO node_contents (node_id, full_content, source) VALUES (?,?,?)",
            (node_id, full_content, source)
        )
        self._conn.commit()
        logger.info(f"NodeVault: Created node [{node_id}] ({ntype}) — {title}")

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
        
    def build_g_prompt(self, recent_memory: str = "", available_tools_info: str = "", knowledge_digest: str = "", inferred_signature: str = "") -> str:
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

        return f"""你是 Genesis 的认知装配师 / 大脑 (G-Process)。
你的核心使命是通过**主动查阅**知识库，理解用户的真实意图，然后为执行器 (Op-Process) 准备一份包含充足上下文的任务派发书 (Task Payload)。
当执行器 (Op-Process) 完成任务后，系统会将执行结果返回给你，你需要基于结果和上下文，给用户做出最终的回复。

[用户配置]
- 语言：始终使用简体中文回复
- 身份：用户是 Genesis 的创造者，偏好直接简洁

{digest_block}

{signature_block}

{memory_block}

{tools_block}

[工作流指令 - 必读]
你和 Op (执行器) 是隔离的。Op 没有任何历史上下文，是个纯粹的打工人。
整个工作流是：你搜索思考 -> 你派发任务给 Op -> Op 在空白环境执行 -> Op 将结果返回给你 -> 你总结给用户。

**阶段一：查阅与思考 (G 的工作)**
1. 先阅读系统提供的 DIGEST，快速判断当前库里大概有什么、哪些节点最近活跃、哪些节点最常被使用。
2. 如果 DIGEST 已经足够支持判断，你可以直接回答用户，或定向派发 Op，不必为了形式而搜索。
3. 如果任务涉及复杂环境、特定报错或你仍缺乏上下文，再**定向调用**搜索工具，获取过往经验（LESSON）或环境信息（CONTEXT）。
4. **绝对限制：你只是一个只能思考和搜索数据库的“缸中之脑”。你没有任何修改现实世界的能力（没有文件读写、没有Shell、没有网络）。**
5. **Op 就是你的终极工具**。当你需要与现实世界交互时（比如：想看某个文件的内容、想运行一个测试、想创建一段代码），你**必须**把 Op 当作你的“探针”或“机械臂”来使用。
6. **侦察兵模式 (Reconnaissance Dispatch)**：如果你发现需要读取特定的本地文件（如阅读用户的代码、配置文件）才能继续思考，你**必须**派发一个侦察任务给 Op，让 Op 去读取文件，然后在 `[Op-Process 执行完毕]` 后把文件内容带回给你。不要自己瞎猜，也不要尝试给出虚假的执行结果。
7. 阅读搜索结果时，优先关注 `RECOMMENDED_ACTIVE_NODES`，它们通常最适合直接挂载给 Op。

**阶段二：派发任务 (呼叫子程序 Op)**
当你收集完信息准备让 Op 开始干活时，请**直接输出以下格式的任务派发书**。
只要你输出这个格式，系统就会立刻挂起你的运行，并将里面的内容交给 Op 去执行。
系统可能会对 `ACTIVE_NODES` 做一次轻量审查；如果你收到 `[Dispatch Review]`，优先修正派发书。如果你确认当前派发是有意为之，可以重新输出 `dispatch`，并让 `INSTRUCTIONS:` 第一行以 `[REVIEW_OVERRIDE]` 开头说明理由。

```dispatch
OP_INTENT: <对 Op 目标的简短明确指令>
ACTIVE_NODES: <你需要挂载给 Op 参考的节点ID列表，用逗号分隔，如 CTX_XXX, LESSON_XXX, ASSET_XXX。如果没有则写 NONE>
INSTRUCTIONS:
<给 Op 的具体执行建议或上下文信息。写清楚你想让 Op 怎么做。
注意：如果是“侦察任务”，请在这里明确告诉 Op：“读取 XXX 文件，并将文件内容通过总结直接返回给我”。>
```

**阶段三：综合与最终回复 (总结)**
当 Op 执行完毕后，你会收到一条包含 `[Op-Process 执行完毕]` 的系统消息。
此时，你需要结合用户的最初诉求、你的历史上下文以及 Op 的执行结果，决定下一步：
1. 如果任务已经足够完成，直接向用户输出最终的自然语言回复。
2. 如果还需要进一步执行，请重新输出新的 `dispatch` 任务书，再次调用 Op 子程序。
3. 最终回复时，不要机械复读 Op 的原文，而要做真正的综合、解释与取舍。
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

        return f"""你是 Genesis 的执行器 (Op-Process)。
你的核心使命是**只管干活**。你不需要知道复杂的历史背景，你只需要根据大脑 (G) 分配给你的目标和参考资料，利用你手头的工具完成任务。

[用户配置]
- 语言：始终使用简体中文回复

[G 派发的任务]
**目标 (OP_INTENT):** {op_intent}

**执行建议 (INSTRUCTIONS):**
{instructions}
{injection_text}

[工作流指令 - 必读]
1. 立即开始使用你的工具（如 Shell、File、Web 等）执行上述目标。
2. 遇到问题时，根据报错信息自行调整重试。
3. **你的双重身份**：你有时候是被叫来“修改代码/执行命令”的，有时候是被叫来“当侦察兵去读取特定文件内容”的。仔细阅读 G 的指令。
4. 你不是直接面向用户回复的人。你是 G 调用的子程序，最终只需要向 G 回传结构化报告。
5. 如果 G 让你去“读取文件”或“调查某个环境”，你**必须**在 `SUMMARY` 或 `FINDINGS` 里把你读到的关键内容、代码片段或调查结果直接写出来，否则 G 依然什么都看不到！
6. 当你认为任务已经彻底完成、阶段性完成、或穷尽方法依然失败时，必须输出如下格式的执行报告，不要输出面向用户的寒暄或总结：

```op_result
STATUS: SUCCESS | PARTIAL | FAILED
SUMMARY:
<一句话或一小段，说明这次执行达成了什么、没达成什么>

FINDINGS:
<如果这是一次侦察任务（如读取文件、查看日志），在这里输出你找到的具体内容片段、配置值或日志全文。如果是纯执行任务，写 NONE>

CHANGES_MADE:
- <本轮实际做出的修改、执行过的关键动作；如果没有写 NONE>

ARTIFACTS:
- <生成或修改的文件、脚本、配置、产物路径；如果没有写 NONE>

OPEN_QUESTIONS:
- <仍未解决的问题、风险、需要 G 决策的点；如果没有写 NONE>
```

7. 如果某一项为空，明确写 `NONE`。
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
            source="conversation"
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
                conn.execute(f"DELETE FROM knowledge_nodes WHERE node_id LIKE 'MEM_CONV_%' AND node_id NOT IN ({placeholders})", tuple(keep_ids))
                conn.execute(f"DELETE FROM node_contents WHERE node_id LIKE 'MEM_CONV_%' AND node_id NOT IN ({placeholders})", tuple(keep_ids))
                conn.commit()
                logger.info(f"NodeManagement: Memory sliding window purged {len(to_delete)} old conversations.")
        except Exception as e:
            logger.error(f"Failed to cleanup old memories: {e}")

