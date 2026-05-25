from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTO_REPORTS_DIR = PROJECT_ROOT / "runtime" / "auto_reports"
DEFAULT_TRACES_DB = PROJECT_ROOT / "runtime" / "traces.db"
DEFAULT_SHADOW_LOG = PROJECT_ROOT / "runtime" / "v6_shadow_predictions.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "runtime" / "v6_sao_distillability_report.json"
SAO_FIELD_GROUPS = {
    "state": ["knowledge_state", "frontier_state", "phase_trace"],
    "action": ["events", "round_topology"],
    "outcome": ["progress_class", "outcome_detected_bool", "kb_delta"],
    "connection": ["pls_telemetry", "round_topology"],
}


class SaoAuditError(RuntimeError):
    pass


def safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


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
        data = dict(data)
        data["_path"] = str(path)
        records.append(data)
    return records


def event_names(record: dict[str, Any], event_types: set[str] | None = None) -> list[str]:
    names = []
    for event in record.get("events") or []:
        if not isinstance(event, dict):
            continue
        if event_types and event.get("type") not in event_types:
            continue
        name = str(event.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def joined_event_text(record: dict[str, Any]) -> str:
    parts = []
    for event in record.get("events") or []:
        if not isinstance(event, dict):
            continue
        parts.append(str(event.get("name") or ""))
        parts.append(str(event.get("result_preview") or ""))
        args = event.get("args")
        if isinstance(args, dict):
            parts.append(json.dumps(args, ensure_ascii=False, sort_keys=True))
        data = event.get("data")
        if isinstance(data, dict):
            parts.append(json.dumps(data, ensure_ascii=False, sort_keys=True))
    parts.append(str(record.get("activity_summary") or ""))
    parts.append(str(record.get("response_preview") or ""))
    return "\n".join(parts).lower()


def compact_record_text(record: dict[str, Any]) -> str:
    parts = [joined_event_text(record)]
    for key in ("knowledge_state", "frontier_state", "phase_trace", "activity_summary", "attention_residue"):
        value = record.get(key)
        if isinstance(value, (dict, list)):
            parts.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
        elif value:
            parts.append(str(value))
    return "\n".join(parts).lower()


def active_node_count(record: dict[str, Any]) -> int:
    preview = record.get("phase_trace")
    if isinstance(preview, dict):
        preview = preview.get("current_state_preview")
    if not isinstance(preview, dict):
        return 0
    active_nodes = preview.get("active_nodes") or []
    return len(active_nodes) if isinstance(active_nodes, list) else 0


def semantic_risk_flags(record: dict[str, Any]) -> list[str]:
    flags = []
    text = compact_record_text(record)
    if active_node_count(record) > 0:
        flags.append("arena_collective_attribution_risk")
    if "env_fact" in text or "environment fact" in text or "环境事实" in text:
        flags.append("env_fact_state_risk")
    if "contradicts" in text or "contradiction" in text or "矛盾" in text:
        flags.append("contradiction_conflict_risk")
    return flags


def has_write_signal(record: dict[str, Any]) -> bool:
    names = set(event_names(record, {"tool_start", "tool_result", "search_result"}))
    if names & {"write_file", "edit_file", "replace_in_file", "append_file"}:
        return True
    text = joined_event_text(record)
    markers = ["sed -i", "write_text(", "text = text.replace(", "cat >", "cat >>", "tee ", "patch ", "git apply", " > ", " >> "]
    return any(marker in text for marker in markers)


def has_test_signal(record: dict[str, Any]) -> bool:
    text = joined_event_text(record)
    return any(marker in text for marker in ["pytest", "doctor.sh test", "unittest", "npm test", "go test", "cargo test"])


def has_read_signal(record: dict[str, Any]) -> bool:
    names = set(event_names(record, {"tool_start", "tool_result", "search_result"}))
    if names & {"read_file", "grep_files", "list_directory", "search_knowledge_nodes", "get_knowledge_node_content"}:
        return True
    text = joined_event_text(record)
    return any(marker in text for marker in ["sed -n", "cat ", "grep", "rg ", "git diff"])


def classify_route_family(record: dict[str, Any]) -> str:
    topology = record.get("round_topology") if isinstance(record.get("round_topology"), dict) else {}
    telemetry = record.get("pls_telemetry") if isinstance(record.get("pls_telemetry"), dict) else {}
    names = set(event_names(record, {"tool_start", "tool_result", "search_result"}))
    text = joined_event_text(record)

    if record.get("status") == "timeout" or topology.get("timeout_risk_shape") is True:
        return "timeout_runaway"
    if int(telemetry.get("points_created") or 0) > 0 and int(telemetry.get("lines_created") or 0) > 0:
        return "pls_point_line_anchor"
    if int(telemetry.get("points_created") or 0) > 0 or names & {"record_point", "record_context_node", "record_lesson_node"}:
        if "search_knowledge_nodes" in names or int(record.get("knowledge_search_count") or 0) > 0:
            return "search_then_record"
        return "record_without_search"
    if has_test_signal(record):
        return "test_or_doctor_verify"
    if has_write_signal(record):
        return "code_read_then_patch"
    if int(record.get("reanchor_streak") or 0) >= 2 or (record.get("state_freshness") or {}).get("state_stale"):
        return "self_referential_report_loop"
    if has_read_signal(record):
        return "inspect_only"
    if "llm_call_start" in text and not names:
        return "text_only_reasoning"
    return "mixed_or_unknown"


def weak_outcome_labels(record: dict[str, Any]) -> list[str]:
    labels = []
    status = str(record.get("status") or "unknown").strip() or "unknown"
    progress = str(record.get("progress_class") or "unknown").strip() or "unknown"
    labels.append(f"status:{status}")
    labels.append(f"progress:{progress}")

    outcome = record.get("outcome_detected")
    if outcome is True:
        labels.append("outcome:sandbox_diff_changed")
    elif outcome is False:
        labels.append("outcome:no_sandbox_diff")
    else:
        labels.append("outcome:missing_or_legacy")

    if record.get("kb_changed") is True:
        labels.append("kb:changed")
    elif record.get("kb_changed") is False:
        labels.append("kb:unchanged")
    else:
        labels.append("kb:unknown")

    c_phase = record.get("c_phase_summary") if isinstance(record.get("c_phase_summary"), dict) else {}
    if int(c_phase.get("supplements") or 0) > 0:
        labels.append("c_phase:supplemented")
    elif c_phase:
        labels.append("c_phase:no_supplement")
    else:
        labels.append("c_phase:missing")

    telemetry = record.get("pls_telemetry") if isinstance(record.get("pls_telemetry"), dict) else {}
    if int(telemetry.get("points_created") or 0) > 0:
        labels.append("pls:point_created")
    if int(telemetry.get("lines_created") or 0) > 0:
        labels.append("pls:line_created")
    if telemetry and int(telemetry.get("points_created") or 0) <= 0 and int(telemetry.get("lines_created") or 0) <= 0:
        labels.append("pls:no_point_line")
    if not telemetry:
        labels.append("pls:missing")

    freshness = record.get("state_freshness") if isinstance(record.get("state_freshness"), dict) else {}
    if freshness.get("state_stale") is True:
        labels.append("state:stale")
    elif freshness:
        labels.append("state:fresh_or_unflagged")
    else:
        labels.append("state:missing_freshness")
    return labels


def pollution_flags(record: dict[str, Any]) -> list[str]:
    flags = []
    if record.get("progress_class") == "strong" and record.get("outcome_detected") is not True:
        flags.append("strong_is_activity_proxy_not_success")
    if record.get("kb_changed") is True:
        flags.append("kb_changed_not_semantic_ground_truth")
    if record.get("status") == "completed":
        flags.append("completed_not_task_success_ground_truth")
    if not isinstance(record.get("outcome_detected"), bool):
        flags.append("missing_or_legacy_outcome_detected")
    if not isinstance(record.get("pls_telemetry"), dict):
        flags.append("missing_pls_telemetry")
    if not isinstance(record.get("round_topology"), dict):
        flags.append("missing_round_topology")
    freshness = record.get("state_freshness") if isinstance(record.get("state_freshness"), dict) else {}
    if freshness.get("state_stale") is True:
        flags.append("state_stale")
    if record.get("status") in {"timeout", "exception", "interrupted"}:
        flags.append("incomplete_round")
    if int(record.get("reanchor_streak") or 0) >= 2:
        flags.append("reanchor_loop")
    flags.extend(flag for flag in semantic_risk_flags(record) if flag not in flags)
    return flags


def field_present(record: dict[str, Any], field: str) -> bool:
    value = record.get(field)
    if value is None:
        return False
    if isinstance(value, (dict, list, str)):
        return bool(value)
    return True


def nested_present(record: dict[str, Any], path: list[str]) -> bool:
    value: Any = record
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return False
        value = value[key]
    if value is None:
        return False
    if isinstance(value, (dict, list, str)):
        return bool(value)
    return True


def coverage_stat(records: list[dict[str, Any]], name: str, predicate) -> dict[str, Any]:
    present = sum(1 for record in records if predicate(record))
    return {"present": present, "total": len(records), "ratio": safe_ratio(present, len(records))}


def build_coverage(records: list[dict[str, Any]]) -> dict[str, Any]:
    fields = {
        "knowledge_state": coverage_stat(records, "knowledge_state", lambda r: field_present(r, "knowledge_state")),
        "frontier_state": coverage_stat(records, "frontier_state", lambda r: field_present(r, "frontier_state")),
        "events": coverage_stat(records, "events", lambda r: field_present(r, "events")),
        "phase_trace": coverage_stat(records, "phase_trace", lambda r: field_present(r, "phase_trace")),
        "current_state_preview": coverage_stat(records, "current_state_preview", lambda r: nested_present(r, ["phase_trace", "current_state_preview"])),
        "active_nodes_roles": coverage_stat(records, "active_nodes_roles", lambda r: nested_present(r, ["phase_trace", "current_state_preview", "active_nodes"])),
        "progress_class": coverage_stat(records, "progress_class", lambda r: field_present(r, "progress_class")),
        "outcome_detected_bool": coverage_stat(records, "outcome_detected_bool", lambda r: isinstance(r.get("outcome_detected"), bool)),
        "kb_delta": coverage_stat(records, "kb_delta", lambda r: field_present(r, "kb_delta")),
        "pls_telemetry": coverage_stat(records, "pls_telemetry", lambda r: isinstance(r.get("pls_telemetry"), dict)),
        "round_topology": coverage_stat(records, "round_topology", lambda r: isinstance(r.get("round_topology"), dict)),
        "state_freshness": coverage_stat(records, "state_freshness", lambda r: isinstance(r.get("state_freshness"), dict)),
    }
    groups = {
        "state": min(fields[name]["ratio"] for name in ["knowledge_state", "frontier_state", "phase_trace"]),
        "action": min(fields[name]["ratio"] for name in ["events", "round_topology"]),
        "outcome": min(fields[name]["ratio"] for name in ["progress_class", "outcome_detected_bool", "kb_delta"]),
        "connection": min(fields[name]["ratio"] for name in ["pls_telemetry", "round_topology"]),
    } if records else {"state": 0.0, "action": 0.0, "outcome": 0.0, "connection": 0.0}
    return {"fields": fields, "group_minimums": groups}


def round_field_presence(record: dict[str, Any]) -> dict[str, bool]:
    return {
        "knowledge_state": field_present(record, "knowledge_state"),
        "frontier_state": field_present(record, "frontier_state"),
        "events": field_present(record, "events"),
        "phase_trace": field_present(record, "phase_trace"),
        "current_state_preview": nested_present(record, ["phase_trace", "current_state_preview"]),
        "active_nodes_roles": nested_present(record, ["phase_trace", "current_state_preview", "active_nodes"]),
        "progress_class": field_present(record, "progress_class"),
        "outcome_detected_bool": isinstance(record.get("outcome_detected"), bool),
        "kb_delta": field_present(record, "kb_delta"),
        "pls_telemetry": isinstance(record.get("pls_telemetry"), dict),
        "round_topology": isinstance(record.get("round_topology"), dict),
        "state_freshness": isinstance(record.get("state_freshness"), dict),
    }


def round_schema_profile(record: dict[str, Any]) -> dict[str, Any]:
    fields = round_field_presence(record)
    groups = {}
    missing = {}
    for group, required_fields in SAO_FIELD_GROUPS.items():
        missing_fields = [field for field in required_fields if not fields.get(field)]
        groups[group] = not missing_fields
        missing[group] = missing_fields
    stable = all(groups.values())
    return {
        "schema": "genesis.v6.sao_round_schema_profile.v1",
        "stable": stable,
        "groups": groups,
        "missing": missing,
        "field_presence": fields,
    }


def build_schema_stability(records: list[dict[str, Any]], top_limit: int, sample_limit: int) -> dict[str, Any]:
    stable_records = []
    legacy_records = []
    session_totals: Counter[str] = Counter()
    session_stable: Counter[str] = Counter()
    session_latest_path: dict[str, str] = {}
    missing_counter: Counter[str] = Counter()
    for record in records:
        session_id = str(record.get("session_id") or Path(str(record.get("_path") or "")).parent.name or "unknown")
        session_totals[session_id] += 1
        if record.get("_path"):
            session_latest_path.setdefault(session_id, str(record.get("_path")))
        profile = round_schema_profile(record)
        for group, missing_fields in profile["missing"].items():
            for field in missing_fields:
                missing_counter[f"{group}:{field}"] += 1
        if profile["stable"]:
            session_stable[session_id] += 1
            stable_records.append((record, profile))
        else:
            legacy_records.append((record, profile))
    candidate_sessions = []
    for session_id, total in session_totals.items():
        stable_count = session_stable[session_id]
        if stable_count <= 0:
            continue
        candidate_sessions.append({
            "session_id": session_id,
            "stable_rounds": stable_count,
            "total_rounds": total,
            "stable_ratio": safe_ratio(stable_count, total),
            "latest_round_path": session_latest_path.get(session_id, ""),
        })
    candidate_sessions.sort(key=lambda item: (item["stable_rounds"], item["stable_ratio"]), reverse=True)
    return {
        "schema": "genesis.v6.sao_schema_stability.v1",
        "stable_rounds": len(stable_records),
        "legacy_or_incomplete_rounds": len(legacy_records),
        "total_rounds": len(records),
        "stable_ratio": safe_ratio(len(stable_records), len(records)),
        "top_missing_requirements": top_items(missing_counter, top_limit),
        "candidate_sessions": candidate_sessions[:top_limit],
        "stable_samples": [
            {
                "path": record.get("_path"),
                "session_id": record.get("session_id"),
                "round": record.get("round"),
                "route_family": classify_route_family(record),
                "weak_outcome_labels": weak_outcome_labels(record),
                "pollution_flags": pollution_flags(record),
            }
            for record, _ in stable_records[:sample_limit]
        ],
    }


def training_readiness(record: dict[str, Any]) -> dict[str, Any]:
    profile = round_schema_profile(record)
    flags = pollution_flags(record)
    exclusion_reasons = []
    review_reasons = []
    if not profile["stable"]:
        exclusion_reasons.append("schema_not_stable")
    if record.get("status") != "completed":
        exclusion_reasons.append("round_not_completed")
    if "missing_or_legacy_outcome_detected" in flags:
        exclusion_reasons.append("missing_outcome_detected")
    if "missing_pls_telemetry" in flags or "missing_round_topology" in flags:
        exclusion_reasons.append("missing_connection_or_topology")
    if "arena_collective_attribution_risk" in flags:
        review_reasons.append("per_node_credit_requires_attribution_audit")
    if "env_fact_state_risk" in flags:
        review_reasons.append("environment_state_requires_freshness_check")
    if "contradiction_conflict_risk" in flags:
        review_reasons.append("conflict_sensitive_sample_requires_contradiction_flag")
    route_policy_candidate = not exclusion_reasons
    per_node_credit_candidate = (
        route_policy_candidate
        and "arena_collective_attribution_risk" not in flags
        and "contradiction_conflict_risk" not in flags
    )
    return {
        "schema": "genesis.v6.sao_training_readiness.v1",
        "schema_stable": profile["stable"],
        "route_policy_candidate": route_policy_candidate,
        "per_node_credit_candidate": per_node_credit_candidate,
        "review_required": bool(review_reasons),
        "exclusion_reasons": exclusion_reasons,
        "review_reasons": review_reasons,
        "pollution_flags": flags,
    }


def build_training_readiness(records: list[dict[str, Any]], top_limit: int) -> dict[str, Any]:
    exclusion_counter: Counter[str] = Counter()
    review_counter: Counter[str] = Counter()
    flag_counter: Counter[str] = Counter()
    route_policy_candidates = 0
    per_node_credit_candidates = 0
    review_required = 0
    for record in records:
        readiness = training_readiness(record)
        if readiness["route_policy_candidate"]:
            route_policy_candidates += 1
        if readiness["per_node_credit_candidate"]:
            per_node_credit_candidates += 1
        if readiness["review_required"]:
            review_required += 1
        exclusion_counter.update(readiness["exclusion_reasons"])
        review_counter.update(readiness["review_reasons"])
        flag_counter.update(readiness["pollution_flags"])
    return {
        "schema": "genesis.v6.sao_training_readiness_summary.v1",
        "total_rounds": len(records),
        "route_policy_candidates": route_policy_candidates,
        "route_policy_candidate_ratio": safe_ratio(route_policy_candidates, len(records)),
        "per_node_credit_candidates": per_node_credit_candidates,
        "per_node_credit_candidate_ratio": safe_ratio(per_node_credit_candidates, len(records)),
        "review_required": review_required,
        "review_required_ratio": safe_ratio(review_required, len(records)),
        "top_exclusion_reasons": top_items(exclusion_counter, top_limit),
        "top_review_reasons": top_items(review_counter, top_limit),
        "top_pollution_flags": top_items(flag_counter, top_limit),
    }


def audit_traces_db(path: Path) -> dict[str, Any]:
    result = {"path": str(path), "available": False, "error": None}
    if not path.exists():
        result["error"] = "traces db not found"
        return result
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        result["available"] = True
        result["trace_count"] = conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
        result["span_count"] = conn.execute("SELECT COUNT(*) FROM spans").fetchone()[0]
        result["tool_span_count"] = conn.execute("SELECT COUNT(*) FROM spans WHERE span_type = 'tool_call'").fetchone()[0]
        result["nonempty_tool_label_count"] = conn.execute("SELECT COUNT(*) FROM spans WHERE span_type = 'tool_call' AND tool_name IS NOT NULL AND TRIM(tool_name) != ''").fetchone()[0]
        result["error_span_count"] = conn.execute("SELECT COUNT(*) FROM spans WHERE error IS NOT NULL AND TRIM(error) != ''").fetchone()[0]
        result["tool_label_nonempty_ratio"] = safe_ratio(result["nonempty_tool_label_count"], result["tool_span_count"])
        result["error_span_ratio"] = safe_ratio(result["error_span_count"], result["span_count"])
    except Exception as exc:
        result["available"] = False
        result["error"] = str(exc)[:200]
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return result


def audit_shadow_log(path: Path) -> dict[str, Any]:
    result = {"path": str(path), "available": False, "records": 0, "fields": []}
    if not path.exists():
        return result
    fields = Counter()
    records = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            if not isinstance(record, dict):
                continue
            records += 1
            for field in record.get("fields") or []:
                fields[str(field)] += 1
    result["available"] = True
    result["records"] = records
    result["fields"] = top_items(fields, 20)
    return result


def sample_rounds(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    samples = []
    for record in records[:limit]:
        samples.append({
            "path": record.get("_path"),
            "session_id": record.get("session_id"),
            "round": record.get("round"),
            "status": record.get("status"),
            "progress_class": record.get("progress_class"),
            "schema_profile": round_schema_profile(record),
            "training_readiness": training_readiness(record),
            "route_family": classify_route_family(record),
            "weak_outcome_labels": weak_outcome_labels(record),
            "pollution_flags": pollution_flags(record),
        })
    return samples


def build_report(
    auto_reports_dir: Path = DEFAULT_AUTO_REPORTS_DIR,
    traces_db: Path = DEFAULT_TRACES_DB,
    shadow_log: Path = DEFAULT_SHADOW_LOG,
    max_rounds: int = 0,
    top_limit: int = 20,
    sample_limit: int = 5,
) -> dict[str, Any]:
    records = load_round_records(auto_reports_dir, max_rounds=max_rounds)
    route_counter: Counter[str] = Counter()
    outcome_counter: Counter[str] = Counter()
    pollution_counter: Counter[str] = Counter()
    for record in records:
        route_counter[classify_route_family(record)] += 1
        outcome_counter.update(weak_outcome_labels(record))
        pollution_counter.update(pollution_flags(record))
    decision = "NO_ROUNDS_AVAILABLE"
    if records:
        coverage = build_coverage(records)
        schema_stability = build_schema_stability(records, top_limit=top_limit, sample_limit=sample_limit)
        if schema_stability["stable_rounds"] > 0 and coverage["group_minimums"]["state"] >= 0.5 and coverage["group_minimums"]["outcome"] >= 0.5:
            decision = "PROCEED_TO_OFFLINE_SAO_CANONICALIZER"
        else:
            decision = "COLLECT_MORE_SCHEMA_STABLE_ROUNDS"
    else:
        coverage = build_coverage(records)
        schema_stability = build_schema_stability(records, top_limit=top_limit, sample_limit=sample_limit)
    return {
        "schema": "genesis.v6.sao_distillability_report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only_audit",
        "decision": decision,
        "source": {
            "auto_reports_dir": str(auto_reports_dir),
            "traces_db": str(traces_db),
            "shadow_log": str(shadow_log),
            "max_rounds": max_rounds,
        },
        "rounds": {
            "total_loaded": len(records),
            "coverage": coverage,
            "schema_stability": schema_stability,
            "training_readiness": build_training_readiness(records, top_limit),
            "route_families": top_items(route_counter, top_limit),
            "weak_outcome_labels": top_items(outcome_counter, top_limit),
            "pollution_flags": top_items(pollution_counter, top_limit),
            "samples": sample_rounds(records, sample_limit),
        },
        "traces_db": audit_traces_db(traces_db),
        "shadow_log": audit_shadow_log(shadow_log),
        "constraints": [
            "do_not_train_route_model_from_this_report_alone",
            "do_not_collapse_weak_outcomes_into_one_score",
            "do_not_use_arena_usage_as_per_node_ground_truth",
            "do_not_change_runtime_surface_or_prompt_from_this_audit",
        ],
        "next_step": "Use this report to design a stable S-A-O canonicalizer and route family vocabulary before any runtime change.",
    }


def render_text(report: dict[str, Any]) -> str:
    rounds = report.get("rounds") or {}
    coverage = (rounds.get("coverage") or {}).get("group_minimums") or {}
    lines = [
        "=== Genesis V6 S-A-O Distillability Audit ===",
        f"mode: {report.get('mode')}",
        f"decision: {report.get('decision')}",
        f"rounds_loaded: {rounds.get('total_loaded', 0)}",
        "coverage_group_minimums:",
    ]
    for key in ["state", "action", "outcome", "connection"]:
        lines.append(f"  {key}: {coverage.get(key, 0.0)}")
    stability = rounds.get("schema_stability") or {}
    lines.append("schema_stability:")
    lines.append(f"  stable_rounds: {stability.get('stable_rounds', 0)}")
    lines.append(f"  stable_ratio: {stability.get('stable_ratio', 0.0)}")
    readiness = rounds.get("training_readiness") or {}
    lines.append("training_readiness:")
    lines.append(f"  route_policy_candidates: {readiness.get('route_policy_candidates', 0)}")
    lines.append(f"  per_node_credit_candidates: {readiness.get('per_node_credit_candidates', 0)}")
    lines.append(f"  review_required: {readiness.get('review_required', 0)}")
    lines.append("route_families:")
    for item in rounds.get("route_families") or []:
        lines.append(f"  {item['value']}: {item['count']}")
    lines.append("pollution_flags:")
    for item in rounds.get("pollution_flags") or []:
        lines.append(f"  {item['value']}: {item['count']}")
    lines.append("constraints:")
    for item in report.get("constraints") or []:
        lines.append(f"  - {item}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only S-A-O distillability audit for Genesis V6")
    parser.add_argument("--auto-reports-dir", default=str(DEFAULT_AUTO_REPORTS_DIR))
    parser.add_argument("--traces-db", default=str(DEFAULT_TRACES_DB))
    parser.add_argument("--shadow-log", default=str(DEFAULT_SHADOW_LOG))
    parser.add_argument("--output", default="")
    parser.add_argument("--max-rounds", type=int, default=0)
    parser.add_argument("--top-limit", type=int, default=20)
    parser.add_argument("--sample-limit", type=int, default=5)
    parser.add_argument("--format", choices={"text", "json"}, default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        auto_reports_dir=Path(args.auto_reports_dir).expanduser(),
        traces_db=Path(args.traces_db).expanduser(),
        shadow_log=Path(args.shadow_log).expanduser(),
        max_rounds=max(0, args.max_rounds),
        top_limit=max(1, args.top_limit),
        sample_limit=max(0, args.sample_limit),
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
