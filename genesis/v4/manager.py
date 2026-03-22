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

# ── 维度注册表治理 ─────────────────────────────────────
_DIM_OPERATIONAL_BLACKLIST = frozenset({
    "timestamp", "port", "daily_nodes_created", "task_completion",
    "followup_needed", "version", "workflow_count", "backup_exists",
})
_DIM_MIN_FREQ = 3           # 自定义维度纳入注册表的最低出现频次
_MAX_CUSTOM_DIMS_PER_NODE = 5  # 单节点自定义维度上限
_CORE_FIELDS_SET = frozenset(METADATA_SIGNATURE_FIELDS)


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
        self._build_dimension_registry()
        self._load_learned_markers()

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
            self._build_dimension_registry()  # 新节点可能带来新的自定义维度
        return synced

    _DIM_FRESHNESS_DAYS = 7  # 新鲜度豁免窗口：7 天内的维度 freq≥1 即可纳入

    def _build_dimension_registry(self):
        """扫描全库签名，构建自定义维度注册表（反向索引 value→key）。
        
        纳入规则（二选一即可）：
        - 成熟维度：出现频率 >= _DIM_MIN_FREQ（默认 3）
        - 新鲜维度：近 _DIM_FRESHNESS_DAYS 天内写入且 freq >= 1（冷启动豁免）
        搜索时 infer_metadata_signature 会用此注册表匹配自定义维度。
        """
        rows = self._conn.execute(
            "SELECT metadata_signature, created_at FROM knowledge_nodes "
            "WHERE node_id NOT LIKE 'MEM_CONV%' AND metadata_signature IS NOT NULL "
            "AND metadata_signature != '{}'"
        ).fetchall()

        freshness_cutoff = datetime.utcnow() - timedelta(days=self._DIM_FRESHNESS_DAYS)

        dim_freq: Dict[str, Dict[str, int]] = {}  # {dim_key: {value: count}}
        dim_fresh: Dict[str, set] = {}             # {dim_key: set of fresh values}
        for row in rows:
            try:
                sig = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            except Exception:
                continue
            if not isinstance(sig, dict):
                continue
            # 判断节点是否在新鲜度窗口内
            is_fresh = False
            try:
                created = row[1] or ""
                node_time = datetime.fromisoformat(str(created).replace("Z", "+00:00")).replace(tzinfo=None)
                is_fresh = node_time >= freshness_cutoff
            except Exception:
                pass
            for key, value in sig.items():
                if key in _CORE_FIELDS_SET or key in _DIM_OPERATIONAL_BLACKLIST:
                    continue
                if key not in dim_freq:
                    dim_freq[key] = {}
                values = value if isinstance(value, list) else [value]
                for v in values:
                    v_str = str(v).strip().lower()
                    if v_str and len(v_str) >= 2:
                        dim_freq[key][v_str] = dim_freq[key].get(v_str, 0) + 1
                        if is_fresh:
                            dim_fresh.setdefault(key, set()).add(v_str)

        self._dim_registry: Dict[str, Dict[str, int]] = {}  # {key: {value: count}}
        self._dim_value_index: Dict[str, str] = {}           # {lowered_value: key}
        fresh_promoted = 0
        for key, values in dim_freq.items():
            fresh_values = dim_fresh.get(key, set())
            qualified = {
                v: c for v, c in values.items()
                if c >= _DIM_MIN_FREQ or v in fresh_values  # 新鲜度豁免
            }
            if qualified:
                self._dim_registry[key] = qualified
                for v in qualified:
                    if v not in self._dim_value_index:  # 先到先得，避免歧义
                        self._dim_value_index[v] = key
                    if v in fresh_values and values[v] < _DIM_MIN_FREQ:
                        fresh_promoted += 1

        if self._dim_registry:
            fresh_note = f", fresh_promoted={fresh_promoted}" if fresh_promoted else ""
            logger.info(f"DimRegistry: {len(self._dim_registry)} custom dims, "
                        f"{len(self._dim_value_index)} indexed values "
                        f"(from {len(rows)} signatures{fresh_note})")

    _LEARNED_MARKER_MAX_PER_KEY = 10  # 每个维度 key 最多学习 10 个 marker，防止污染

    def _load_learned_markers(self):
        """从 SQLite 加载 C-Phase 历史学习到的签名 marker，补充硬编码关键词表。"""
        self._learned_markers: Dict[str, set] = {}  # {dim_key: set(marker_values)}
        try:
            rows = self._conn.execute(
                "SELECT dim_key, marker_value FROM learned_signature_markers"
            ).fetchall()
            for row in rows:
                key, val = row[0], row[1]
                self._learned_markers.setdefault(key, set()).add(val)
            if self._learned_markers:
                total = sum(len(v) for v in self._learned_markers.values())
                logger.info(f"LearnedMarkers: loaded {total} markers across {len(self._learned_markers)} dims")
        except Exception as e:
            logger.debug(f"LearnedMarkers: load failed (table may not exist yet): {e}")
            self._learned_markers = {}

    def learn_signature_marker(self, dim_key: str, marker_value: str, source: str = "c_phase"):
        """从 C-Phase 偏差检测学习新的签名 marker 并持久化。
        
        安全阀：
        - 每个 key 最多 _LEARNED_MARKER_MAX_PER_KEY 个 marker
        - marker 长度必须 >= 2 且 <= 50（防止过短误匹配或过长垃圾）
        - 不学习核心维度的 marker（硬编码表已覆盖）
        """
        import re as _re
        val = str(marker_value).strip().lower()
        key = str(dim_key).strip().lower()
        if not val or not key or len(val) < 2 or len(val) > 50:
            return False
        # dim_key 格式校验：只允许小写字母/数字/下划线，长度 2-30
        # 拦截 LLM 幻觉产生的非规范维度 key（如含空格、中文、特殊字符）
        if len(key) > 30 or not _re.fullmatch(r'[a-z][a-z0-9_]*', key):
            return False
        if key in _CORE_FIELDS_SET or key in _DIM_OPERATIONAL_BLACKLIST:
            return False
        existing = self._learned_markers.get(key, set())
        if val in existing:
            # 已知 marker，增加计数
            try:
                self._conn.execute(
                    "UPDATE learned_signature_markers SET hit_count = hit_count + 1 WHERE dim_key = ? AND marker_value = ?",
                    (key, val)
                )
                self._conn.commit()
            except Exception:
                pass
            return False
        if len(existing) >= self._LEARNED_MARKER_MAX_PER_KEY:
            return False
        # 新 marker：写入内存 + SQLite
        self._learned_markers.setdefault(key, set()).add(val)
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO learned_signature_markers (dim_key, marker_value, source_persona) VALUES (?, ?, ?)",
                (key, val, source)
            )
            self._conn.commit()
            logger.info(f"LearnedMarkers: +1 marker {key}={val} (from {source})")
        except Exception as e:
            logger.debug(f"LearnedMarkers: persist failed: {e}")
        return True

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
            
        _MAX_VALUES_PER_FIELD = 3  # 反堆砌：单字段最多 3 个值
        normalized: Dict[str, Any] = {}
        for key, value in signature.items():
            if not value:
                continue
            if isinstance(value, list):
                sorted_vals = sorted(set(str(v).strip() for v in value if v))[:_MAX_VALUES_PER_FIELD]
                if sorted_vals:
                    normalized[key] = sorted_vals if len(sorted_vals) > 1 else sorted_vals[0]
            elif isinstance(value, str):
                item_str = value.strip()
                if "," in item_str:
                    sorted_vals = sorted(set(p.strip() for p in item_str.split(",") if p.strip()))[:_MAX_VALUES_PER_FIELD]
                    if sorted_vals:
                        normalized[key] = sorted_vals if len(sorted_vals) > 1 else sorted_vals[0]
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
        result = dict(self._normalize_metadata_signature_cached(dict_str))

        # 治理：单节点自定义维度上限
        custom_keys = [k for k in result if k not in _CORE_FIELDS_SET]
        if len(custom_keys) > _MAX_CUSTOM_DIMS_PER_NODE:
            registry = getattr(self, '_dim_registry', {})
            # 优先保留注册表中频率高的维度
            custom_keys.sort(key=lambda k: max(registry.get(k, {}).values(), default=0), reverse=True)
            for drop_key in custom_keys[_MAX_CUSTOM_DIMS_PER_NODE:]:
                del result[drop_key]
        return result

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
                    sorted_vals = sorted(set(str(v) for v in existing_values))
                    merged[key] = sorted_vals if len(sorted_vals) > 1 else sorted_vals[0]
        return merged

    def infer_metadata_signature(self, text: str) -> Dict[str, Any]:
        """推断签名 = 硬编码标记词（缓存）+ 学习标记词 + 维度注册表匹配（动态）。"""
        core = self._infer_core_signature(text)
        source = (text or "").lower()
        if not source.strip():
            return core
        extended = dict(core)
        # 学习标记词：C-Phase 偏差检测自动学习到的新 marker
        learned = getattr(self, '_learned_markers', None)
        if learned:
            for key, markers in learned.items():
                if key not in extended:
                    for marker in markers:
                        if marker in source:
                            extended[key] = marker
                            break
        # 维度注册表：节点签名中的自定义维度反向索引
        registry_idx = getattr(self, '_dim_value_index', None)
        if registry_idx:
            for value, key in registry_idx.items():
                if key not in extended and value in source:
                    extended[key] = value
        return extended

    @functools.lru_cache(maxsize=128)
    def _infer_core_signature(self, text: str) -> Dict[str, Any]:
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

    def get_kb_entropy(self) -> Optional[Dict[str, Any]]:
        """知识库熵增诊断：低/高 confidence 节点占比（供 heartbeat）"""
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

    # ─── Persona 学习持久化 ───

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
                if not tk:  # 全局统计
                    global_stats[persona] = {"wins": wins, "losses": losses}
                else:  # 按 task_kind 统计
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
                    "INSERT OR REPLACE INTO persona_stats (persona, task_kind, wins, losses, updated_at) "
                    "VALUES (?, '', ?, ?, CURRENT_TIMESTAMP)",
                    (persona, s["wins"], s["losses"])
                )
            for key, s in task_stats.items():
                parts = key.split(":", 1)
                if len(parts) == 2:
                    self._conn.execute(
                        "INSERT OR REPLACE INTO persona_stats (persona, task_kind, wins, losses, updated_at) "
                        "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                        (parts[0], parts[1], s["wins"], s["losses"])
                    )
            self._conn.commit()
        except Exception as e:
            logger.error(f"PersonaStats: save failed: {e}")

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
        # 签名标准化
        if "metadata_signature" in updates:
            sig = updates["metadata_signature"]
            if isinstance(sig, dict):
                sig = self.normalize_metadata_signature(sig)
                updates["metadata_signature"] = json.dumps(sig, ensure_ascii=False)
            elif isinstance(sig, str):
                parsed = self.normalize_metadata_signature(sig)
                updates["metadata_signature"] = json.dumps(parsed, ensure_ascii=False)
        # 信任层校验
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
            # 重新生成向量嵌入（如果向量引擎就绪）
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
                "INSERT OR IGNORE INTO node_edges (source_id, target_id, relation, weight) VALUES (?, ?, ?, ?)",
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
        # 拆分 WHERE 条件和 ORDER BY
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
                 "fixed_contradiction": 0, "unchanged": 0}

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

            # 1. 规范化修复（sort/dedup/cap）
            normalized = self.normalize_metadata_signature(stored_sig)
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
                re_inferred = self._infer_core_signature(content[:2000])
                for key in ["language", "runtime", "os_family", "framework"]:
                    stored_val = new_sig.get(key)
                    inferred_val = re_inferred.get(key)
                    if not stored_val or not inferred_val:
                        continue
                    # 转为集合比较
                    stored_set = set(stored_val if isinstance(stored_val, list) else [stored_val])
                    inferred_set = set(inferred_val if isinstance(inferred_val, list) else [inferred_val])
                    # 完全不相交 = 矛盾
                    if stored_set and inferred_set and not (stored_set & inferred_set):
                        # 合并而非覆盖（可能内容和签名各有对的部分）
                        merged = sorted(stored_set | inferred_set)[:3]
                        new_sig[key] = merged if len(merged) > 1 else merged[0]
                        changed = True
                        stats["fixed_contradiction"] += 1
                        logger.info(f"SigAudit [{node_id}] {key}: {stored_val} ⊕ {inferred_val} → {new_sig[key]}")

            if changed:
                self._conn.execute(
                    "UPDATE knowledge_nodes SET metadata_signature = ?, updated_at = CURRENT_TIMESTAMP WHERE node_id = ?",
                    (json.dumps(new_sig, ensure_ascii=False), node_id)
                )
            else:
                stats["unchanged"] += 1

        if stats["audited"] > 0:
            self._conn.commit()
            fixed = stats["fixed_normalize"] + stats["fixed_blacklist"] + stats["fixed_contradiction"]
            if fixed > 0:
                logger.info(f"SigAudit: {stats['audited']} audited, {fixed} fixed "
                            f"(norm={stats['fixed_normalize']}, blacklist={stats['fixed_blacklist']}, "
                            f"contradict={stats['fixed_contradiction']})")
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
        # 计算归一化权重：最高分节点 weight=1.0，最低分节点 weight=floor
        max_weight = max(weights.values()) if weights else 0.0
        FLOOR = 0.4  # 最低节点也拿到 40% 的基础 boost/decay，避免完全不归因
        for node_id in node_ids:
            if node_id.startswith("MEM_CONV"):
                continue
            # 权重归一化：有 weights 且 max > 0 时按比例；否则 1.0（回退到旧行为）
            if weights and max_weight > 0:
                raw = weights.get(node_id, 0.0)
                w = max(FLOOR, raw / max_weight)  # 归一到 [FLOOR, 1.0]
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


