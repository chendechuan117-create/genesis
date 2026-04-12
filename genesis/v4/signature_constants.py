"""
Genesis V4 - 签名相关常量

从 manager.py 中提取，供 manager.py 和 signature_engine.py 共同引用，
打破循环导入。
"""

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
    "knowledge_state",
    "invalidation_reason",
    "valid_from",
    "valid_until",
]

METADATA_SCHEMA_VERSION = "2"
METADATA_SCHEMA_VERSION_FIELD = "metadata_schema_version"

# ── 状态别名映射 ─────────────────────────────────────
_VALIDATION_STATUS_ALIASES = {
    "validated": "validated",
    "verified": "validated",
    "已验证": "validated",
    "验证通过": "validated",
    "通过": "validated",
    "tested": "validated",
    "有效": "validated",
    "unverified": "unverified",
    "未验证": "unverified",
    "partial": "partial",
    "partial_information": "partial",
    "content-analyzed": "partial",
    "outdated": "outdated",
    "stale": "outdated",
    "low_quality": "low_quality",
}
_KNOWLEDGE_STATE_ALIASES = {
    "current": "current",
    "active": "current",
    "latest": "current",
    "live": "current",
    "historical": "historical",
    "history": "historical",
    "outdated": "historical",
    "stale": "historical",
    "superseded": "historical",
    "archived": "historical",
    "unverified": "unverified",
    "tentative": "unverified",
    "experimental": "unverified",
    "hypothesis": "unverified",
    "未验证": "unverified",
}
_INVALIDATION_REASON_ALIASES = {
    "superseded_env": "superseded_env",
    "superseded_epoch": "superseded_env",
    "environment_superseded": "superseded_env",
    "audit_outdated": "audit_outdated",
    "audited_outdated": "audit_outdated",
    "verifier_outdated": "audit_outdated",
    "manual_outdated": "manual_outdated",
    "manual": "manual_outdated",
}

# ── 维度注册表治理 ─────────────────────────────────────
_DIM_OPERATIONAL_BLACKLIST = frozenset({
    "timestamp", "port", "daily_nodes_created", "task_completion",
    "followup_needed", "version", "workflow_count", "backup_exists",
    "environment_epoch", "superseded_by_epoch",
    "observed_environment_scope", "observed_environment_epoch",
    "applies_to_environment_scope", "applies_to_environment_epoch",
    "invalidation_reason",
    "valid_from", "valid_until",
    METADATA_SCHEMA_VERSION_FIELD,
})
_DIM_MIN_FREQ = 3
_MAX_CUSTOM_DIMS_PER_NODE = 5
_CORE_FIELDS_SET = frozenset(METADATA_SIGNATURE_FIELDS)
_PROTECTED_METADATA_FIELDS = frozenset({
    "environment_epoch", "superseded_by_epoch",
    "observed_environment_scope", "observed_environment_epoch",
    "applies_to_environment_scope", "applies_to_environment_epoch",
    "invalidation_reason",
    METADATA_SCHEMA_VERSION_FIELD,
})
_ENVIRONMENT_SCOPE_ALIASES = {
    "doctor": "doctor_workspace",
    "doctor sandbox": "doctor_workspace",
    "doctor_sandbox": "doctor_workspace",
    "doctor-workspace": "doctor_workspace",
    "doctor workspace": "doctor_workspace",
    "workspace": "doctor_workspace",
}
