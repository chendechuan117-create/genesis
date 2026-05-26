from __future__ import annotations

import json
from pathlib import Path

from genesis.v6.audit_outcome_domain_compatibility import build_report, classify_record_domains, load_round_records


def write_round(root: Path, session: str, name: str, data: dict) -> Path:
    path = root / session / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_classify_record_domains_separates_physical_knowledge_line_and_consumption():
    record = {
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
    }

    domains = classify_record_domains(record)

    assert domains["physical_file_outcome"]["mappable"] is True
    assert domains["physical_file_outcome"]["observed"] is False
    assert domains["knowledge_domain_evidence"]["observed"] is True
    assert domains["line_activity_evidence"]["observed"] is True
    assert domains["line_consumption_evidence"]["observed"] is True
    assert domains["line_consumption_evidence"]["consumption_tier"] == "weak_active_context"
    assert domains["governance_review_outcome"]["mappable"] is False


def test_build_report_counts_contract_mapping_and_physical_shadow_gap(tmp_path):
    auto_dir = tmp_path / "auto_reports"
    review_doc = tmp_path / "review.md"
    contract_doc = tmp_path / "contract.md"
    review_doc.write_text("review", encoding="utf-8")
    contract_doc.write_text("contract", encoding="utf-8")
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

    report = build_report(auto_reports_dir=auto_dir, review_doc=review_doc, contract_doc=contract_doc, sample_limit=5)

    assert report["mode"] == "read_only_audit"
    assert report["dry_run"] is True
    assert report["consumer"] == "outcome_domain_compatibility_audit"
    assert report["decision"] == "PROCEED_TO_READ_ONLY_DOMAIN_CANONICALIZER_DESIGN"
    assert report["rounds"]["total_loaded"] == 2
    coverage = report["domain_coverage"]
    assert coverage["physical_file_outcome"]["mappable_rounds"] == 2
    assert coverage["physical_file_outcome"]["observed_rounds"] == 1
    assert coverage["knowledge_domain_evidence"]["observed_rounds"] == 1
    assert coverage["line_activity_evidence"]["observed_rounds"] == 1
    assert coverage["line_consumption_evidence"]["observed_rounds"] == 1
    assert coverage["governance_review_outcome"]["mappable_rounds"] == 0
    gap = report["physical_only_shadow_gap"]
    assert gap["physical_absent_rounds"] == 1
    assert gap["physical_only_shadow_gap_rounds"] == 1
    assert gap["shadow_gap_ratio_among_physical_absent_rounds"] == 1.0
    assert gap["samples"][0]["outcome_detected"] is False
    assert "knowledge_domain_evidence" in gap["samples"][0]["non_physical_domains"]
    assert "do_not_broaden_outcome_detected" in report["constraints"]
    assert report["external_artifacts"]["review_doc"]["available"] is True
    assert report["external_artifacts"]["contract_doc"]["available"] is True


def test_legacy_round_reports_missing_domain_fields(tmp_path):
    auto_dir = tmp_path / "auto_reports"
    write_round(
        auto_dir,
        "legacy",
        "round_001.json",
        {
            "session_id": "legacy",
            "round": 1,
            "status": "completed",
            "progress_class": "strong",
            "events": [],
        },
    )

    records = load_round_records(auto_dir)
    domains = classify_record_domains(records[0])

    assert domains["physical_file_outcome"]["mappable"] is False
    assert "outcome_detected_bool" in domains["physical_file_outcome"]["missing_requirements"]
    assert domains["knowledge_domain_evidence"]["mappable"] is False
    assert domains["line_activity_evidence"]["mappable"] is True
    assert domains["line_activity_evidence"]["observed"] is False
    assert domains["line_consumption_evidence"]["mappable"] is False
    assert "record_line_success" in domains["line_consumption_evidence"]["missing_requirements"]
    assert "phase_trace.current_state_preview.active_nodes" in domains["line_consumption_evidence"]["missing_requirements"]


def test_line_consumption_not_observed_when_point_not_in_active_nodes():
    """line created but point ID not in active_nodes → consumption NOT observed"""
    record = {
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
        "phase_trace": {"current_state_preview": {"active_nodes": [{"node_id": "P_OTHER"}]}},
        "pls_telemetry": {"points_created": 1, "lines_created": 1, "cross_round_lines": 1, "line_errors": 0},
    }
    domains = classify_record_domains(record)
    assert domains["line_activity_evidence"]["observed"] is True
    assert domains["line_consumption_evidence"]["mappable"] is True
    assert domains["line_consumption_evidence"]["observed"] is False


def test_line_consumption_observed_when_point_in_active_nodes():
    """line created AND point ID in active_nodes → consumption observed (weak)"""
    record = {
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
    }
    domains = classify_record_domains(record)
    assert domains["line_activity_evidence"]["observed"] is True
    assert domains["line_consumption_evidence"]["observed"] is True
    assert domains["line_consumption_evidence"]["consumption_tier"] == "weak_active_context"


def test_line_consumption_requires_both_line_success_and_active_nodes():
    """Without active_nodes field, consumption is not mappable even with line success"""
    record = {
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
        "phase_trace": {},
        "pls_telemetry": {"points_created": 1, "lines_created": 1, "cross_round_lines": 1, "line_errors": 0},
    }
    domains = classify_record_domains(record)
    assert domains["line_activity_evidence"]["observed"] is True
    assert domains["line_consumption_evidence"]["mappable"] is False
    assert "phase_trace.current_state_preview.active_nodes" in domains["line_consumption_evidence"]["missing_requirements"]