# ─── Multi-G 人格激活映射 ─────────────────────────────────────
PERSONA_ACTIVATION_MAP = {
    "debug":     ["ISTJ", "INTP", "INTJ"],
    "refactor":  ["INTP", "ENFP", "ENTJ"],
    "deploy":    ["ISTJ", "ESTJ", "ISTP"],
    "configure": ["ISTJ", "ISFJ", "INTJ"],
    "build":     ["ENTJ", "ENFP", "INTP"],
    "test":      ["ISTJ", "INTP", "ISFJ"],
    "optimize":  ["INTP", "INTJ", "ISTP"],
    "design":    ["ENFP", "INFJ", "ENTJ"],
    "_default":  ["ISTJ", "INTP", "ENFP"],
}

# ─── 16 型人格透镜的认知框架 ─────────────────────────────
# 基于 MBTI 认知功能栈设计。不是限制搜索范围，而是塑造对同一信息的不同理解方式。
# 所有透镜看到相同的搜索结果，差异在于：怎么思考、关注什么、质疑什么、怎么下结论。
PERSONA_LENS_PROFILES = {
    "ISTJ": {
        "label": "物流师",
        "cognitive_frame": (
            "你的认知模式（Si-Te）：面对信息时，你首先与历史经验对照——「这件事以前发生过吗？结果如何？」"
            "你信任已验证的事实胜过理论推演。你会注意到搜索结果中与过去成功/失败经验相似的模式。"
            "你的结论倾向保守和可追溯：优先推荐已被验证过的方案，而非未经测试的新路径。"
            "你质疑的是：当前方案是否有前车之鉴？是否忽略了历史教训？"
        ),
    },
    "INTP": {
        "label": "逻辑学家",
        "cognitive_frame": (
            "你的认知模式（Ti-Ne）：面对信息时，你自动解构到底层机制——「为什么会这样？因果链是什么？」"
            "你不满足于表面的「怎么做」，而是追问「为什么有效」。搜索结果中，你会关注能解释根因的线索，"
            "忽略纯操作性的描述。你的结论倾向于揭示底层规律，可能抽象但逻辑严密。"
            "你质疑的是：当前理解是否真正触及了根因？还是只是在症状层面打转？"
        ),
    },
    "INTJ": {
        "label": "建筑师",
        "cognitive_frame": (
            "你的认知模式（Ni-Te）：面对信息时，你自动从全局视角审视——「这在系统架构中处于什么位置？改动的涟漪效应是什么？」"
            "你看到的不是单个问题，而是系统中的节点和它们的关联。搜索结果中，你会关注架构决策、设计模式、"
            "以及当前方案对未来扩展的影响。你的结论倾向战略性的，考虑长期后果。"
            "你质疑的是：当前方案是否只是局部最优？是否会在系统层面引入技术债？"
        ),
    },
    "ENFP": {
        "label": "竞选者",
        "cognitive_frame": (
            "你的认知模式（Ne-Fi）：面对信息时，你自动发散联想——「这让我想到什么？有没有完全不同的方式？」"
            "你擅长跨域类比，在看似无关的信息中发现隐藏的连接。搜索结果中，你最兴奋的是意外发现和非显而易见的关联。"
            "你的结论倾向于打开新可能性，而不是收敛到唯一解。你敢于提出看似大胆的假设。"
            "你质疑的是：我们是否被思维定式限制了？是否存在被忽视的替代路径？"
        ),
    },
    "ENTJ": {
        "label": "指挥官",
        "cognitive_frame": (
            "你的认知模式（Te-Ni）：面对信息时，你直奔执行路径——「最快到达目标的关键路径是什么？瓶颈在哪？」"
            "你看搜索结果时关注可操作性：哪些信息能直接转化为执行步骤，哪些是噪音。"
            "你的结论倾向于清晰、可衡量、有截止条件的行动方案。"
            "你质疑的是：当前方案的执行效率是否最优？是否有更短的路径？"
        ),
    },
    "ESTJ": {
        "label": "总经理",
        "cognitive_frame": (
            "你的认知模式（Te-Si）：面对信息时，你对照标准和流程——「正确的做法是什么？是否有遗漏的步骤？」"
            "你信任经过验证的标准操作流程，搜索结果中你关注规范、配置要求、检查清单。"
            "你的结论倾向于完整和合规，确保每个步骤都被覆盖，没有跳过。"
            "你质疑的是：当前方案是否遵循了最佳实践？是否有步骤被想当然地跳过了？"
        ),
    },
    "ISTP": {
        "label": "鉴赏家",
        "cognitive_frame": (
            "你的认知模式（Ti-Se）：面对信息时，你想的是「能不能马上验证？」——最小实验优先。"
            "你不耐烦长篇理论，偏好动手试。搜索结果中你关注具体的命令、代码片段、可立即执行的操作。"
            "你的结论倾向于最小可验证方案：用最少的改动确认假设的真伪。"
            "你质疑的是：我们是否在过度分析而不是直接测试？最简单的验证实验是什么？"
        ),
    },
    "ISFJ": {
        "label": "守卫者",
        "cognitive_frame": (
            "你的认知模式（Si-Fe）：面对信息时，你关注别人可能忽略的细节和边界条件——「如果这个值为空呢？如果并发呢？」"
            "你是团队中的安全网，搜索结果中你注意异常处理、回退方案、容错机制。"
            "你的结论倾向于防御性的：不只是解决问题，还要确保不引入新问题。"
            "你质疑的是：当前方案的边界条件是否被覆盖？失败时的回退策略是什么？"
        ),
    },
    "INFJ": {
        "label": "提倡者",
        "cognitive_frame": (
            "你的认知模式（Ni-Fe）：面对信息时，你透过表象看本质——「表面问题背后的真正问题是什么？」"
            "你擅长读出搜索结果中的隐含信息：用户没说但暗示的需求、系统设计中未言明的约束。"
            "你的结论倾向于揭示深层意图，连接表面不相关的线索。"
            "你质疑的是：我们是否在解决正确的问题？表面需求之下是否藏着更深层的诉求？"
        ),
    },
}


