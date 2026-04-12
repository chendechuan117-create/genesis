"""
Genesis V4 — Environment Epoch Mixin
环境纪元管理：作用域归一化、纪元激活/废止、节点软失效。
从 manager.py NodeVault 中提取，通过 mixin 继承合并回 NodeVault。
"""

import json
import logging
from typing import Any, Dict, Optional
from datetime import datetime

from genesis.v4.signature_constants import _ENVIRONMENT_SCOPE_ALIASES

logger = logging.getLogger(__name__)


class EnvironmentEpochMixin:
    """Environment epoch lifecycle: scoping, activation, soft-invalidation."""

    # ─── 作用域归一化 ───

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

    # ─── 签名绑定 ───

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
        from genesis.v4.signature_constants import METADATA_SCHEMA_VERSION, METADATA_SCHEMA_VERSION_FIELD
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

        explicit_validation_status = self.signature.resolve_validation_status(normalized)
        invalidation_reason = self.signature.resolve_invalidation_reason(normalized)
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

        validation_status = self.signature.resolve_validation_status(normalized)
        if validation_status == "unverified" and not normalized.get("knowledge_state"):
            normalized["knowledge_state"] = "unverified"
        elif validation_status == "outdated":
            normalized["knowledge_state"] = "historical"

        if normalized.get("knowledge_state"):
            normalized["knowledge_state"] = self.signature.resolve_knowledge_state(normalized)
        return normalized

    # ─── 纪元激活/查询 ───

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
            signature = self.signature.parse(row["metadata_signature"])
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
            normalized_signature = self.signature.normalize(new_signature)
            self._conn.execute(
                "UPDATE knowledge_nodes SET metadata_signature = ?, updated_at = CURRENT_TIMESTAMP WHERE node_id = ?",
                (json.dumps(normalized_signature, ensure_ascii=False), row["node_id"])
            )
            changed += 1
        if changed:
            self._conn.commit()
            self.signature._build_dimension_registry()
        return changed

    def bind_environment_signature(self, signature: Any, ntype: str = "", context_text: str = "") -> Dict[str, Any]:
        normalized = self.signature.normalize(signature)
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
        return self.signature.normalize(normalized)
