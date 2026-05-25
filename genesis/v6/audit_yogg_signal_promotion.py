from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTO_REPORTS_DIR = PROJECT_ROOT / "runtime" / "auto_reports"
DEFAULT_NODEVAULT_DB = Path.home() / ".genesis" / "workshop_v4.sqlite"
DEFAULT_OUTPUT = PROJECT_ROOT / "runtime" / "yogg_signal_promotion_queue.json"
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
LINE_DELTA_KEYS = {"lines", "edges", "reasoning_lines", "node_edges", "line_delta", "graph_delta"}
LINE_RESULT_RE = re.compile(r":\s*([^\s]+)\s+--\[based_on\]-->\s*([^\s]+)")
NON_ACTIONS = [
    "modify NodeVault",
    "change confidence",
    "promote epistemic_status",
    "restart services",
    "apply patches",
    "change C-Phase behavior",
    "clear rollback/canary markers",
    "train models",
]


class PromotionAuditError(RuntimeError):
    pass


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


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise PromotionAuditError(f"database not found: {path}")
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int | float | str | None:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def top_items(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def queue_shell() -> dict[str, list[dict[str, Any]]]:
    return {state: [] for state in GOVERNANCE_STATES}


def add_queue_item(queues: dict[str, list[dict[str, Any]]], state: str, item: dict[str, Any]) -> None:
    if state not in queues:
        raise PromotionAuditError(f"unknown governance state: {state}")
    normalized = {
        "signal_id": item.get("signal_id", ""),
        "signal_type": item.get("signal_type", ""),
        "source_refs": item.get("source_refs", []),
        "claim": item.get("claim", ""),
        "evidence_refs": item.get("evidence_refs", []),
        "verification_method": item.get("verification_method", ""),
        "governance_state": state,
        "promotion_target": item.get("promotion_target", ""),
        "consumer_decision": item.get("consumer_decision", ""),
        "non_actions": item.get("non_actions", NON_ACTIONS),
    }
    queues[state].append(normalized)


def record_path(record: dict[str, Any]) -> str:
    return str(record.get("_path") or f"session={record.get('session_id')} round={record.get('round')}")


def event_result_counts(records: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for record in records:
        for event in record.get("events") or []:
            if not isinstance(event, dict):
                continue
            if event.get("type") != "tool_result":
                continue
            name = str(event.get("name") or "")
            result = str(event.get("result_preview") or "")
            if name == "record_line":
                if result.startswith("✅ LINE"):
                    counts["record_line_success"] += 1
                elif result.startswith("ℹ️ LINE"):
                    counts["record_line_existing"] += 1
                elif result.startswith("Error:"):
                    counts["record_line_error"] += 1
            if "sudo systemctl restart" in result or "systemctl restart yogg-auto.service" in result:
                counts["privileged_restart_result"] += 1
    return counts


def parse_line_result(result: str) -> tuple[str, str] | None:
    match = LINE_RESULT_RE.search(result)
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def successful_line_pairs(records: list[dict[str, Any]], sample_limit: int) -> tuple[list[dict[str, str]], set[str]]:
    samples = []
    new_point_ids = set()
    for record in records:
        for event in record.get("events") or []:
            if not isinstance(event, dict):
                continue
            if event.get("type") != "tool_result" or event.get("name") != "record_line":
                continue
            result = str(event.get("result_preview") or "")
            if not result.startswith("✅ LINE"):
                continue
            parsed = parse_line_result(result)
            if not parsed:
                continue
            new_point_id, basis_point_id = parsed
            new_point_ids.add(new_point_id)
            if len(samples) < sample_limit:
                samples.append({
                    "path": record_path(record),
                    "new_point_id": new_point_id,
                    "basis_point_id": basis_point_id,
                })
    return samples, new_point_ids


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
            nid = item.get("node_id") or item.get("id")
        else:
            nid = item
        if nid:
            ids.add(str(nid))
    return ids


def active_context_line_hits(records: list[dict[str, Any]], line_node_ids: set[str], sample_limit: int) -> list[dict[str, str]]:
    if not line_node_ids:
        return []
    samples = []
    seen = set()
    for record in records:
        for node_id in sorted(active_node_ids(record) & line_node_ids):
            key = (record_path(record), node_id)
            if key in seen:
                continue
            seen.add(key)
            samples.append({"path": record_path(record), "node_id": node_id})
            if len(samples) >= sample_limit:
                return samples
    return samples


def summarize_records(records: list[dict[str, Any]], sample_limit: int) -> dict[str, Any]:
    progress_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    outcome_counter: Counter[str] = Counter()
    kb_delta_key_counter: Counter[str] = Counter()
    kb_delta_key_sets: Counter[str] = Counter()
    line_round_paths = []
    activity_without_outcome_paths = []
    raw_activity_only_paths = []
    knowledge_without_physical_paths = []
    no_domain_outcome_paths = []
    kb_delta_has_line_fields = False
    totals = Counter()
    outcome_domain_counter: Counter[str] = Counter()
    line_pair_samples, line_new_point_ids = successful_line_pairs(records, sample_limit)
    active_line_hit_samples = active_context_line_hits(records, line_new_point_ids, sample_limit)
    for record in records:
        progress = str(record.get("progress_class") or "unknown")
        status = str(record.get("status") or "unknown")
        progress_counter[progress] += 1
        status_counter[status] += 1
        if record.get("outcome_detected") is True:
            outcome_counter["sandbox_diff_changed"] += 1
        elif record.get("outcome_detected") is False:
            outcome_counter["no_sandbox_diff"] += 1
        else:
            outcome_counter["missing_or_legacy"] += 1
        telemetry = record.get("pls_telemetry") if isinstance(record.get("pls_telemetry"), dict) else {}
        lines_created = int_value(telemetry.get("lines_created"))
        cross_round_lines = int_value(telemetry.get("cross_round_lines"))
        line_errors = int_value(telemetry.get("line_errors"))
        points_created = int_value(telemetry.get("points_created"))
        totals["lines_created"] += lines_created
        totals["cross_round_lines"] += cross_round_lines
        totals["line_errors"] += line_errors
        totals["points_created"] += points_created
        if lines_created > 0 and len(line_round_paths) < sample_limit:
            line_round_paths.append(record_path(record))
        kb_delta = record.get("kb_delta") if isinstance(record.get("kb_delta"), dict) else {}
        new_nodes = list_count(kb_delta.get("new_nodes"))
        updated_nodes = list_count(kb_delta.get("updated_nodes"))
        totals["kb_new_nodes"] += new_nodes
        totals["kb_updated_nodes"] += updated_nodes
        key_set = tuple(sorted(str(key) for key in kb_delta.keys()))
        kb_delta_key_sets[",".join(key_set)] += 1
        for key in key_set:
            kb_delta_key_counter[key] += 1
            if key in LINE_DELTA_KEYS:
                kb_delta_has_line_fields = True
        activity_like = progress in {"strong", "soft", "evidence"}
        physical_outcome = record.get("outcome_detected") is True
        knowledge_outcome = bool(record.get("kb_changed")) or new_nodes > 0 or updated_nodes > 0 or points_created > 0
        line_outcome = lines_created > 0 or cross_round_lines > 0
        if physical_outcome:
            outcome_domain_counter["physical_outcome"] += 1
        if knowledge_outcome:
            outcome_domain_counter["knowledge_outcome"] += 1
        if line_outcome:
            outcome_domain_counter["line_activity_evidence"] += 1
        if knowledge_outcome and not physical_outcome and len(knowledge_without_physical_paths) < sample_limit:
            knowledge_without_physical_paths.append(record_path(record))
        if not physical_outcome and not knowledge_outcome and not line_outcome and len(no_domain_outcome_paths) < sample_limit:
            no_domain_outcome_paths.append(record_path(record))
        if activity_like and record.get("outcome_detected") is False:
            if len(activity_without_outcome_paths) < sample_limit:
                activity_without_outcome_paths.append(record_path(record))
            if not record.get("kb_changed") and lines_created <= 0 and int_value(telemetry.get("points_created")) <= 0:
                if len(raw_activity_only_paths) < sample_limit:
                    raw_activity_only_paths.append(record_path(record))
    event_counts = event_result_counts(records)
    return {
        "total_rounds": len(records),
        "progress_class_distribution": top_items(progress_counter, 12),
        "status_distribution": top_items(status_counter, 12),
        "weak_outcome_distribution": top_items(outcome_counter, 12),
        "kb_delta_key_distribution": top_items(kb_delta_key_counter, 12),
        "kb_delta_key_sets": top_items(kb_delta_key_sets, 12),
        "kb_delta_has_line_fields": kb_delta_has_line_fields,
        "line_round_paths": line_round_paths,
        "activity_without_outcome_paths": activity_without_outcome_paths,
        "raw_activity_only_paths": raw_activity_only_paths,
        "knowledge_without_physical_paths": knowledge_without_physical_paths,
        "no_domain_outcome_paths": no_domain_outcome_paths,
        "outcome_domain_distribution": top_items(outcome_domain_counter, 12),
        "line_pair_samples": line_pair_samples,
        "line_new_point_id_count": len(line_new_point_ids),
        "active_context_line_hit_samples": active_line_hit_samples,
        "active_context_line_hit_count": len(active_line_hit_samples),
        "totals": dict(totals),
        "event_counts": dict(event_counts),
    }


def audit_nodevault_db(path: Path, created_since: str = "") -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "path": str(path), "error": "database_not_found"}
    try:
        conn = connect_readonly(path)
    except Exception as exc:
        return {"available": False, "path": str(path), "error": str(exc)}
    try:
        result: dict[str, Any] = {"available": True, "path": str(path), "counts": {}, "created_since": created_since or None}
        for table in ["knowledge_nodes", "node_content", "node_edges", "reasoning_lines"]:
            if table_exists(conn, table):
                result["counts"][table] = int_value(scalar(conn, f"SELECT COUNT(*) FROM {table}"))
                if created_since:
                    try:
                        result["counts"][f"{table}_created_since"] = int_value(scalar(conn, f"SELECT COUNT(*) FROM {table} WHERE created_at >= ?", (created_since,)))
                    except Exception:
                        pass
        if table_exists(conn, "node_edges"):
            rows = conn.execute("SELECT relation, COUNT(*) AS c FROM node_edges GROUP BY relation ORDER BY c DESC LIMIT 12").fetchall()
            result["node_edge_relations"] = [{"value": str(row["relation"]), "count": int(row["c"])} for row in rows]
        if table_exists(conn, "reasoning_lines"):
            where = ""
            params: tuple[Any, ...] = ()
            if created_since:
                where = "WHERE rl.created_at >= ?"
                params = (created_since,)
            consumed_sql = f"""
                SELECT COUNT(*)
                FROM reasoning_lines rl
                {where}
                AND EXISTS (
                    SELECT 1
                    FROM reasoning_lines later
                    WHERE later.basis_point_id = rl.new_point_id
                      AND later.line_id != rl.line_id
                      AND datetime(later.created_at) >= datetime(rl.created_at)
                )
            """ if where else """
                SELECT COUNT(*)
                FROM reasoning_lines rl
                WHERE EXISTS (
                    SELECT 1
                    FROM reasoning_lines later
                    WHERE later.basis_point_id = rl.new_point_id
                      AND later.line_id != rl.line_id
                      AND datetime(later.created_at) >= datetime(rl.created_at)
                )
            """
            total_sql = "SELECT COUNT(*) FROM reasoning_lines"
            total_params: tuple[Any, ...] = ()
            if created_since:
                total_sql += " WHERE created_at >= ?"
                total_params = (created_since,)
            total_lines = int_value(scalar(conn, total_sql, total_params))
            consumed_lines = int_value(scalar(conn, consumed_sql, params))
            sample_sql = f"""
                SELECT rl.created_at, rl.new_point_id, rl.basis_point_id,
                       later.created_at AS consumed_at, later.new_point_id AS consuming_new_point_id
                FROM reasoning_lines rl
                JOIN reasoning_lines later ON later.basis_point_id = rl.new_point_id
                {"WHERE rl.created_at >= ?" if created_since else "WHERE 1=1"}
                  AND later.line_id != rl.line_id
                  AND datetime(later.created_at) >= datetime(rl.created_at)
                ORDER BY later.created_at DESC
                LIMIT 8
            """
            samples = conn.execute(sample_sql, params).fetchall()
            result["line_consumption"] = {
                "reasoning_lines_total": total_lines,
                "consumed_as_basis": consumed_lines,
                "unconsumed_or_unproven": max(0, total_lines - consumed_lines),
                "consumption_samples": [dict(row) for row in samples],
            }
        return result
    finally:
        conn.close()


def read_text_snapshot(path: Path | None) -> dict[str, Any]:
    if not path:
        return {"available": False, "path": None, "text": ""}
    if not path.exists():
        return {"available": False, "path": str(path), "text": "", "error": "file_not_found"}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {"available": False, "path": str(path), "text": "", "error": str(exc)}
    return {"available": True, "path": str(path), "text": text}


def constraint_surface_audit(service_snapshot: dict[str, Any], sudo_snapshot: dict[str, Any]) -> dict[str, Any]:
    service_text = str(service_snapshot.get("text") or "")
    sudo_text = str(sudo_snapshot.get("text") or "")
    signals = {
        "service_snapshot_available": bool(service_snapshot.get("available")),
        "sudo_snapshot_available": bool(sudo_snapshot.get("available")),
        "service_user_declared": "User=" in service_text,
        "service_memory_limit_declared": "MemoryMax=" in service_text or "MemoryHigh=" in service_text,
        "service_restart_declared": "Restart=" in service_text,
        "broad_sudo_detected": "NOPASSWD: ALL" in sudo_text or "(ALL) NOPASSWD: ALL" in sudo_text or "(ALL : ALL) ALL" in sudo_text,
        "bounded_service_restart_sudo_detected": "systemctl restart yogg-auto.service" in sudo_text and "NOPASSWD: ALL" not in sudo_text,
    }
    declared = signals["service_user_declared"] or signals["service_memory_limit_declared"] or signals["service_restart_declared"]
    bypassable = signals["broad_sudo_detected"]
    audit_available = signals["service_snapshot_available"] or signals["sudo_snapshot_available"]
    if bypassable:
        risk_level = "high"
    elif declared and audit_available:
        risk_level = "medium"
    else:
        risk_level = "unknown"
    return {
        "signals": signals,
        "declared_constraint_surface": declared,
        "audit_available": audit_available,
        "bypassable_private_channel": bypassable,
        "risk_level": risk_level,
    }


def build_queues(record_summary: dict[str, Any], nodevault: dict[str, Any], service_snapshot: dict[str, Any], sudo_snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    queues = queue_shell()
    total_rounds = int_value(record_summary.get("total_rounds"))
    totals = record_summary.get("totals") if isinstance(record_summary.get("totals"), dict) else {}
    event_counts = record_summary.get("event_counts") if isinstance(record_summary.get("event_counts"), dict) else {}
    if total_rounds > 0:
        add_queue_item(queues, "observed", {
            "signal_id": "round_reports_loaded",
            "signal_type": "activity_signal",
            "source_refs": ["auto_reports round JSON"],
            "claim": f"Loaded {total_rounds} Yogg round reports for signal screening.",
            "evidence_refs": ["record_summary.total_rounds"],
            "verification_method": "Count parsed round_*.json files without writing runtime state.",
            "promotion_target": "screening_input",
            "consumer_decision": "accept_as_observed_input",
        })
    if record_summary.get("raw_activity_only_paths"):
        add_queue_item(queues, "ignored", {
            "signal_id": "raw_progress_class_activity_only",
            "signal_type": "activity_signal",
            "source_refs": record_summary.get("raw_activity_only_paths", []),
            "claim": "Some strong/soft/evidence progress_class rounds have no sandbox outcome, KB change, point, or line signal.",
            "evidence_refs": ["progress_class", "outcome_detected", "kb_changed", "pls_telemetry"],
            "verification_method": "Inspect report fields only; do not treat progress_class alone as outcome.",
            "promotion_target": "none",
            "consumer_decision": "ignore_raw_activity_without_evidence_path",
        })
    if record_summary.get("activity_without_outcome_paths"):
        add_queue_item(queues, "candidate", {
            "signal_id": "activity_signal_promotion_candidates",
            "signal_type": "activity_signal",
            "source_refs": record_summary.get("activity_without_outcome_paths", []),
            "claim": "Some activity-positive rounds lack sandbox outcome and require review before any outcome claim.",
            "evidence_refs": ["progress_class", "outcome_detected", "kb_changed", "pls_telemetry", "events"],
            "verification_method": "Review sampled reports and require concrete evidence refs before promotion.",
            "promotion_target": "ActivitySignalPromotionGate",
            "consumer_decision": "queue_for_review_not_runtime_change",
        })
    if record_summary.get("knowledge_without_physical_paths"):
        add_queue_item(queues, "needs_resolution", {
            "signal_id": "knowledge_outcome_without_physical_outcome",
            "signal_type": "governance_signal",
            "source_refs": record_summary.get("knowledge_without_physical_paths", []),
            "claim": "Some rounds changed knowledge-domain signals while sandbox physical outcome remained false.",
            "evidence_refs": ["outcome_detected", "kb_changed", "kb_delta", "pls_telemetry.points_created"],
            "verification_method": "Compare physical_outcome with knowledge_outcome fields in round reports.",
            "promotion_target": "multi-domain outcome contract",
            "consumer_decision": "separate_outcome_domains_before_runtime_behavior",
        })
    if record_summary.get("no_domain_outcome_paths"):
        add_queue_item(queues, "ignored", {
            "signal_id": "no_observed_outcome_domain",
            "signal_type": "activity_signal",
            "source_refs": record_summary.get("no_domain_outcome_paths", []),
            "claim": "Some rounds have no physical, knowledge, or line-domain evidence in audited fields.",
            "evidence_refs": ["outcome_detected", "kb_changed", "kb_delta", "pls_telemetry"],
            "verification_method": "Require a concrete domain before promotion.",
            "promotion_target": "none",
            "consumer_decision": "ignore_until_domain_evidence_exists",
        })
    if int_value(totals.get("lines_created")) > 0:
        add_queue_item(queues, "needs_verification", {
            "signal_id": "reasoning_line_activity_visible",
            "signal_type": "evidence_signal",
            "source_refs": record_summary.get("line_round_paths", []),
            "claim": "PLS Line activity is visible in telemetry/events and can enter line outcome review.",
            "evidence_refs": ["pls_telemetry.lines_created", "events.record_line", "NodeVault.reasoning_lines"],
            "verification_method": "Compare report line counters with read-only NodeVault reasoning_lines counts.",
            "promotion_target": "PLS Line Outcome Schema review",
            "consumer_decision": "verify_line_consumption_before_outcome",
        })
    if int_value(totals.get("lines_created")) > 0 and not record_summary.get("kb_delta_has_line_fields"):
        add_queue_item(queues, "needs_resolution", {
            "signal_id": "kb_delta_node_only_line_gap",
            "signal_type": "governance_signal",
            "source_refs": record_summary.get("line_round_paths", []),
            "claim": "Round reports contain Line activity, but kb_delta has no line/edge fields.",
            "evidence_refs": ["kb_delta_key_distribution", "pls_telemetry.lines_created"],
            "verification_method": "Check kb_delta keys across loaded reports and compare with line telemetry.",
            "promotion_target": "line_delta / graph_delta contract",
            "consumer_decision": "define_consumer_before_runtime_fields",
        })
    if int_value(event_counts.get("record_line_error")) > 0 or int_value(totals.get("line_errors")) > 0:
        add_queue_item(queues, "needs_resolution", {
            "signal_id": "record_line_rejections_present",
            "signal_type": "governance_signal",
            "source_refs": record_summary.get("line_round_paths", []),
            "claim": "Some record_line attempts failed and should be separated from successful Line evidence.",
            "evidence_refs": ["events.record_line Error", "pls_telemetry.line_errors"],
            "verification_method": "Inspect record_line tool results and line_errors counters.",
            "promotion_target": "line_rejection_review",
            "consumer_decision": "do_not_count_rejected_lines_as_outcome",
        })
    counts = nodevault.get("counts") if isinstance(nodevault.get("counts"), dict) else {}
    line_consumption = nodevault.get("line_consumption") if isinstance(nodevault.get("line_consumption"), dict) else {}
    consumed_as_basis = int_value(line_consumption.get("consumed_as_basis"))
    unconsumed_or_unproven = int_value(line_consumption.get("unconsumed_or_unproven"))
    active_context_line_hit_count = int_value(record_summary.get("active_context_line_hit_count"))
    if int_value(counts.get("reasoning_lines")) > 0:
        add_queue_item(queues, "observed", {
            "signal_id": "nodevault_reasoning_lines_available",
            "signal_type": "evidence_signal",
            "source_refs": [str(nodevault.get("path"))],
            "claim": "NodeVault has reasoning_lines available for read-only comparison.",
            "evidence_refs": ["NodeVault.reasoning_lines count"],
            "verification_method": "Open SQLite with mode=ro and count reasoning_lines.",
            "promotion_target": "line_delta verification input",
            "consumer_decision": "accept_as_observed_input",
        })
    if consumed_as_basis > 0:
        add_queue_item(queues, "resolved", {
            "signal_id": "reasoning_line_consumed_as_later_basis",
            "signal_type": "evidence_signal",
            "source_refs": [str(nodevault.get("path"))],
            "claim": "Some reasoning_lines were later consumed as basis for newer reasoning lines.",
            "evidence_refs": ["NodeVault.reasoning_lines later.basis_point_id = earlier.new_point_id"],
            "verification_method": "Read-only self-join on reasoning_lines ordered by created_at.",
            "promotion_target": "line_promoted consumption evidence",
            "consumer_decision": "accept_as_consumed_evidence_not_runtime_action",
        })
    if active_context_line_hit_count > 0:
        add_queue_item(queues, "needs_verification", {
            "signal_id": "reasoning_line_node_selected_into_active_context",
            "signal_type": "evidence_signal",
            "source_refs": [sample.get("path", "") for sample in record_summary.get("active_context_line_hit_samples", [])],
            "claim": "Some nodes created by successful Line events appeared in active context, which is weak consumption evidence.",
            "evidence_refs": ["round.phase_trace.current_state_preview.active_nodes", "events.record_line"],
            "verification_method": "Compare successful record_line new_point_id values with active node ids, then review whether any later decision changed.",
            "promotion_target": "weak line consumption evidence review",
            "consumer_decision": "verify_before_treating_as_consumed_outcome",
        })
    if unconsumed_or_unproven > 0:
        add_queue_item(queues, "needs_verification", {
            "signal_id": "reasoning_lines_unconsumed_or_unproven",
            "signal_type": "evidence_signal",
            "source_refs": [str(nodevault.get("path"))],
            "claim": "Some reasoning_lines have no observed later-basis consumption in the audited NodeVault window.",
            "evidence_refs": ["NodeVault.reasoning_lines self-join absence"],
            "verification_method": "Read-only count of lines without later reasoning_lines using them as basis.",
            "promotion_target": "line consumption follow-up",
            "consumer_decision": "keep_as_evidence_until_consumption_observed",
        })
    service_text = str(service_snapshot.get("text") or "")
    sudo_text = str(sudo_snapshot.get("text") or "")
    constraint_audit = constraint_surface_audit(service_snapshot, sudo_snapshot)
    privileged_restart_observed = int_value(event_counts.get("privileged_restart_result")) > 0 or "systemctl restart yogg-auto.service" in service_text or "yogg-auto.service" in service_text
    broad_sudo = "NOPASSWD: ALL" in sudo_text or "(ALL) NOPASSWD: ALL" in sudo_text or "(ALL : ALL) ALL" in sudo_text
    if privileged_restart_observed or broad_sudo:
        add_queue_item(queues, "needs_human_review", {
            "signal_id": "privileged_promotion_review_required",
            "signal_type": "risk_signal",
            "source_refs": [ref for ref in [service_snapshot.get("path"), sudo_snapshot.get("path")] if ref],
            "claim": "Privileged restart or broad sudo scope requires explicit review before promotion semantics can be trusted.",
            "evidence_refs": ["service snapshot", "sudo snapshot", "recorded restart command"],
            "verification_method": "Read snapshots only; do not run sudo or restart services.",
            "promotion_target": "PrivilegedPromotionReview",
            "consumer_decision": "manual_review_required",
        })
    if constraint_audit["declared_constraint_surface"] or constraint_audit["bypassable_private_channel"]:
        state = "quarantined_candidate" if constraint_audit["bypassable_private_channel"] else "needs_verification"
        add_queue_item(queues, state, {
            "signal_id": "constraint_surface_private_bypass_audit",
            "signal_type": "risk_signal",
            "source_refs": [ref for ref in [service_snapshot.get("path"), sudo_snapshot.get("path")] if ref],
            "claim": "Declared service constraints require bypass analysis before they can be treated as real safety boundaries.",
            "evidence_refs": ["service User/Memory/Restart fields", "sudo scope snapshot"],
            "verification_method": "Read service and sudo snapshots without executing privileged commands.",
            "promotion_target": "ConstraintSurfaceReviewLine",
            "consumer_decision": "quarantine_if_broad_sudo_else_verify_enforcement",
        })
    return queues


def queue_counts(queues: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    return {state: len(items) for state, items in queues.items()}


def build_report(
    auto_reports_dir: Path = DEFAULT_AUTO_REPORTS_DIR,
    nodevault_db: Path = DEFAULT_NODEVAULT_DB,
    service_file: Path | None = None,
    sudo_snapshot: Path | None = None,
    max_rounds: int = 0,
    sample_limit: int = 5,
    created_since: str = "",
) -> dict[str, Any]:
    records = load_round_records(auto_reports_dir, max_rounds=max_rounds)
    record_summary = summarize_records(records, sample_limit=max(1, sample_limit))
    nodevault = audit_nodevault_db(nodevault_db, created_since=created_since)
    service = read_text_snapshot(service_file)
    sudo = read_text_snapshot(sudo_snapshot)
    constraint_audit = constraint_surface_audit(service, sudo)
    queues = build_queues(record_summary, nodevault, service, sudo)
    return {
        "schema": "genesis.v6.yogg_signal_promotion_queue.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only_audit",
        "dry_run": True,
        "governance_mode": "report_only",
        "consumer": "yogg_signal_promotion_queue",
        "source": {
            "auto_reports_dir": str(auto_reports_dir),
            "nodevault_db": str(nodevault_db),
            "service_file": str(service_file) if service_file else None,
            "sudo_snapshot": str(sudo_snapshot) if sudo_snapshot else None,
            "max_rounds": max_rounds,
            "created_since": created_since or None,
        },
        "rounds": record_summary,
        "nodevault": nodevault,
        "service_snapshot": {key: value for key, value in service.items() if key != "text"},
        "sudo_snapshot": {key: value for key, value in sudo.items() if key != "text"},
        "constraint_surface": constraint_audit,
        "queue_counts": queue_counts(queues),
        "queues": queues,
        "constraints": [
            "do_not_modify_nodevault",
            "do_not_change_confidence_or_epistemic_status",
            "do_not_restart_services",
            "do_not_apply_patches",
            "do_not_change_c_phase_behavior",
            "do_not_train_models_from_this_report",
            "do_not_treat_activity_as_outcome",
        ],
        "next_step": "Review queued candidates manually before implementing any runtime field or behavior change.",
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "=== Yogg Signal Promotion Queue ===",
        f"mode: {report.get('mode')}",
        f"dry_run: {report.get('dry_run')}",
        f"governance_mode: {report.get('governance_mode')}",
        f"consumer: {report.get('consumer')}",
        f"rounds_loaded: {(report.get('rounds') or {}).get('total_rounds', 0)}",
        "queue_counts:",
    ]
    for state in GOVERNANCE_STATES:
        lines.append(f"  {state}: {(report.get('queue_counts') or {}).get(state, 0)}")
    lines.append("queues:")
    queues = report.get("queues") if isinstance(report.get("queues"), dict) else {}
    for state in GOVERNANCE_STATES:
        items = queues.get(state) or []
        if not items:
            continue
        lines.append(f"  {state}:")
        for item in items[:5]:
            lines.append(f"    - {item.get('signal_id')}: {item.get('consumer_decision')}")
    lines.append("constraints:")
    for constraint in report.get("constraints") or []:
        lines.append(f"  - {constraint}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only Yogg signal promotion queue audit")
    parser.add_argument("--auto-reports-dir", default=str(DEFAULT_AUTO_REPORTS_DIR))
    parser.add_argument("--nodevault-db", default=str(DEFAULT_NODEVAULT_DB))
    parser.add_argument("--service-file", default="")
    parser.add_argument("--sudo-snapshot", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--max-rounds", type=int, default=0)
    parser.add_argument("--sample-limit", type=int, default=5)
    parser.add_argument("--created-since", default="")
    parser.add_argument("--format", choices={"text", "json"}, default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    service_file = Path(args.service_file).expanduser() if args.service_file else None
    sudo_snapshot = Path(args.sudo_snapshot).expanduser() if args.sudo_snapshot else None
    report = build_report(
        auto_reports_dir=Path(args.auto_reports_dir).expanduser(),
        nodevault_db=Path(args.nodevault_db).expanduser(),
        service_file=service_file,
        sudo_snapshot=sudo_snapshot,
        max_rounds=max(0, args.max_rounds),
        sample_limit=max(1, args.sample_limit),
        created_since=args.created_since,
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
