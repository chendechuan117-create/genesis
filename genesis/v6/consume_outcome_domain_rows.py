from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from genesis.v6.canonicalize_outcome_domains import build_report as build_canonical_report
from genesis.v6.audit_outcome_domain_compatibility import CONTRACT_DOMAINS, NON_ACTIONS, safe_ratio, top_items

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTO_REPORTS_DIR = PROJECT_ROOT / "runtime" / "auto_reports"
DEFAULT_OUTPUT = PROJECT_ROOT / "runtime" / "v6_outcome_domain_row_consumption.json"
QUEUE_STATES = [
    "review_queue",
    "verification_queue",
    "training_readiness_candidates",
    "human_review_required",
    "rejected_rows",
]


def load_rows_from_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        return [row for row in data["rows"] if isinstance(row, dict)]
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def load_rows_from_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return load_rows_from_jsonl(path)
    return load_rows_from_json(path)


def queue_item(row: dict[str, Any], decision: str, reason: str) -> dict[str, Any]:
    return {
        "row_id": row.get("row_id"),
        "source_path": row.get("source_path"),
        "session_id": row.get("session_id"),
        "round": row.get("round"),
        "domain": row.get("domain"),
        "domain_state": row.get("domain_state"),
        "governance_state_hint": row.get("governance_state_hint"),
        "observed": row.get("observed"),
        "mappable": row.get("mappable"),
        "physical_only_shadowed": row.get("physical_only_shadowed"),
        "consumption_tier": row.get("consumption_tier"),
        "decision": decision,
        "reason": reason,
        "consumer_refs": row.get("consumer_refs") or [],
        "allowed_decision_effects": row.get("allowed_decision_effects") or [],
        "evidence_refs": row.get("evidence_refs") or [],
        "missing_requirements": row.get("missing_requirements") or [],
        "non_actions": row.get("non_actions") or NON_ACTIONS,
    }


