from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTO_REPORTS_DIR = PROJECT_ROOT / "runtime" / "auto_reports"
DEFAULT_REVIEW_DOC = PROJECT_ROOT / "docs" / "yogg_signal_promotion_review.md"
DEFAULT_CONTRACT_DOC = PROJECT_ROOT / "docs" / "v6_outcome_domain_contract.md"
DEFAULT_OUTPUT = PROJECT_ROOT / "runtime" / "v6_outcome_domain_compatibility.json"
LINE_RESULT_RE = re.compile(r":\s*([^\s]+)\s+--\[[^\]]+\]-->\s*([^\s]+)")
CONTRACT_DOMAINS = [
    "physical_file_outcome",
    "knowledge_domain_evidence",
    "line_activity_evidence",
    "line_consumption_evidence",
    "governance_review_outcome",
]
DOMAIN_CONSUMERS = {
    "physical_file_outcome": ["auto_mode physical dry-state", "patch/canary review", "human code review"],
    "knowledge_domain_evidence": ["knowledge governance queue", "manual review", "S-A-O distillability audit"],
    "line_activity_evidence": ["PLS Line Outcome Schema review", "line/graph contract review"],
    "line_consumption_evidence": ["line consumption audit", "knowledge governance review", "future S-A-O sample builder"],
    "governance_review_outcome": ["human reviewer", "governance aggregator", "future promotion gate"],
}
DOMAIN_DECISION_EFFECTS = {
    "physical_file_outcome": ["physical dry-state", "patch review", "canary input"],
    "knowledge_domain_evidence": ["review queue", "contract_required", "verification work"],
    "line_activity_evidence": ["line schema review", "line rejection analysis"],
    "line_consumption_evidence": ["line consumption review", "training-readiness review"],
    "governance_review_outcome": ["queue transition", "promotion eligibility", "training-readiness label"],
}
NON_ACTIONS = [
    "do_not_modify_nodevault",
    "do_not_change_confidence_or_epistemic_status",
    "do_not_restart_services",
    "do_not_patch_c_phase",
    "do_not_change_dry_state_logic",
    "do_not_train_models_from_this_report",
    "do_not_broaden_outcome_detected",
]


class OutcomeDomainAuditError(RuntimeError):
    pass


def safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def top_items(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def parse_json_file(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_round_records(auto_reports_dir: Path, max_rounds: int = 0) -> list[dict[str, Any]]:
    if not auto_reports_dir.exists():
        return []
    paths = sorted(auto_reports_dir.glob("*/round_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if max_rounds > 0:
        paths = paths[:max_rounds]
    records = []
    for path in paths:
        data = parse_json_file(path)
        if not data:
            continue
        record = dict(data)
        record["_path"] = str(path)
        records.append(record)
    return records


def record_path(record: dict[str, Any]) -> str:
    return str(record.get("_path") or f"session={record.get('session_id')} round={record.get('round')}")


def has_field(record: dict[str, Any], key: str) -> bool:
    return key in record and record.get(key) is not None


def kb_delta_counts(record: dict[str, Any]) -> tuple[int, int]:
    kb_delta = record.get("kb_delta") if isinstance(record.get("kb_delta"), dict) else {}
    return list_count(kb_delta.get("new_nodes")), list_count(kb_delta.get("updated_nodes"))


def pls_telemetry(record: dict[str, Any]) -> dict[str, Any]:
    return record.get("pls_telemetry") if isinstance(record.get("pls_telemetry"), dict) else {}


def event_records(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [event for event in record.get("events") or [] if isinstance(event, dict)]


def parse_line_result(result: str) -> tuple[str, str] | None:
    match = LINE_RESULT_RE.search(result)
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def line_event_summary(record: dict[str, Any]) -> dict[str, Any]:
    success_pairs = []
    counts: Counter[str] = Counter()
    for event in event_records(record):
        if event.get("name") != "record_line":
            continue
        result = str(event.get("result_preview") or "")
        if result.startswith("✅ LINE"):
            counts["success"] += 1
            parsed = parse_line_result(result)
            if parsed:
                success_pairs.append({"new_point_id": parsed[0], "basis_point_id": parsed[1]})
        elif result.startswith("ℹ️ LINE"):
            counts["existing"] += 1
        elif result.startswith("Error:"):
            counts["error"] += 1
        else:
            counts["unknown"] += 1
    return {"counts": dict(counts), "success_pairs": success_pairs}


def active_node_ids(record: dict[str, Any]) -> set[str]:
    preview = record.get("phase_trace")
    if isinstance(preview, dict):
        preview = preview.get("current_state_preview")
    if not isinstance(preview, dict):
        return set()
    active_nodes = preview.get("active_nodes") or []
    if not isinstance(active_nodes, list):
        return set()
    ids = set()
    for item in active_nodes:
        if isinstance(item, dict):
            node_id = item.get("node_id") or item.get("id")
        else:
            node_id = item
        if node_id:
            ids.add(str(node_id))
    return ids


def has_active_nodes_field(record: dict[str, Any]) -> bool:
    preview = record.get("phase_trace")
    if isinstance(preview, dict):
        preview = preview.get("current_state_preview")
    return isinstance(preview, dict) and isinstance(preview.get("active_nodes"), list)


def domain_entry(domain: str, mappable: bool, observed: bool, evidence_refs: list[str], missing: list[str], consumption_tier: str = "none") -> dict[str, Any]:
    if observed:
        state = "observed"
    elif mappable:
        state = "mappable_absent"
    else:
        state = "missing_fields"
    return {
        "domain": domain,
        "state": state,
        "mappable": mappable,
        "observed": observed,
        "evidence_refs": evidence_refs,
        "missing_requirements": missing,
        "consumer_refs": DOMAIN_CONSUMERS[domain],
        "decision_effects": DOMAIN_DECISION_EFFECTS[domain],
        "consumption_tier": consumption_tier,
    }


def classify_record_domains(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    new_nodes, updated_nodes = kb_delta_counts(record)
    telemetry = pls_telemetry(record)
    line_summary = line_event_summary(record)
    active_ids = active_node_ids(record)
    line_new_ids = {item["new_point_id"] for item in line_summary["success_pairs"]}
    active_line_hits = sorted(active_ids & line_new_ids)
    has_active_context = has_active_nodes_field(record)
    line_consumption_missing = []
    if not line_new_ids:
        line_consumption_missing.append("record_line_success")
    if not has_active_context:
        line_consumption_missing.append("phase_trace.current_state_preview.active_nodes")

    physical_mappable = isinstance(record.get("outcome_detected"), bool)
    physical_observed = record.get("outcome_detected") is True

    knowledge_mappable = has_field(record, "kb_changed") or isinstance(record.get("kb_delta"), dict) or isinstance(record.get("pls_telemetry"), dict)
    knowledge_observed = record.get("kb_changed") is True or new_nodes > 0 or updated_nodes > 0 or int_value(telemetry.get("points_created")) > 0

    line_activity_mappable = isinstance(record.get("pls_telemetry"), dict) or isinstance(record.get("events"), list)
    line_activity_observed = (
        int_value(telemetry.get("lines_created")) > 0
        or int_value(telemetry.get("cross_round_lines")) > 0
        or int_value(telemetry.get("line_errors")) > 0
        or sum(int_value(value) for value in line_summary["counts"].values()) > 0
    )

    line_consumption_mappable = bool(line_new_ids) and has_active_context
    line_consumption_observed = bool(active_line_hits)

    governance_mappable = any(has_field(record, key) for key in ["governance_review", "review_decision", "outcome_domains"])
    governance_observed = governance_mappable

    return {
        "physical_file_outcome": domain_entry(
            "physical_file_outcome",
            physical_mappable,
            physical_observed,
            ["outcome_detected"] if physical_mappable else [],
            [] if physical_mappable else ["outcome_detected_bool"],
        ),
        "knowledge_domain_evidence": domain_entry(
            "knowledge_domain_evidence",
            knowledge_mappable,
            knowledge_observed,
            [ref for ref, present in [
                ("kb_changed", has_field(record, "kb_changed")),
                ("kb_delta", isinstance(record.get("kb_delta"), dict)),
                ("pls_telemetry.points_created", isinstance(record.get("pls_telemetry"), dict)),
            ] if present],
            [] if knowledge_mappable else ["kb_changed_or_kb_delta"],
        ),
        "line_activity_evidence": domain_entry(
            "line_activity_evidence",
            line_activity_mappable,
            line_activity_observed,
            [ref for ref, present in [
                ("pls_telemetry.lines_created", isinstance(record.get("pls_telemetry"), dict)),
                ("events.record_line", bool(line_summary["counts"])),
            ] if present],
            [] if line_activity_mappable else ["pls_telemetry_or_events"],
        ),
        "line_consumption_evidence": domain_entry(
            "line_consumption_evidence",
            line_consumption_mappable,
            line_consumption_observed,
            ["events.record_line", "phase_trace.current_state_preview.active_nodes"] if line_consumption_mappable else [],
            line_consumption_missing,
            "weak_active_context" if line_consumption_observed else "none",
        ),
        "governance_review_outcome": domain_entry(
            "governance_review_outcome",
            governance_mappable,
            governance_observed,
            [key for key in ["governance_review", "review_decision", "outcome_domains"] if has_field(record, key)],
            [] if governance_mappable else ["governance_review_or_review_decision_or_outcome_domains"],
        ),
    }


def build_domain_coverage(records: list[dict[str, Any]], top_limit: int) -> dict[str, Any]:
    domain_stats: dict[str, dict[str, Any]] = {}
    for domain in CONTRACT_DOMAINS:
        domain_stats[domain] = {
            "mappable_rounds": 0,
            "observed_rounds": 0,
            "missing_requirements": Counter(),
            "consumer_refs": DOMAIN_CONSUMERS[domain],
            "decision_effects": DOMAIN_DECISION_EFFECTS[domain],
        }
    for record in records:
        domains = classify_record_domains(record)
        for domain, entry in domains.items():
            if entry["mappable"]:
                domain_stats[domain]["mappable_rounds"] += 1
            if entry["observed"]:
                domain_stats[domain]["observed_rounds"] += 1
            domain_stats[domain]["missing_requirements"].update(entry["missing_requirements"])
    return {
        domain: {
            "mappable_rounds": values["mappable_rounds"],
            "mappable_ratio": safe_ratio(values["mappable_rounds"], len(records)),
            "observed_rounds": values["observed_rounds"],
            "observed_ratio": safe_ratio(values["observed_rounds"], len(records)),
            "top_missing_requirements": top_items(values["missing_requirements"], top_limit),
            "consumer_refs": values["consumer_refs"],
            "decision_effects": values["decision_effects"],
        }
        for domain, values in domain_stats.items()
    }


def build_shadow_gap(records: list[dict[str, Any]], sample_limit: int) -> dict[str, Any]:
    hidden_counter: Counter[str] = Counter()
    samples = []
    physical_absent_rounds = 0
    shadow_gap_rounds = 0
    for record in records:
        domains = classify_record_domains(record)
        physical = domains["physical_file_outcome"]
        if not physical["observed"]:
            physical_absent_rounds += 1
        non_physical_observed = [
            domain for domain in ["knowledge_domain_evidence", "line_activity_evidence", "line_consumption_evidence", "governance_review_outcome"]
            if domains[domain]["observed"]
        ]
        if physical["observed"] or not non_physical_observed:
            continue
        shadow_gap_rounds += 1
        for domain in non_physical_observed:
            hidden_counter[domain] += 1
        if len(samples) < sample_limit:
            samples.append({
                "path": record_path(record),
                "session_id": record.get("session_id"),
                "round": record.get("round"),
                "outcome_detected": record.get("outcome_detected"),
                "non_physical_domains": non_physical_observed,
            })
    return {
        "physical_absent_rounds": physical_absent_rounds,
        "physical_only_shadow_gap_rounds": shadow_gap_rounds,
        "non_physical_observed_when_physical_absent": top_items(hidden_counter, 12),
        "shadow_gap_ratio_among_physical_absent_rounds": safe_ratio(shadow_gap_rounds, physical_absent_rounds),
        "samples": samples,
    }


def sample_round_mappings(records: list[dict[str, Any]], sample_limit: int) -> list[dict[str, Any]]:
    samples = []
    for record in records[:sample_limit]:
        domains = classify_record_domains(record)
        samples.append({
            "path": record_path(record),
            "session_id": record.get("session_id"),
            "round": record.get("round"),
            "status": record.get("status"),
            "progress_class": record.get("progress_class"),
            "outcome_detected": record.get("outcome_detected"),
            "domains": domains,
        })
    return samples


def read_artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "available": False, "error": "file_not_found"}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {"path": str(path), "available": False, "error": str(exc)}
    return {"path": str(path), "available": True, "bytes": len(text.encode("utf-8"))}


def build_report(
    auto_reports_dir: Path = DEFAULT_AUTO_REPORTS_DIR,
    review_doc: Path = DEFAULT_REVIEW_DOC,
    contract_doc: Path = DEFAULT_CONTRACT_DOC,
    max_rounds: int = 0,
    top_limit: int = 12,
    sample_limit: int = 5,
) -> dict[str, Any]:
    records = load_round_records(auto_reports_dir, max_rounds=max_rounds)
    coverage = build_domain_coverage(records, top_limit=top_limit)
    shadow_gap = build_shadow_gap(records, sample_limit=sample_limit)
    decision = "NO_ROUNDS_AVAILABLE"
    if records:
        if coverage["physical_file_outcome"]["mappable_rounds"] > 0 and any(coverage[domain]["observed_rounds"] > 0 for domain in CONTRACT_DOMAINS):
            decision = "PROCEED_TO_READ_ONLY_DOMAIN_CANONICALIZER_DESIGN"
        else:
            decision = "COLLECT_MORE_DOMAIN_COMPATIBLE_REPORTS"
    return {
        "schema": "genesis.v6.outcome_domain_compatibility.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only_audit",
        "dry_run": True,
        "consumer": "outcome_domain_compatibility_audit",
        "decision": decision,
        "source": {
            "auto_reports_dir": str(auto_reports_dir),
            "review_doc": str(review_doc),
            "contract_doc": str(contract_doc),
            "max_rounds": max_rounds,
        },
        "contract_domains": CONTRACT_DOMAINS,
        "domain_coverage": coverage,
        "physical_only_shadow_gap": shadow_gap,
        "rounds": {
            "total_loaded": len(records),
            "samples": sample_round_mappings(records, sample_limit=sample_limit),
        },
        "external_artifacts": {
            "review_doc": read_artifact(review_doc),
            "contract_doc": read_artifact(contract_doc),
        },
        "constraints": NON_ACTIONS,
        "next_step": "Design a read-only domain canonicalizer only after reviewing missing requirements and consumers.",
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "=== V6 Outcome-Domain Compatibility Audit ===",
        f"mode: {report.get('mode')}",
        f"dry_run: {report.get('dry_run')}",
        f"consumer: {report.get('consumer')}",
        f"decision: {report.get('decision')}",
        f"rounds_loaded: {(report.get('rounds') or {}).get('total_loaded', 0)}",
        "domain_coverage:",
    ]
    coverage = report.get("domain_coverage") if isinstance(report.get("domain_coverage"), dict) else {}
    for domain in CONTRACT_DOMAINS:
        item = coverage.get(domain) or {}
        lines.append(f"  {domain}: mappable={item.get('mappable_rounds', 0)} observed={item.get('observed_rounds', 0)}")
    gap = report.get("physical_only_shadow_gap") if isinstance(report.get("physical_only_shadow_gap"), dict) else {}
    lines.append(f"physical_only_shadow_gap_rounds: {gap.get('physical_only_shadow_gap_rounds', 0)}")
    lines.append("constraints:")
    for constraint in report.get("constraints") or []:
        lines.append(f"  - {constraint}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only V6 outcome-domain compatibility audit")
    parser.add_argument("--auto-reports-dir", default=str(DEFAULT_AUTO_REPORTS_DIR))
    parser.add_argument("--review-doc", default=str(DEFAULT_REVIEW_DOC))
    parser.add_argument("--contract-doc", default=str(DEFAULT_CONTRACT_DOC))
    parser.add_argument("--output", default="")
    parser.add_argument("--max-rounds", type=int, default=0)
    parser.add_argument("--top-limit", type=int, default=12)
    parser.add_argument("--sample-limit", type=int, default=5)
    parser.add_argument("--format", choices={"text", "json"}, default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        auto_reports_dir=Path(args.auto_reports_dir).expanduser(),
        review_doc=Path(args.review_doc).expanduser(),
        contract_doc=Path(args.contract_doc).expanduser(),
        max_rounds=max(0, args.max_rounds),
        top_limit=max(1, args.top_limit),
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
