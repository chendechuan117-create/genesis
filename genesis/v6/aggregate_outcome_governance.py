from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from genesis.v6.consume_outcome_domain_rows import build_report as build_consumer_report
from genesis.v6.audit_outcome_domain_compatibility import NON_ACTIONS, safe_ratio, top_items

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTO_REPORTS_DIR = PROJECT_ROOT / "runtime" / "auto_reports"
DEFAULT_OUTPUT = PROJECT_ROOT / "runtime" / "v6_outcome_governance_aggregation.json"
GOVERNANCE_STATES = [
    "observed",
    "candidate",
    "needs_verification",
    "needs_resolution",
    "needs_human_review",
    "quarantined_candidate",
    "resolved",
    "ignored",
]
DECISION_TO_STATE = {
    "review_physical_artifact": "candidate",
    "review_knowledge_evidence": "needs_resolution",
    "verify_line_activity": "needs_verification",
    "verify_weak_line_consumption": "needs_verification",
    "verify_line_consumption": "needs_verification",
    "consider_training_readiness": "needs_human_review",
    "unknown_domain_review": "needs_human_review",
    "reject_unmappable": "ignored",
    "reject_unobserved": "ignored",
}
DECISION_TO_TARGET = {
    "review_physical_artifact": "PhysicalArtifactReview",
    "review_knowledge_evidence": "GovernanceReviewOutcomeDraft",
    "verify_line_activity": "LineActivityVerification",
    "verify_weak_line_consumption": "LineConsumptionVerification",
    "verify_line_consumption": "LineConsumptionVerification",
    "consider_training_readiness": "TrainingReadinessReview",
    "unknown_domain_review": "ManualDomainReview",
    "reject_unmappable": "none",
    "reject_unobserved": "none",
}
DECISION_TO_ACTION = {
    "review_physical_artifact": "review_physical_artifact_before_patch_or_canary",
    "review_knowledge_evidence": "decide_whether_to_create_governance_review_outcome",
    "verify_line_activity": "verify_line_schema_before_outcome_claim",
    "verify_weak_line_consumption": "require_stronger_downstream_consumption_evidence",
    "verify_line_consumption": "review_line_consumption_evidence",
    "consider_training_readiness": "run_pollution_and_review_checks_before_training",
    "unknown_domain_review": "manual_review_unknown_domain",
    "reject_unmappable": "ignore_until_required_fields_exist",
    "reject_unobserved": "ignore_until_domain_observed",
}


def state_shell() -> dict[str, list[dict[str, Any]]]:
    return {state: [] for state in GOVERNANCE_STATES}


def aggregate_key(item: dict[str, Any]) -> tuple[str, str]:
    return str(item.get("decision") or "unknown"), str(item.get("domain") or "unknown")


def priority_for(decision: str, row_count: int, shadowed_count: int) -> str:
    if decision == "review_knowledge_evidence" and shadowed_count > 0:
        return "P0"
    if decision in {"verify_line_activity", "verify_weak_line_consumption", "verify_line_consumption"} and row_count > 0:
        return "P1"
    if decision in {"review_physical_artifact", "consider_training_readiness", "unknown_domain_review"}:
        return "P1"
    return "P3"


def claim_for(decision: str, domain: str, row_count: int, shadowed_count: int) -> str:
    if decision == "review_knowledge_evidence":
        return f"{row_count} {domain} rows require governance review; {shadowed_count} are hidden by a physical-only outcome lens."
    if decision == "verify_line_activity":
        return f"{row_count} {domain} rows require line/graph verification before outcome claims."
    if decision in {"verify_weak_line_consumption", "verify_line_consumption"}:
        return f"{row_count} {domain} rows require stronger downstream consumption verification."
    if decision == "review_physical_artifact":
        return f"{row_count} physical artifact rows can enter review but are not automatic runtime success."
    if decision == "consider_training_readiness":
        return f"{row_count} governance review outcome rows can enter training-readiness review after pollution checks."
    if decision == "reject_unmappable":
        return f"{row_count} {domain} rows are unmappable and should remain ignored until required fields exist."
    if decision == "reject_unobserved":
        return f"{row_count} {domain} rows are mappable but unobserved and should remain ignored."
    return f"{row_count} {domain} rows require manual review."


