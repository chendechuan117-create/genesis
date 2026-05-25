from __future__ import annotations

import json
from pathlib import Path

from genesis.v6.aggregate_outcome_governance import aggregate_consumption, build_report
from genesis.v6.canonicalize_outcome_domains import canonicalize_records, render_jsonl
from genesis.v6.consume_outcome_domain_rows import consume_rows
from genesis.v6.audit_outcome_domain_compatibility import load_round_records


def write_round(root: Path, session: str, name: str, data: dict) -> Path:
    path = root / session / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def make_rows(tmp_path: Path) -> list[dict]:
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
            "kb_delta": {"new_nodes": [{"node_id": "P_NEW"}], "updated_nodes": []},
            "events": [
                {"type": "tool_result", "name": "record_line", "result_preview": "✅ LINE [异轮]: P_NEW --[based_on]--> P_OLD"},
            ],
            "phase_trace": {"current_state_preview": {"active_nodes": [{"node_id": "P_NEW"}]}},
            "pls_telemetry": {"points_created": 1, "lines_created": 1, "cross_round_lines": 1, "line_errors": 0},
        },
    )
    return canonicalize_records(load_round_records(auto_dir))


def test_aggregate_consumption_groups_full_queues_into_governance_states(tmp_path):
    rows = make_rows(tmp_path)
    consumption = consume_rows(rows, sample_limit=1)

    aggregates = aggregate_consumption(consumption, sample_limit=3)

    assert len(consumption["queues"]["review_queue"]) == 2
    assert len(consumption["queue_samples"]["review_queue"]) == 1
    assert len(aggregates["candidate"]) == 1
    assert len(aggregates["needs_resolution"]) == 1
    assert len(aggregates["needs_verification"]) == 2
    assert len(aggregates["ignored"]) == 5
    physical = aggregates["candidate"][0]
    knowledge = aggregates["needs_resolution"][0]
    assert physical["aggregate_id"] == "review_physical_artifact:physical_file_outcome"
    assert physical["row_count"] == 1
    assert knowledge["aggregate_id"] == "review_knowledge_evidence:knowledge_domain_evidence"
    assert knowledge["priority"] == "P0"
    assert knowledge["physical_only_shadowed_count"] == 1
    assert knowledge["consumer_decision"] == "decide_whether_to_create_governance_review_outcome"
    assert "do_not_write_aggregation_to_nodevault" in knowledge["non_actions"]


def test_build_report_from_auto_reports_is_ready_for_manual_governance_review(tmp_path):
    rows = make_rows(tmp_path)
    auto_dir = Path(rows[0]["source_path"]).parents[1]

    report = build_report(auto_reports_dir=auto_dir, sample_limit=5)

    assert report["mode"] == "read_only_governance_aggregator"
    assert report["dry_run"] is True
    assert report["consumer"] == "outcome_governance_aggregator"
    assert report["decision"] == "READY_FOR_MANUAL_GOVERNANCE_REVIEW"
    assert report["input_total_rows"] == 10
    assert report["summary"]["aggregate_counts"]["needs_resolution"] == 1
    assert report["summary"]["aggregate_counts"]["needs_verification"] == 2
    assert report["summary"]["aggregate_counts"]["candidate"] == 1
    assert report["summary"]["aggregate_counts"]["ignored"] == 5
    rows_by_state = {item["value"]: item["count"] for item in report["summary"]["row_counts_by_governance_state"]}
    assert rows_by_state["ignored"] == 6
    assert "do_not_create_governance_review_outcome_without_human_decision" in report["constraints"]


def test_build_report_can_aggregate_rows_input_jsonl(tmp_path):
    rows = make_rows(tmp_path)
    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text(render_jsonl(rows), encoding="utf-8")

    report = build_report(rows_input=rows_path, sample_limit=5)

    assert report["source"]["rows_input"] == str(rows_path)
    assert report["input_total_rows"] == 10
    assert report["summary"]["aggregate_counts"]["needs_resolution"] == 1
