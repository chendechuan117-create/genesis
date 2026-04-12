"""
Genesis V4 — Arena & Knowledge Quality Mixin
知识竞技场：使用反馈闭环、成熟度评分、可靠性画像。
从 manager.py NodeVault 中提取，通过 mixin 继承合并回 NodeVault。

设计原则（2026-04 重构）：
  - 知识不会因时间流逝而失效，只会因事件（环境变化、使用失败、显式矛盾）而失效
  - 质量信号来自使用战绩（usage_success/fail），不是创建时 LLM 拍的分数
  - 时间维度用于成熟度（老兵比新兵可靠），不用于衰减
  - 节点淘汰由事件驱动：epoch_stale / CONTRADICTS 边 / 高失败率
"""


import json
import math
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

TRUST_TIERS = ("HUMAN", "REFLECTION", "FERMENTED", "SCAVENGED", "CONVERSATION")


class ArenaConfidenceMixin:
    """Knowledge Arena feedback loop + confidence/reliability scoring."""

    # ─── 工具方法 ───

    TIER_BASE = {"HUMAN": 1.0, "REFLECTION": 0.6, "SCAVENGED": 0.4,
                 "CONVERSATION": 0.55, "FERMENTED": 0.45, "OBSERVATION": 0.6}

    def _parse_db_timestamp(self, raw_value: Any) -> Optional[datetime]:
        if not raw_value:
            return None
        try:
            return datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def effective_confidence(node_row: Dict[str, Any]) -> float:
        """基于使用战绩的质量评分。无时间衰减。

        知识不会因时间流逝失效——只会因事件失效（环境变化、矛盾、使用失败）。
        评分反映经验性战绩：
          - HUMAN 节点 → 1.0
          - 有使用记录 → 0.5 + 0.4 × success_rate（范围 0.5~0.9）
          - 未使用 → tier 默认值（REFLECTION=0.6）
        节点淘汰由 CONTRADICTS 边 / epoch_stale 驱动，不由此分数驱动。
        """
        trust_tier = node_row.get("trust_tier", "REFLECTION")
        if trust_tier == "HUMAN":
            return 1.0

        success = node_row.get("usage_success_count", 0) or 0
        fail = node_row.get("usage_fail_count", 0) or 0
        total = success + fail

        if total > 0:
            return 0.5 + 0.4 * (success / total)

        TIER_BASE = {"HUMAN": 1.0, "REFLECTION": 0.6, "SCAVENGED": 0.4,
                     "CONVERSATION": 0.55, "FERMENTED": 0.45, "OBSERVATION": 0.6}
        return TIER_BASE.get(trust_tier, 0.55)

    # ─── KB 熵 ───

    def get_kb_entropy(self) -> Optional[Dict[str, Any]]:
        try:
            total_row = self._conn.execute(
                "SELECT COUNT(*), "
                "SUM(CASE WHEN usage_fail_count > 0 AND usage_fail_count > usage_success_count THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN usage_success_count >= 3 THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN usage_count = 0 THEN 1 ELSE 0 END) "
                "FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%'"
            ).fetchone()
            total_nodes = total_row[0] or 0
            if total_nodes > 0:
                return {
                    "total_nodes": total_nodes,
                    "failing_pct": round((total_row[1] or 0) / total_nodes, 3),
                    "proven_pct": round((total_row[2] or 0) / total_nodes, 3),
                    "untested_pct": round((total_row[3] or 0) / total_nodes, 3),
                }
        except Exception:
            pass
        return None

    # ─── 可靠性画像 ───

    def build_reliability_profile(self, row: Dict[str, Any]) -> Dict[str, Any]:
        row_dict = dict(row or {})
        signature = self.signature.parse(row_dict.get("metadata_signature"))
        validation_status = self.signature.resolve_validation_status(signature)
        knowledge_state = self.signature.resolve_knowledge_state(signature, row_dict.get("ntype") or row_dict.get("type") or "")
        observed_environment_scope = self._resolve_observed_environment_scope(signature)
        observed_environment_epoch = self._resolve_observed_environment_epoch(signature)
        environment_scope = self._resolve_applicable_environment_scope(signature)
        environment_epoch = self._resolve_applicable_environment_epoch(signature)
        active_environment = self.get_active_environment_epoch(environment_scope) if environment_scope else None
        active_environment_epoch = active_environment["epoch_id"] if active_environment else ""
        invalidation_reason = self.signature.infer_invalidation_reason(
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
        quality_score = self.effective_confidence(row_dict)

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
        trust_score = quality_score * 6.0 + freshness_score + tier_bonus.get(trust_tier, 0.0) + state_bonus.get(knowledge_state, 0.0)
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

        # Temporal validity: check valid_until expiry
        valid_from = signature.get("valid_from") or ""
        valid_until = signature.get("valid_until") or ""
        temporally_expired = False
        if valid_until:
            try:
                expiry = datetime.strptime(valid_until, "%Y-%m-%d")
                if datetime.utcnow() > expiry:
                    temporally_expired = True
                    trust_score -= 1.5
                    if knowledge_state != "historical":
                        knowledge_state = "historical"
            except (ValueError, TypeError):
                pass

        return {
            "confidence_score": round(quality_score, 3),
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
            "temporally_expired": temporally_expired,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "last_verified_at": row_dict.get("last_verified_at") or "",
            "verification_source": row_dict.get("verification_source") or "",
        }

    # ─── 使用反馈 ───

    def promote_node_title(self, node_id: str):
        """
        转正晋升：移除标题中的 [拾荒] 标记。
        置信度不再由标量控制，quality 由 usage 战绩自动派生。
        """
        row = self._conn.execute("SELECT title FROM knowledge_nodes WHERE node_id = ?", (node_id,)).fetchone()
        if not row:
            return
        old_title = row[0] if row[0] else ""
        if "[拾荒]" not in old_title:
            return
        new_title = old_title.replace("[拾荒] ", "").strip()
        self._conn.execute(
            "UPDATE knowledge_nodes SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE node_id = ?",
            (new_title, node_id)
        )
        self._conn.commit()
        logger.info(f"NodeVault: Promoted title [{node_id}]: removed [拾荒]")

    # ─── Knowledge Arena 反馈闭环 ───

    def record_usage_outcome(self, node_ids: List[str], success: bool, weights: Dict[str, float] = None):
        """
        Knowledge Arena 反馈闭环：
        记录节点在实际任务中的使用结果（成功/失败）。
        quality_score 由 usage 计数自动派生，无需额外调整。
        成功时还会移除 [拾荒] 标记（转正）。
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
                self.promote_node_title(node_id)
            else:
                self._conn.execute(
                    "UPDATE knowledge_nodes SET usage_fail_count = usage_fail_count + 1, updated_at = CURRENT_TIMESTAMP WHERE node_id = ?",
                    (node_id,)
                )
        self._conn.commit()