def verification_method_for(decision: str) -> str:
    if decision == "review_knowledge_evidence":
        return "Sample source rows, verify evidence_refs, then explicitly accept/reject governance_review_outcome creation."
    if decision == "verify_line_activity":
        return "Compare line telemetry/events with line schema expectations and separate successful, existing, and rejected lines."
    if decision in {"verify_weak_line_consumption", "verify_line_consumption"}:
        return "Require stronger downstream evidence such as later reasoning basis use, review citation, behavior change, or training inclusion."
    if decision == "review_physical_artifact":
        return "Inspect sandbox/git diff evidence and route to patch/canary review only if artifact is meaningful."
    if decision == "consider_training_readiness":
        return "Run pollution, attribution, and reviewer-decision checks before treating as training-ready."
    return "No verification required unless new evidence appears."


def build_aggregate_item(decision: str, domain: str, items: list[dict[str, Any]], sample_limit: int) -> dict[str, Any]:
    row_count = len(items)
    shadowed_count = sum(1 for item in items if item.get("physical_only_shadowed"))
    state = DECISION_TO_STATE.get(decision, "needs_human_review")
    evidence_refs = sorted({ref for item in items for ref in item.get("evidence_refs") or []})
    missing_requirements = sorted({ref for item in items for ref in item.get("missing_requirements") or []})
    source_refs = [str(item.get("source_path")) for item in items[:sample_limit] if item.get("source_path")]
    sample_row_ids = [str(item.get("row_id")) for item in items[:sample_limit] if item.get("row_id")]
    return {
        "aggregate_id": f"{decision}:{domain}",
        "governance_state": state,
        "priority": priority_for(decision, row_count, shadowed_count),
        "decision": decision,
        "domain": domain,
        "row_count": row_count,
        "physical_only_shadowed_count": shadowed_count,
        "claim": claim_for(decision, domain, row_count, shadowed_count),
        "source_refs": source_refs,
        "sample_row_ids": sample_row_ids,
        "evidence_refs": evidence_refs,
        "missing_requirements": missing_requirements,
        "verification_method": verification_method_for(decision),
        "promotion_target": DECISION_TO_TARGET.get(decision, "ManualDomainReview"),
        "consumer_decision": DECISION_TO_ACTION.get(decision, "manual_review_required"),
        "non_actions": NON_ACTIONS + [
            "do_not_write_aggregation_to_nodevault",
            "do_not_promote_without_human_decision",
            "do_not_treat_aggregation_as_runtime_outcome",
        ],
    }


def aggregate_consumption(consumption: dict[str, Any], sample_limit: int = 5) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    queues = consumption.get("queues") if isinstance(consumption.get("queues"), dict) else {}
    for queue_items in queues.values():
        for item in queue_items or []:
            if isinstance(item, dict):
                groups[aggregate_key(item)].append(item)
    state_queues = state_shell()
    for (decision, domain), items in sorted(groups.items()):
        aggregate = build_aggregate_item(decision, domain, items, sample_limit=sample_limit)
        state_queues[aggregate["governance_state"]].append(aggregate)
    for state in state_queues:
        state_queues[state].sort(key=lambda item: (item["priority"], -int(item["row_count"]), item["aggregate_id"]))
    return state_queues


