from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from genesis.v6.audit_outcome_domain_compatibility import (
    CONTRACT_DOMAINS,
    DOMAIN_CONSUMERS,
    DOMAIN_DECISION_EFFECTS,
    NON_ACTIONS,
    build_shadow_gap,
    classify_record_domains,
    load_round_records,
    record_path,
    safe_ratio,
    top_items,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTO_REPORTS_DIR = PROJECT_ROOT / "runtime" / "auto_reports"
DEFAULT_OUTPUT = PROJECT_ROOT / "runtime" / "v6_outcome_domain_canonical_rows.json"


def row_id(record: dict[str, Any], domain: str) -> str:
    session_id = str(record.get("session_id") or Path(str(record.get("_path") or "unknown")).parent.name or "unknown")
    round_id = str(record.get("round") if record.get("round") is not None else "unknown")
    return f"{session_id}:{round_id}:{domain}"


def governance_state_hint(domain: str, entry: dict[str, Any]) -> str:
    if not entry.get("mappable"):
        return "ignored"
    if not entry.get("observed"):
        return "observed"
    if domain == "physical_file_outcome":
        return "observed"
    if domain == "line_consumption_evidence":
        if entry.get("consumption_tier") == "weak_active_context":
            return "needs_verification"
        return "needs_verification"
    if domain == "governance_review_outcome":
        return "resolved"
    return "needs_verification"


def decision_effect_allowed(domain: str, entry: dict[str, Any]) -> list[str]:
    if not entry.get("observed"):
        return ["none"]
    if domain == "physical_file_outcome":
        return ["physical_review_candidate"]
    if domain == "knowledge_domain_evidence":
        return ["review_created", "contract_required"]
    if domain == "line_activity_evidence":
        return ["line_schema_review"]
    if domain == "line_consumption_evidence":
        return ["verify_consumption_before_outcome"]
    if domain == "governance_review_outcome":
        return ["governance_state_changed"]
    return ["none"]


def canonical_row(record: dict[str, Any], domain: str, entry: dict[str, Any]) -> dict[str, Any]:
    physical_entry = classify_record_domains(record)["physical_file_outcome"]
    return {
        "schema": "genesis.v6.outcome_domain_row.v1",
        "row_id": row_id(record, domain),
        "source_path": record_path(record),
        "session_id": record.get("session_id"),
        "round": record.get("round"),
        "status": record.get("status"),
        "progress_class": record.get("progress_class"),
        "domain": domain,
        "domain_state": entry.get("state"),
        "governance_state_hint": governance_state_hint(domain, entry),
        "mappable": bool(entry.get("mappable")),
        "observed": bool(entry.get("observed")),
        "legacy_outcome_detected": record.get("outcome_detected"),
        "physical_outcome_observed": bool(physical_entry.get("observed")),
        "physical_only_shadowed": bool(not physical_entry.get("observed") and entry.get("observed") and domain != "physical_file_outcome"),
        "consumption_tier": entry.get("consumption_tier", "none"),
        "evidence_refs": entry.get("evidence_refs") or [],
        "missing_requirements": entry.get("missing_requirements") or [],
        "consumer_refs": entry.get("consumer_refs") or DOMAIN_CONSUMERS[domain],
        "decision_effects": entry.get("decision_effects") or DOMAIN_DECISION_EFFECTS[domain],
        "allowed_decision_effects": decision_effect_allowed(domain, entry),
        "non_actions": NON_ACTIONS,
    }


def canonicalize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        domains = classify_record_domains(record)
        for domain in CONTRACT_DOMAINS:
            rows.append(canonical_row(record, domain, domains[domain]))
    return rows


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    domain_counter: Counter[str] = Counter()
    observed_counter: Counter[str] = Counter()
    mappable_counter: Counter[str] = Counter()
    governance_counter: Counter[str] = Counter()
    shadow_counter: Counter[str] = Counter()
    missing_counter: Counter[str] = Counter()
    for row in rows:
        domain = str(row.get("domain") or "unknown")
        domain_counter[domain] += 1
        governance_counter[str(row.get("governance_state_hint") or "unknown")] += 1
        if row.get("observed"):
            observed_counter[domain] += 1
        if row.get("mappable"):
            mappable_counter[domain] += 1
        if row.get("physical_only_shadowed"):
            shadow_counter[domain] += 1
        for missing in row.get("missing_requirements") or []:
            missing_counter[f"{domain}:{missing}"] += 1
    return {
        "total_rows": len(rows),
        "domain_rows": top_items(domain_counter, len(CONTRACT_DOMAINS)),
        "observed_by_domain": top_items(observed_counter, len(CONTRACT_DOMAINS)),
        "mappable_by_domain": top_items(mappable_counter, len(CONTRACT_DOMAINS)),
        "governance_state_hints": top_items(governance_counter, 12),
        "physical_only_shadowed_by_domain": top_items(shadow_counter, len(CONTRACT_DOMAINS)),
        "top_missing_requirements": top_items(missing_counter, 12),
        "observed_ratio": safe_ratio(sum(observed_counter.values()), len(rows)),
        "mappable_ratio": safe_ratio(sum(mappable_counter.values()), len(rows)),
    }


def build_report(auto_reports_dir: Path = DEFAULT_AUTO_REPORTS_DIR, max_rounds: int = 0, sample_limit: int = 5) -> dict[str, Any]:
    records = load_round_records(auto_reports_dir, max_rounds=max_rounds)
    rows = canonicalize_records(records)
    shadow_gap = build_shadow_gap(records, sample_limit=sample_limit)
    decision = "NO_ROWS_AVAILABLE"
    if rows:
        if any(row.get("physical_only_shadowed") for row in rows):
            decision = "PROCEED_TO_READ_ONLY_DOMAIN_ROW_CONSUMER_DESIGN"
        else:
            decision = "ROWS_AVAILABLE_NO_PHYSICAL_SHADOW_GAP"
    return {
        "schema": "genesis.v6.outcome_domain_canonicalizer.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only_canonicalizer",
        "dry_run": True,
        "consumer": "outcome_domain_canonicalizer",
        "decision": decision,
        "source": {
            "auto_reports_dir": str(auto_reports_dir),
            "max_rounds": max_rounds,
        },
        "contract_domains": CONTRACT_DOMAINS,
        "rounds_loaded": len(records),
        "summary": summarize_rows(rows),
        "physical_only_shadow_gap": shadow_gap,
        "rows": rows,
        "sample_rows": rows[:sample_limit],
        "constraints": NON_ACTIONS + [
            "do_not_consume_rows_as_runtime_outcome",
            "do_not_write_canonical_rows_to_nodevault",
        ],
        "next_step": "Review canonical row shape before wiring any aggregator, training builder, or runtime consumer.",
    }


def render_jsonl(rows: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "=== V6 Outcome-Domain Canonicalizer ===",
        f"mode: {report.get('mode')}",
        f"dry_run: {report.get('dry_run')}",
        f"decision: {report.get('decision')}",
        f"rounds_loaded: {report.get('rounds_loaded')}",
        f"total_rows: {(report.get('summary') or {}).get('total_rows', 0)}",
        "observed_by_domain:",
    ]
    for item in (report.get("summary") or {}).get("observed_by_domain") or []:
        lines.append(f"  {item['value']}: {item['count']}")
    gap = report.get("physical_only_shadow_gap") if isinstance(report.get("physical_only_shadow_gap"), dict) else {}
    lines.append(f"physical_only_shadow_gap_rounds: {gap.get('physical_only_shadow_gap_rounds', 0)}")
    lines.append("constraints:")
    for constraint in report.get("constraints") or []:
        lines.append(f"  - {constraint}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only V6 outcome-domain canonicalizer")
    parser.add_argument("--auto-reports-dir", default=str(DEFAULT_AUTO_REPORTS_DIR))
    parser.add_argument("--output", default="")
    parser.add_argument("--rows-output", default="")
    parser.add_argument("--max-rounds", type=int, default=0)
    parser.add_argument("--sample-limit", type=int, default=5)
    parser.add_argument("--format", choices={"text", "json", "jsonl"}, default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        auto_reports_dir=Path(args.auto_reports_dir).expanduser(),
        max_rounds=max(0, args.max_rounds),
        sample_limit=max(1, args.sample_limit),
    )
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.rows_output:
        rows_output = Path(args.rows_output).expanduser()
        rows_output.parent.mkdir(parents=True, exist_ok=True)
        rows_output.write_text(render_jsonl(report["rows"]), encoding="utf-8")
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.format == "jsonl":
        print(render_jsonl(report["rows"]))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