class FactoryManager:
    """负责组装系统提示词 (G / Op / C / Lens)"""
    
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

        # ⚠️ 前缀缓存优化：稳定指令放前面（跨请求不变），变量内容放后面
        return f"""你是 Genesis 大脑 (G-Process)——一个有自知之明的 agent，不是百科全书式的 AI 助手。
用简体中文回复。用户是 Genesis 创造者，偏好直接简洁。

[你是谁]
你是缸中之脑。你没有手脚、没有终端、没有浏览器。你唯一的信息来源是：
1. 知识库 (NodeVault) 中存储的、经过验证分级的节点
2. Op 执行任务后带回的实地报告
3. 透镜阶段的多视角侦察结果（如果有）
除此之外，你脑中的一切都是语言模型的参数记忆——它可能过时、可能错误、可能是幻觉。

[认知纪律]
- 区分「我从知识库/Op报告中看到的」和「我作为语言模型猜测的」。前者可以断言，后者必须标记为推测或直接派 Op 去验证。
- 不确定时，行动优先于猜测。派 Op 去读文件、跑命令、检查状态，比你凭空推理强 10 倍。
- 禁止纸上谈兵：如果你发现自己在写"建议执行…"、"可以尝试…"、"通常来说…"这类泛泛而谈——停下来，改为 dispatch Op 去做。
- 你的回复中，每一个事实断言都应该能追溯到具体节点 ID 或 Op 的 FINDINGS。做不到就说"我不确定，需要验证"。

[工作流]
Op 没有任何历史上下文，且迭代上限仅 12 轮。你是大脑，Op 只是手脚——你必须做分治规划。

检索：先读 DIGEST 建立全局判断。PROVEN 是久经考验的节点；UNTESTED 是新知识——优先挂载让它们证明自己。需要细节时用 search_knowledge_nodes 定向搜索。
派发：调用 dispatch_to_op(op_intent, active_nodes, instructions)。每次只给 Op 一个原子任务（5-10 步可完成）。
  - ✅ 好的派发："读取 /etc/nginx/nginx.conf 并报告当前 upstream 配置"
  - ✅ 好的派发："用 sed 将 proxy_pass 从 8080 改为 8081，然后 nginx -t 验证"
  - ❌ 坏的派发："调查系统所有配置，优化数据库，启动服务，创建监控"（太大，Op 会迷失）
综合：收到 Op 结果后，仔细阅读 FINDINGS 和 OPEN_QUESTIONS。决策下一步：
  - 任务完成 → 向用户输出最终回复（纯文本），引用具体证据
  - 需要更多工作 → 基于 Op 反馈再次 dispatch（下一个原子步骤）
  - Op 报告 PARTIAL/FAILED → 分析原因，调整策略后重新派发
  禁止说"将会执行"——要么你已经在做，要么你现在就 dispatch。

[回复风格]
- 说人话，不要列清单式的"1. 2. 3. 4."教科书回答
- 有观点、有判断、有取舍，像一个经验丰富的工程师而不是客服机器人
- 承认不知道的事。"我没找到相关信息"比编造一个看似合理的答案好 100 倍
- 收到 [Dispatch Review] 时优先修正；确认无误则 instructions 首行写 [REVIEW_OVERRIDE] 并说明理由

{digest_block}
{signature_block}
{memory_block}
{tools_block}
{daemon_block}
"""

    def build_lens_prompt(self, persona: str, task_context: str, blackboard_state: str = "", knowledge_digest: str = "", inferred_signature: str = "") -> str:
        """
        为透镜子程序 (Lens) 构建系统提示词。
        
        ⚠️ 前缀缓存优化：DeepSeek 按 token 前缀匹配做缓存。
        所有透镜共享的内容（digest, signature, task, format）放在 prompt 最前面，
        人格特定内容（identity, cognitive_frame, blackboard）放在最后面。
        这样 3~7 个透镜调用可以共享前缀缓存，大幅降低未命中缓存的 token 量。
        """
        profile = PERSONA_LENS_PROFILES.get(persona, {})
        label = profile.get("label", persona)
        cognitive_frame = profile.get("cognitive_frame", "你从通用视角分析问题，搜索知识库中所有可能相关的信息。")
        
        # ── 共享前缀（所有透镜相同，利于缓存命中）──
        digest_block = ""
        if knowledge_digest:
            digest_block = f"""[NodeVault 认知摘要]
{knowledge_digest}
"""
        
        signature_block = ""
        if inferred_signature:
            signature_block = f"""[任务推测签名]
{inferred_signature}
"""

        # ── 人格特定后缀（每个透镜不同，放最后）──
        blackboard_block = ""
        if blackboard_state:
            blackboard_block = f"""
[当前黑板状态 — 其他透镜已提交的内容]
{blackboard_state}
避免重复已有的框架。如果你认同某个已有框架，搜索更多证据来支撑它；如果你有不同视角，提交新框架。
"""
        
        return f"""你是 Genesis 透镜子程序。G 主脑已解读用户意图并给你布置了搜索任务。

{digest_block}{signature_block}[任务简报 — G 的意图解读]
{task_context}

[搜索指令]
1. 从上面的搜索方向中，选择最符合你认知视角的 1-2 个方向
2. 用 search_knowledge_nodes 搜索（你只能使用这一个工具）
3. 搜索关键词基于任务简报的搜索方向和知识库摘要中的实际主题

[输出格式]
搜索完成后，输出**严格 JSON**（不要包裹在代码块中）：

如果搜到了相关证据节点：
{{"type": "evidence", "framework": "你对问题的独特理解（一句话，体现你的认知视角）", "evidence_node_ids": ["节点ID1", "节点ID2"], "verification_action": "最快验证此框架真伪的最小动作（具体命令/文件/测试）"}}

如果没搜到证据但有推理假设：
{{"type": "hypothesis", "framework": "你的假设（一句话）", "reasoning_chain": "从你的认知模式出发的推理过程", "suggested_search_directions": ["建议搜索方向1", "建议搜索方向2"]}}

必须输出且仅输出一个 JSON。不要解释。

[你的认知人格: Lens-{persona} — {label}]
{cognitive_frame}
{blackboard_block}
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
                preview = raw_output[:2000] + ("..." if len(raw_output) > 2000 else "")
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