def aggregate_counts(aggregates: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    return {state: len(items) for state, items in aggregates.items()}


def summarize_aggregates(aggregates: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    priority_counter: Counter[str] = Counter()
    state_row_counter: Counter[str] = Counter()
    domain_counter: Counter[str] = Counter()
    for state, items in aggregates.items():
        for item in items:
            priority_counter[str(item.get("priority") or "unknown")] += 1
            state_row_counter[state] += int(item.get("row_count") or 0)
            domain_counter[str(item.get("domain") or "unknown")] += int(item.get("row_count") or 0)
    return {
        "aggregate_counts": aggregate_counts(aggregates),
        "row_counts_by_governance_state": top_items(state_row_counter, len(GOVERNANCE_STATES)),
        "row_counts_by_domain": top_items(domain_counter, 12),
        "priority_distribution": top_items(priority_counter, 8),
    }


def build_report(
    auto_reports_dir: Path = DEFAULT_AUTO_REPORTS_DIR,
    rows_input: Path | None = None,
    max_rounds: int = 0,
    sample_limit: int = 5,
) -> dict[str, Any]:
    consumer_report = build_consumer_report(
        auto_reports_dir=auto_reports_dir,
        rows_input=rows_input,
        max_rounds=max_rounds,
        sample_limit=max(1, sample_limit),
    )
    consumption = consumer_report.get("consumption") if isinstance(consumer_report.get("consumption"), dict) else {}
    aggregates = aggregate_consumption(consumption, sample_limit=max(1, sample_limit))
    summary = summarize_aggregates(aggregates)
    decision = "NO_AGGREGATES_AVAILABLE"
    counts = summary["aggregate_counts"]
    if counts.get("needs_resolution") or counts.get("needs_verification"):
        decision = "READY_FOR_MANUAL_GOVERNANCE_REVIEW"
    elif counts.get("candidate") or counts.get("needs_human_review"):
        decision = "READY_FOR_TARGETED_HUMAN_REVIEW"
    elif counts.get("ignored"):
        decision = "ONLY_IGNORED_AGGREGATES_AVAILABLE"
    return {
        "schema": "genesis.v6.outcome_governance_aggregation.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only_governance_aggregator",
        "dry_run": True,
        "consumer": "outcome_governance_aggregator",
        "decision": decision,
        "source": consumer_report.get("source"),
        "input_consumer_decision": consumer_report.get("decision"),
        "input_queue_counts": consumption.get("queue_counts"),
        "input_total_rows": consumption.get("total_rows", 0),
        "summary": summary,
        "aggregates": aggregates,
        "constraints": NON_ACTIONS + [
            "do_not_write_aggregation_to_nodevault",
            "do_not_create_governance_review_outcome_without_human_decision",
            "do_not_train_from_aggregates",
            "do_not_change_runtime_from_aggregates",
        ],
        "next_step": "Human reviewer should decide P0/P1 aggregate items before any governance_review_outcome or training-readiness artifact is created.",
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "=== V6 Outcome Governance Aggregator ===",
        f"mode: {report.get('mode')}",
        f"dry_run: {report.get('dry_run')}",
        f"decision: {report.get('decision')}",
        f"input_total_rows: {report.get('input_total_rows', 0)}",
        "aggregate_counts:",
    ]
    counts = ((report.get("summary") or {}).get("aggregate_counts") or {})
    for state in GOVERNANCE_STATES:
        lines.append(f"  {state}: {counts.get(state, 0)}")
    lines.append("top_aggregates:")
    aggregates = report.get("aggregates") if isinstance(report.get("aggregates"), dict) else {}
    for state in ["needs_resolution", "needs_verification", "candidate", "needs_human_review", "ignored"]:
        for item in (aggregates.get(state) or [])[:3]:
            lines.append(f"  {state}: {item.get('priority')} {item.get('aggregate_id')} rows={item.get('row_count')}")
    lines.append("constraints:")
    for constraint in report.get("constraints") or []:
        lines.append(f"  - {constraint}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only V6 outcome governance aggregator")
    parser.add_argument("--auto-reports-dir", default=str(DEFAULT_AUTO_REPORTS_DIR))
    parser.add_argument("--rows-input", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--max-rounds", type=int, default=0)
    parser.add_argument("--sample-limit", type=int, default=5)
    parser.add_argument("--format", choices={"text", "json"}, default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows_input = Path(args.rows_input).expanduser() if args.rows_input else None
    report = build_report(
        auto_reports_dir=Path(args.auto_reports_dir).expanduser(),
        rows_input=rows_input,
        max_rounds=max(0, args.max_rounds),
        sample_limit=max(1, args.sample_limit),
    )
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
