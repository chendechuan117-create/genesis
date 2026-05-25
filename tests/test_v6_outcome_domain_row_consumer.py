from __future__ import annotations

import json
from pathlib import Path

from genesis.v6.canonicalize_outcome_domains import canonicalize_records, render_jsonl
from genesis.v6.consume_outcome_domain_rows import build_report, consume_rows, load_rows
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


def test_consume_rows_routes_observed_domains_without_promoting_runtime_outcome(tmp_path):
    rows = make_rows(tmp_path)

    result = consume_rows(rows, sample_limit=10)

    assert result["total_rows"] == 10
    assert result["queue_counts"]["review_queue"] == 2
    assert result["queue_counts"]["verification_queue"] == 2
    assert result["queue_counts"]["training_readiness_candidates"] == 0
    assert result["queue_counts"]["rejected_rows"] == 6
    decisions = {item["value"]: item["count"] for item in result["decision_distribution"]}
    assert decisions["review_physical_artifact"] == 1
    assert decisions["review_knowledge_evidence"] == 1
    assert decisions["verify_line_activity"] == 1
    assert decisions["verify_weak_line_consumption"] == 1
    review_item = next(item for item in result["queues"]["review_queue"] if item["domain"] == "knowledge_domain_evidence")
    assert review_item["physical_only_shadowed"] is True
    assert "do_not_broaden_outcome_detected" in review_item["non_actions"]


def test_build_report_from_auto_reports_produces_governance_aggregator_decision(tmp_path):
    rows = make_rows(tmp_path)
    auto_dir = Path(rows[0]["source_path"]).parents[1]

    report = build_report(auto_reports_dir=auto_dir, sample_limit=10)

    assert report["mode"] == "read_only_consumer"
    assert report["dry_run"] is True
    assert report["consumer"] == "outcome_domain_row_consumer"
    assert report["decision"] == "PROCEED_TO_GOVERNANCE_AGGREGATOR_DESIGN"
    assert report["consumption"]["queue_counts"]["review_queue"] == 2
    assert report["consumption"]["queue_counts"]["verification_queue"] == 2
    assert "do_not_write_queue_to_nodevault" in report["constraints"]
    assert "do_not_promote_review_queue_without_human_decision" in report["constraints"]


def test_build_report_can_consume_jsonl_rows_input(tmp_path):
    rows = make_rows(tmp_path)
    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text(render_jsonl(rows), encoding="utf-8")

    loaded = load_rows(rows_path)
    report = build_report(rows_input=rows_path, sample_limit=10)

    assert len(loaded) == 10
    assert report["source"]["rows_input"] == str(rows_path)
    assert report["source"]["auto_reports_dir"] is None
    assert report["consumption"]["queue_counts"]["review_queue"] == 2
