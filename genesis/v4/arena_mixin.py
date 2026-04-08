"""
Genesis V4 — Arena & Confidence Mixin
知识竞技场：置信度提升/衰减、认知论演化、可靠性评分。
从 manager.py NodeVault 中提取，通过 mixin 继承合并回 NodeVault。
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

    # ─── 置信度工具方法 ───

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
        validation_status = self.signature.resolve_validation_status(self.signature.normalize(signature))
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

    @staticmethod
    def effective_confidence(node_row: Dict[str, Any]) -> float:
        """读时衰减：基于节点类型半衰期计算有效置信度。

        HUMAN 节点不衰减。其他节点按 idle 天数和类型半衰期指数衰减。
        无 schema 变更，对现有节点立即生效。
        effective_confidence < 0.2 → 搜索排除（软淘汰，不删除，可复活）。
        """
        trust_tier = node_row.get("trust_tier", "REFLECTION")
        raw_conf = float(node_row.get("confidence_score") or 0.55)
        if trust_tier == "HUMAN":
            return raw_conf

        # 取最近活跃时间
        last_verified = node_row.get("last_verified_at") or ""
        updated_at = node_row.get("updated_at") or ""
        latest = max(str(last_verified), str(updated_at))
        if not latest or latest < "2020":
            return raw_conf  # 无时间信息，不衰减

        try:
            from datetime import datetime
            latest_dt = datetime.fromisoformat(latest.replace("Z", "+00:00").replace(" ", "T"))
            now = datetime.utcnow()
            days_idle = max(0, (now - latest_dt.replace(tzinfo=None)).days)
        except (ValueError, TypeError):
            return raw_conf

        ntype = node_row.get("type", "LESSON")
        half_life = {"CONTEXT": 30, "DISCOVERY": 90, "PATTERN": 180, "LESSON": 120,
                     "EPISODE": 60, "ENTITY": 150, "EVENT": 30, "ACTION": 90}.get(ntype, 120)
        return raw_conf * (0.5 ** (days_idle / half_life))

    # ─── KB 熵 ───

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
            "temporally_expired": temporally_expired,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "last_verified_at": row_dict.get("last_verified_at") or "",
            "verification_source": row_dict.get("verification_source") or "",
        }

    # ─── 置信度提升/衰减 ───

    TIER_MIN_CONFIDENCE = {
        "CORE": 0.6,
        "VERIFIED": 0.55,
        "REFLECTION": 0.1,
        "SCAVENGED": 0.1,
        "CONVERSATION": 0.1,
    }

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

    def decay_node_confidence(self, node_id: str, penalty: float = 0.15, min_score: float = 0.1) -> float:
        """
        贝叶斯衰减：
        penalty 随节点的历史战绩自动减轻。久经考验的知识天然抗衰减（Long-Term Potentiation）。
        高信任 tier 的节点享有地板保护，永远不会被连坐打到 GC 线以下。
        """
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

    # ─── Knowledge Arena 反馈闭环 ───

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
                # Epistemic promotion: BELIEF → FACT when enough evidence accumulates
                self._try_promote_epistemic(node_id)
            else:
                self._conn.execute(
                    "UPDATE knowledge_nodes SET usage_fail_count = usage_fail_count + 1, updated_at = CURRENT_TIMESTAMP WHERE node_id = ?",
                    (node_id,)
                )
                self.decay_node_confidence(node_id, penalty=round(0.08 * w, 4), min_score=0.1)
        self._conn.commit()

    def _try_promote_epistemic(self, node_id: str):
        """Epistemic evolution: BELIEF → FACT on strong evidence, FACT → BELIEF on contradictions."""
        row = self._conn.execute(
            "SELECT epistemic_status, usage_success_count, usage_fail_count FROM knowledge_nodes WHERE node_id = ?",
            (node_id,)
        ).fetchone()
        if not row:
            return
        status = row[0] or "BELIEF"
        wins = row[1] or 0
        fails = row[2] or 0
        total = wins + fails
        if total == 0:
            return
        win_rate = wins / total
        # BELIEF/HYPOTHESIS → FACT: >=5 wins, >=80% success
        if status in ("BELIEF", "HYPOTHESIS") and wins >= 5 and win_rate >= 0.8:
            self._conn.execute(
                "UPDATE knowledge_nodes SET epistemic_status = 'FACT' WHERE node_id = ?",
                (node_id,)
            )
            logger.info(f"Epistemic promotion: [{node_id}] {status} → FACT ({wins}W/{fails}L = {win_rate:.0%})")
        # FACT → BELIEF: if win rate drops below 60% with enough data
        elif status == "FACT" and total >= 5 and win_rate < 0.6:
            self._conn.execute(
                "UPDATE knowledge_nodes SET epistemic_status = 'BELIEF' WHERE node_id = ?",
                (node_id,)
            )
            logger.info(f"Epistemic demotion: [{node_id}] FACT → BELIEF ({wins}W/{fails}L = {win_rate:.0%})")