def consume_row(row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    domain = str(row.get("domain") or "")
    if not row.get("mappable"):
        return "rejected_rows", queue_item(row, "reject_unmappable", "Required domain fields are missing.")
    if not row.get("observed"):
        return "rejected_rows", queue_item(row, "reject_unobserved", "Domain is mappable but not observed in this round.")
    if domain == "physical_file_outcome":
        return "review_queue", queue_item(row, "review_physical_artifact", "Physical outcome can enter patch/canary review, not automatic runtime success.")
    if domain == "knowledge_domain_evidence":
        return "review_queue", queue_item(row, "review_knowledge_evidence", "Knowledge evidence should be reviewed before any outcome or dry-state claim.")
    if domain == "line_activity_evidence":
        return "verification_queue", queue_item(row, "verify_line_activity", "Line activity requires line/graph schema review before outcome claims.")
    if domain == "line_consumption_evidence":
        if row.get("consumption_tier") == "weak_active_context":
            return "verification_queue", queue_item(row, "verify_weak_line_consumption", "Weak active-context evidence requires stronger downstream consumption proof.")
        return "verification_queue", queue_item(row, "verify_line_consumption", "Line consumption evidence requires explicit review.")
    if domain == "governance_review_outcome":
        return "training_readiness_candidates", queue_item(row, "consider_training_readiness", "Governance review outcome can become a training-readiness candidate after pollution checks.")
    return "human_review_required", queue_item(row, "unknown_domain_review", "Unknown domain requires human review.")


def queue_shell() -> dict[str, list[dict[str, Any]]]:
    return {state: [] for state in QUEUE_STATES}


def consume_rows(rows: list[dict[str, Any]], sample_limit: int = 5) -> dict[str, Any]:
    queues = queue_shell()
    domain_counter: Counter[str] = Counter()
    decision_counter: Counter[str] = Counter()
    shadow_counter: Counter[str] = Counter()
    for row in rows:
        domain = str(row.get("domain") or "unknown")
        domain_counter[domain] += 1
        queue_name, item = consume_row(row)
        decision_counter[str(item.get("decision") or "unknown")] += 1
        if row.get("physical_only_shadowed"):
            shadow_counter[domain] += 1
        queues[queue_name].append(item)
    queue_counts = {state: len(items) for state, items in queues.items()}
    return {
        "total_rows": len(rows),
        "queue_counts": queue_counts,
        "domain_distribution": top_items(domain_counter, len(CONTRACT_DOMAINS)),
        "decision_distribution": top_items(decision_counter, 16),
        "physical_only_shadowed_by_domain": top_items(shadow_counter, len(CONTRACT_DOMAINS)),
        "training_candidate_ratio": safe_ratio(queue_counts["training_readiness_candidates"], len(rows)),
        "review_or_verification_ratio": safe_ratio(queue_counts["review_queue"] + queue_counts["verification_queue"], len(rows)),
        "queues": queues,
        "queue_samples": {state: items[:sample_limit] for state, items in queues.items()},
    }


def build_report(
    auto_reports_dir: Path = DEFAULT_AUTO_REPORTS_DIR,
    rows_input: Path | None = None,
    max_rounds: int = 0,
    sample_limit: int = 5,
) -> dict[str, Any]:
    if rows_input:
        rows = load_rows(rows_input)
        source = {"rows_input": str(rows_input), "auto_reports_dir": None, "max_rounds": None}
    else:
        canonical_report = build_canonical_report(auto_reports_dir=auto_reports_dir, max_rounds=max_rounds, sample_limit=sample_limit)
        rows = [row for row in canonical_report.get("rows") or [] if isinstance(row, dict)]
        source = {"rows_input": None, "auto_reports_dir": str(auto_reports_dir), "max_rounds": max_rounds}
    consumption = consume_rows(rows, sample_limit=sample_limit)
    decision = "NO_ROWS_AVAILABLE"
    if rows:
        if consumption["queue_counts"]["review_queue"] or consumption["queue_counts"]["verification_queue"]:
            decision = "PROCEED_TO_GOVERNANCE_AGGREGATOR_DESIGN"
        elif consumption["queue_counts"]["training_readiness_candidates"]:
            decision = "REVIEW_TRAINING_READINESS_CANDIDATES"
        else:
            decision = "ROWS_CONSUMED_NO_ACTIONABLE_QUEUE"
    return {
        "schema": "genesis.v6.outcome_domain_row_consumer.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only_consumer",
        "dry_run": True,
        "consumer": "outcome_domain_row_consumer",
        "decision": decision,
        "source": source,
        "consumption": consumption,
        "constraints": NON_ACTIONS + [
            "do_not_write_queue_to_nodevault",
            "do_not_treat_training_candidates_as_training_data",
            "do_not_promote_review_queue_without_human_decision",
        ],
        "next_step": "Design a governance aggregator only after reviewing queue semantics and non-actions.",
    }


def render_text(report: dict[str, Any]) -> str:
    consumption = report.get("consumption") if isinstance(report.get("consumption"), dict) else {}
    lines = [
        "=== V6 Outcome-Domain Row Consumer ===",
        f"mode: {report.get('mode')}",
        f"dry_run: {report.get('dry_run')}",
        f"decision: {report.get('decision')}",
        f"total_rows: {consumption.get('total_rows', 0)}",
        "queue_counts:",
    ]
    counts = consumption.get("queue_counts") if isinstance(consumption.get("queue_counts"), dict) else {}
    for state in QUEUE_STATES:
        lines.append(f"  {state}: {counts.get(state, 0)}")
    lines.append("decision_distribution:")
    for item in consumption.get("decision_distribution") or []:
        lines.append(f"  {item['value']}: {item['count']}")
    lines.append("constraints:")
    for constraint in report.get("constraints") or []:
        lines.append(f"  - {constraint}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only V6 outcome-domain row consumer")
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
