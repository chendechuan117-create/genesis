"""
Genesis V4 - 签名引擎 (Signature Engine)

从 NodeVault 中提取的 17 个签名相关方法，统一管理元数据签名的推断、标准化、合并和渲染。
NodeVault 通过组合模式委托签名操作到此引擎。
"""

import json
import functools
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# ── 从 manager.py 共享的常量（通过 manager.py 的顶层定义导入）──
from genesis.v4.signature_constants import (
    METADATA_SIGNATURE_FIELDS,
    METADATA_SCHEMA_VERSION_FIELD,
    _CORE_FIELDS_SET,
    _PROTECTED_METADATA_FIELDS,
    _DIM_OPERATIONAL_BLACKLIST,
    _DIM_MIN_FREQ,
    _MAX_CUSTOM_DIMS_PER_NODE,
    _VALIDATION_STATUS_ALIASES,
    _KNOWLEDGE_STATE_ALIASES,
    _INVALIDATION_REASON_ALIASES,
)
from genesis.v4.pipeline_config import PIPELINE_CONFIG


class SignatureEngine:
    """元数据签名引擎——推断、标准化、合并、渲染。

    设计约束：
    - conn: SQLite 连接（由 NodeVault 所有，共享给引擎）
    - vault: NodeVault 的反向引用（仅用于环境方法和 CRUD 回调）
    """

    _DIM_FRESHNESS_DAYS = PIPELINE_CONFIG.dim_freshness_days
    _LEARNED_MARKER_MAX_PER_KEY = PIPELINE_CONFIG.learned_marker_max_per_key

    def __init__(self, conn, vault=None):
        self._conn = conn
        self._vault = vault  # back-reference for environment/CRUD methods
        self._dim_registry: Dict[str, Dict[str, int]] = {}
        self._dim_value_index: Dict[str, str] = {}
        self._learned_markers: Dict[str, set] = {}

    def initialize(self):
        """启动时调用：构建维度注册表 + 加载学习标记"""
        self._build_dimension_registry()
        self._load_learned_markers()

    # ── 维度注册表 ──────────────────────────────────

    def _build_dimension_registry(self):
        """扫描全库签名，构建自定义维度注册表（反向索引 value→key）。"""
        rows = self._conn.execute(
            "SELECT metadata_signature, created_at FROM knowledge_nodes "
            "WHERE node_id NOT LIKE 'MEM_CONV%' AND metadata_signature IS NOT NULL "
            "AND metadata_signature != '{}'"
        ).fetchall()

        freshness_cutoff = datetime.utcnow() - timedelta(days=self._DIM_FRESHNESS_DAYS)

        dim_freq: Dict[str, Dict[str, int]] = {}
        dim_fresh: Dict[str, set] = {}
        for row in rows:
            try:
                sig = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            except Exception:
                continue
            if not isinstance(sig, dict):
                continue
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

        self._dim_registry = {}
        self._dim_value_index = {}
        fresh_promoted = 0
        for key, values in dim_freq.items():
            fresh_values = dim_fresh.get(key, set())
            qualified = {
                v: c for v, c in values.items()
                if c >= _DIM_MIN_FREQ or v in fresh_values
            }
            if qualified:
                self._dim_registry[key] = qualified
                for v in qualified:
                    if v not in self._dim_value_index:
                        self._dim_value_index[v] = key
                    if v in fresh_values and values[v] < _DIM_MIN_FREQ:
                        fresh_promoted += 1

        if self._dim_registry:
            fresh_note = f", fresh_promoted={fresh_promoted}" if fresh_promoted else ""
            logger.info(f"DimRegistry: {len(self._dim_registry)} custom dims, "
                        f"{len(self._dim_value_index)} indexed values "
                        f"(from {len(rows)} signatures{fresh_note})")

    # ── 学习标记 ──────────────────────────────────

    def _load_learned_markers(self):
        """从 SQLite 加载 C-Phase 历史学习到的签名 marker。"""
        self._learned_markers = {}
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
        """从 C-Phase 偏差检测学习新的签名 marker 并持久化。"""
        import re as _re
        val = str(marker_value).strip().lower()
        key = str(dim_key).strip().lower()
        if not val or not key or len(val) < 2 or len(val) > 50:
            return False
        if len(key) > 30 or not _re.fullmatch(r'[a-z][a-z0-9_]*', key):
            return False
        if key in _CORE_FIELDS_SET or key in _DIM_OPERATIONAL_BLACKLIST:
            return False
        existing = self._learned_markers.get(key, set())
        if val in existing:
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

    # ── 标准化 / 解析 / 渲染 / 合并 ──────────────────────────────────

    def _normalize_metadata_signature_cached(self, dict_str: str) -> Dict[str, Any]:
        """Internal cached worker for normalize_metadata_signature."""
        try:
            signature = json.loads(dict_str)
        except Exception:
            return {}

        _MAX_VALUES_PER_FIELD = 3
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

    def normalize(self, signature: Any) -> Dict[str, Any]:
        """标准化签名（外部接口名为 normalize，NodeVault 门面映射到 normalize_metadata_signature）"""
        if not signature:
            return {}
        if isinstance(signature, str):
            try:
                signature = json.loads(signature)
            except Exception:
                return {}
        if not isinstance(signature, dict):
            return {}

        dict_str = json.dumps(signature, sort_keys=True)
        result = dict(self._normalize_metadata_signature_cached(dict_str))

        custom_keys = [k for k in result if k not in _CORE_FIELDS_SET and k not in _PROTECTED_METADATA_FIELDS]
        if len(custom_keys) > _MAX_CUSTOM_DIMS_PER_NODE:
            custom_keys.sort(key=lambda k: max(self._dim_registry.get(k, {}).values(), default=0), reverse=True)
            for drop_key in custom_keys[_MAX_CUSTOM_DIMS_PER_NODE:]:
                del result[drop_key]
        if result.get("validation_status"):
            resolved_validation_status = self.resolve_validation_status(result)
            if resolved_validation_status:
                result["validation_status"] = resolved_validation_status
        if result.get("knowledge_state"):
            result["knowledge_state"] = self.resolve_knowledge_state(result)
        # 环境绑定需要 vault
        if self._vault:
            result = self._vault._bind_environment_aliases(result)
            result = self._vault._apply_metadata_contract(result)
        return result

    def parse(self, raw_signature: Any) -> Dict[str, Any]:
        return self.normalize(raw_signature)

    def render(self, signature: Any) -> str:
        """渲染签名为人类可读字符串"""
        normalized = self.normalize(signature)
        if not normalized:
            return ""
        display_signature = dict(normalized)
        display_signature.pop(METADATA_SCHEMA_VERSION_FIELD, None)
        if display_signature.get("applies_to_environment_scope") == display_signature.get("environment_scope"):
            display_signature.pop("applies_to_environment_scope", None)
        if display_signature.get("applies_to_environment_epoch") == display_signature.get("environment_epoch"):
            display_signature.pop("applies_to_environment_epoch", None)
        if display_signature.get("observed_environment_epoch") == display_signature.get("environment_epoch"):
            display_signature.pop("observed_environment_epoch", None)
        if display_signature.get("observed_environment_scope") == display_signature.get("environment_scope") and not display_signature.get("observed_environment_epoch"):
            display_signature.pop("observed_environment_scope", None)
        parts = []
        rendered_keys = set()
        for key in METADATA_SIGNATURE_FIELDS:
            value = display_signature.get(key)
            if not value:
                continue
            rendered_keys.add(key)
            if isinstance(value, list):
                parts.append(f"{key}={','.join(str(v) for v in value)}")
            else:
                parts.append(f"{key}={value}")
        for key in sorted(display_signature.keys()):
            if key in rendered_keys:
                continue
            value = display_signature[key]
            if isinstance(value, list):
                parts.append(f"{key}={','.join(str(v) for v in value)}")
            else:
                parts.append(f"{key}={value}")
        return " | ".join(parts)

    def merge(self, *signatures: Any) -> Dict[str, Any]:
        """合并多个签名"""
        merged: Dict[str, Any] = {}
        for raw_signature in signatures:
            signature = self.normalize(raw_signature)
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

    # ── 字段解析辅助 ──────────────────────────────────

    def signature_values(self, signature: Dict[str, Any], key: str) -> List[str]:
        value = (signature or {}).get(key)
        if not value:
            return []
        values = value if isinstance(value, list) else [value]
        result: List[str] = []
        for raw in values:
            if isinstance(raw, str) and "," in raw:
                parts = [part.strip() for part in raw.split(",") if part.strip()]
                result.extend(parts)
                continue
            item = str(raw).strip()
            if item:
                result.append(item)
        return result

    def resolve_validation_status(self, signature: Dict[str, Any]) -> str:
        normalized = []
        for raw in self.signature_values(signature, "validation_status"):
            mapped = _VALIDATION_STATUS_ALIASES.get(raw.lower(), raw.lower())
            if mapped not in normalized:
                normalized.append(mapped)
        for preferred in ("unverified", "validated", "partial", "outdated", "low_quality"):
            if preferred in normalized:
                return preferred
        return normalized[0] if normalized else ""

    def resolve_knowledge_state(self, signature: Dict[str, Any], ntype: str = "") -> str:
        normalized = []
        for raw in self.signature_values(signature, "knowledge_state"):
            mapped = _KNOWLEDGE_STATE_ALIASES.get(raw.lower(), raw.lower())
            if mapped not in normalized:
                normalized.append(mapped)
        for preferred in ("unverified", "historical", "current"):
            if preferred in normalized:
                return preferred
        validation_status = self.resolve_validation_status(signature)
        if validation_status == "unverified":
            return "unverified"
        if (ntype or "").upper() == "EPISODE":
            return "historical"
        return "current"

    def resolve_invalidation_reason(self, signature: Dict[str, Any]) -> str:
        normalized = []
        for raw in self.signature_values(signature, "invalidation_reason"):
            mapped = _INVALIDATION_REASON_ALIASES.get(raw.lower(), raw.lower())
            if mapped not in normalized:
                normalized.append(mapped)
        for preferred in ("superseded_env", "audit_outdated", "manual_outdated"):
            if preferred in normalized:
                return preferred
        return normalized[0] if normalized else ""

    def infer_invalidation_reason(self, signature: Dict[str, Any], verification_source: str = "", active_environment_epoch: str = "") -> str:
        explicit_reason = self.resolve_invalidation_reason(signature)
        if explicit_reason:
            return explicit_reason
        superseded_by_epoch = str((signature or {}).get("superseded_by_epoch") or "").strip()
        if superseded_by_epoch:
            return "superseded_env"
        validation_status = self.resolve_validation_status(signature)
        knowledge_state = self.resolve_knowledge_state(signature)
        # 环境检查需要 vault
        if self._vault:
            applicable_scope = self._vault._resolve_applicable_environment_scope(signature)
            applicable_epoch = self._vault._resolve_applicable_environment_epoch(signature)
            if applicable_scope == "doctor_workspace":
                active_epoch = str(active_environment_epoch or "").strip()
                if not active_epoch:
                    active_environment = self._vault.get_active_environment_epoch(applicable_scope)
                    active_epoch = active_environment["epoch_id"] if active_environment else ""
                if active_epoch and applicable_epoch and applicable_epoch != active_epoch:
                    return "superseded_env"
                if active_epoch and not applicable_epoch and validation_status == "outdated" and knowledge_state == "historical":
                    return "superseded_env"
        source_key = str(verification_source or "").strip().lower()
        if validation_status == "outdated" and source_key == "auditor_daemon":
            return "audit_outdated"
        return ""

    # ── 推断 ──────────────────────────────────

    def infer(self, text: str) -> Dict[str, Any]:
        """推断签名 = 硬编码标记词（缓存）+ 学习标记词 + 维度注册表匹配（动态）。"""
        core = self._infer_core(text)
        source = (text or "").lower()
        if not source.strip():
            return core
        extended = dict(core)
        if self._learned_markers:
            for key, markers in self._learned_markers.items():
                if key not in extended:
                    for marker in markers:
                        if marker in source:
                            extended[key] = marker
                            break
        if self._dim_value_index:
            for value, key in self._dim_value_index.items():
                if key not in extended and value in source:
                    extended[key] = value
        return extended

    @functools.lru_cache(maxsize=128)
    def _infer_core(self, text: str) -> Dict[str, Any]:
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
            "self_improvement": ["自主改进", "doctor沙箱", "doctor.sh", "自我改进"],
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

        cognitive_markers = {
            "aggressive": ["激进", "直接", "别把人当", "别啰嗦", "大胆", "aggressive"],
            "conservative": ["保守", "谨慎", "先确认", "稳一点", "别急", "conservative"],
            "deep_analysis": ["深入", "深度分析", "不够深", "这谁不知道", "深挖", "deep_analysis"],
        }
        for value, markers in cognitive_markers.items():
            if any(marker in source for marker in markers):
                add("cognitive_approach", value)

        domain_markers = {
            "consumer_service": ["外卖", "美团", "饿了么", "淘宝", "拼多多", "京东", "消费", "购物", "省钱", "优惠", "coupon"],
            "system_config": ["系统配置", "system config", "systemd", "网络配置", "防火墙"],
            "code_review": ["代码审查", "code review", "重构", "架构"],
            "research": ["调研", "research", "分析", "评估", "对比"],
        }
        for value, markers in domain_markers.items():
            if any(marker in source for marker in markers):
                add("domain", value)

        return inferred

    def infer_from_artifacts(self, artifacts: List[str]) -> Dict[str, Any]:
        """从文件路径列表推断签名"""
        if not artifacts:
            return {}

        signatures: List[Dict[str, Any]] = []
        for artifact in artifacts:
            text = str(artifact or "").strip()
            if not text:
                continue
            lower = text.lower()

            signature = self.infer(text)

            if lower.endswith(".py") or lower.endswith("requirements.txt") or lower.endswith("pyproject.toml") or lower.endswith("poetry.lock") or lower.endswith("uv.lock"):
                signature = self.merge(signature, {"language": "python", "runtime": "python"})
            if lower.endswith(".js") or lower.endswith("package.json") or lower.endswith("yarn.lock") or lower.endswith("pnpm-lock.yaml") or lower.endswith("bun.lockb"):
                signature = self.merge(signature, {"language": "javascript", "runtime": "node"})
            if lower.endswith(".ts") or lower.endswith(".tsx") or lower.endswith("tsconfig.json"):
                signature = self.merge(signature, {"language": "typescript", "runtime": "node"})
            if lower.endswith("go.mod") or lower.endswith(".go"):
                signature = self.merge(signature, {"language": "go"})
            if lower.endswith("cargo.toml") or lower.endswith(".rs"):
                signature = self.merge(signature, {"language": "rust"})
            if lower.endswith("pom.xml") or lower.endswith("build.gradle") or lower.endswith("build.gradle.kts"):
                signature = self.merge(signature, {"language": "java"})
            if lower.endswith("dockerfile") or "dockerfile" in lower or lower.endswith("docker-compose.yml") or lower.endswith("docker-compose.yaml") or lower.endswith("compose.yml") or lower.endswith("compose.yaml"):
                signature = self.merge(signature, {"runtime": "docker"})
            if lower.endswith(".service"):
                signature = self.merge(signature, {"runtime": "systemd", "target_kind": "service"})
            if lower.endswith(".sql"):
                signature = self.merge(signature, {"target_kind": "database"})
            if lower.endswith(".yaml") or lower.endswith(".yml"):
                if any(marker in lower for marker in ["k8s", "kubernetes", "helm", "deployment", "ingress"]):
                    signature = self.merge(signature, {"runtime": "kubernetes"})
            if any(marker in lower for marker in ["/frontend/", "frontend/", "/src/components/", "components/"]):
                signature = self.merge(signature, {"target_kind": "frontend"})
            if any(marker in lower for marker in ["/backend/", "backend/", "/api/", "api/"]):
                signature = self.merge(signature, {"target_kind": "backend"})

            if signature:
                signatures.append(signature)

        return self.merge(*signatures)

    def expand_from_node_ids(self, node_ids: List[str]) -> Dict[str, Any]:
        """从节点 ID 列表展开签名"""
        if not node_ids or not self._vault:
            return {}

        briefs = self._vault.get_node_briefs(node_ids)
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
            prereq_briefs = self._vault.get_node_briefs(prereq_ids)
            for brief in prereq_briefs.values():
                if brief.get("metadata_signature"):
                    signatures.append(brief.get("metadata_signature"))

        return self.merge(*signatures)
