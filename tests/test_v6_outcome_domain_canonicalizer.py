from __future__ import annotations

import json
from pathlib import Path

from genesis.v6.canonicalize_outcome_domains import build_report, canonicalize_records, render_jsonl
from genesis.v6.audit_outcome_domain_compatibility import load_round_records


def write_round(root: Path, session: str, name: str, data: dict) -> Path:
    path = root / session / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def domain_row(rows: list[dict], domain: str) -> dict:
    matches = [row for row in rows if row["domain"] == domain]
    assert len(matches) == 1
    return matches[0]


def test_canonicalize_records_emits_one_row_per_domain_and_preserves_boundaries(tmp_path):
    auto_dir = tmp_path / "auto_reports"
    write_round(
        auto_dir,
        "s1",
        "round_001.json",
        {
            "session_id": "s1",
            "round": 1,
            "status": "completed",
            "progress_class": "strong",
            "outcome_detected": False,
            "kb_changed": True,
            "kb_delta": {"new_nodes": [{"node_id": "P_NEW"}], "updated_nodes": []},
            "events": [
                {"type": "tool_result", "name": "record_line", "result_preview": "✅ LINE [异轮]: P_NEW --[based_on]--> P_OLD"},
            ],
            "phase_trace": {"current_state_preview": {"active_nodes": [{"node_id": "P_NEW"}]}},
            "pls_telemetry": {"points_created": 1, "lines_created": 1, "cross_round_lines": 1, "line_errors": 0},
        },
    )

    rows = canonicalize_records(load_round_records(auto_dir))

    assert len(rows) == 5
    physical = domain_row(rows, "physical_file_outcome")
    knowledge = domain_row(rows, "knowledge_domain_evidence")
    line_activity = domain_row(rows, "line_activity_evidence")
    line_consumption = domain_row(rows, "line_consumption_evidence")
    governance = domain_row(rows, "governance_review_outcome")
    assert physical["observed"] is False
    assert physical["physical_only_shadowed"] is False
    assert knowledge["observed"] is True
    assert knowledge["physical_only_shadowed"] is True
    assert "contract_required" in knowledge["allowed_decision_effects"]
    assert line_activity["physical_only_shadowed"] is True
    assert line_consumption["governance_state_hint"] == "needs_verification"
    assert line_consumption["consumption_tier"] == "weak_active_context"
    assert "verify_consumption_before_outcome" in line_consumption["allowed_decision_effects"]
    assert governance["mappable"] is False
    assert governance["governance_state_hint"] == "ignored"
    assert "do_not_broaden_outcome_detected" in knowledge["non_actions"]


def test_build_report_summarizes_rows_and_shadow_gap(tmp_path):
    auto_dir = tmp_path / "auto_reports"
    write_round(
        auto_dir,
        "s1",
        "round_001.json",
        {
            "session_id": "s1",
            "round": 1,
            "status": "completed",
            "progress_class": "evidence",
            "outcome_detected": True,
            "kb_changed": False,
            "kb_delta": {"new_nodes": [], "updated_nodes": []},
            "events": [],
            "phase_trace": {"current_state_preview": {"active_nodes": []}},
            "pls_telemetry": {"points_created": 0, "lines_created": 0, "cross_round_lines": 0, "line_errors": 0},
        },
    )
    write_round(
        auto_dir,
        "s1",
        "round_002.json",
        {
            "session_id": "s1",
            "round": 2,
            "status": "completed",
            "progress_class": "strong",
            "outcome_detected": False,
            "kb_changed": True,
            "kb_delta": {"new_nodes": [], "updated_nodes": []},
            "events": [],
            "phase_trace": {"current_state_preview": {"active_nodes": []}},
            "pls_telemetry": {"points_created": 0, "lines_created": 0, "cross_round_lines": 0, "line_errors": 0},
        },
    )

    report = build_report(auto_reports_dir=auto_dir, sample_limit=3)

    assert report["mode"] == "read_only_canonicalizer"
    assert report["dry_run"] is True
    assert report["rounds_loaded"] == 2
    assert report["summary"]["total_rows"] == 10
    observed = {item["value"]: item["count"] for item in report["summary"]["observed_by_domain"]}
    assert observed["physical_file_outcome"] == 1
    assert observed["knowledge_domain_evidence"] == 1
    shadowed = {item["value"]: item["count"] for item in report["summary"]["physical_only_shadowed_by_domain"]}
    assert shadowed["knowledge_domain_evidence"] == 1
    assert report["physical_only_shadow_gap"]["physical_only_shadow_gap_rounds"] == 1
    assert "do_not_write_canonical_rows_to_nodevault" in report["constraints"]


def test_render_jsonl_outputs_one_json_object_per_row(tmp_path):
    auto_dir = tmp_path / "auto_reports"
    write_round(
        auto_dir,
        "s1",
        "round_001.json",
        {
            "session_id": "s1",
            "round": 1,
            "status": "completed",
            "progress_class": "idle",
            "outcome_detected": False,
            "kb_changed": False,
            "kb_delta": {"new_nodes": [], "updated_nodes": []},
            "events": [],
            "phase_trace": {"current_state_preview": {"active_nodes": []}},
            "pls_telemetry": {"points_created": 0, "lines_created": 0, "cross_round_lines": 0, "line_errors": 0},
        },
    )
    rows = canonicalize_records(load_round_records(auto_dir))
    text = render_jsonl(rows)
    parsed = [json.loads(line) for line in text.splitlines()]

    assert len(parsed) == 5
    assert {row["domain"] for row in parsed} == {
        "physical_file_outcome",
        "knowledge_domain_evidence",
        "line_activity_evidence",
        "line_consumption_evidence",
        "governance_review_outcome",
    }
