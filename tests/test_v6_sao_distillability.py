from __future__ import annotations

import json
import sqlite3
import sys
import types
from pathlib import Path

from genesis.v6.audit_sao_distillability import build_report, classify_route_family, pollution_flags, round_schema_profile, training_readiness, weak_outcome_labels


def write_round(root: Path, session: str, name: str, data: dict) -> Path:
    path = root / session / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def make_traces_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE traces (
            trace_id TEXT PRIMARY KEY,
            user_input TEXT,
            started_at REAL,
            ended_at REAL,
            duration_ms REAL,
            total_input_tokens INTEGER DEFAULT 0,
            total_output_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            phase_count INTEGER DEFAULT 0,
            llm_call_count INTEGER DEFAULT 0,
            tool_call_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running',
            final_response_preview TEXT,
            error TEXT
        );
        CREATE TABLE spans (
            span_id TEXT PRIMARY KEY,
            trace_id TEXT,
            parent_span_id TEXT,
            name TEXT,
            span_type TEXT,
            phase TEXT,
            started_at REAL,
            ended_at REAL,
            duration_ms REAL,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            total_tokens INTEGER,
            tool_name TEXT,
            tool_args_preview TEXT,
            tool_result_preview TEXT,
            metadata_json TEXT,
            status TEXT DEFAULT 'running',
            error TEXT,
            cache_hit_tokens INTEGER
        );
        INSERT INTO traces (trace_id, user_input, started_at, status, tool_call_count) VALUES ('tr_test', 'debug pytest failure', 1.0, 'completed', 1);
        INSERT INTO spans (span_id, trace_id, name, span_type, phase, started_at, ended_at, tool_name, tool_args_preview, tool_result_preview, status)
        VALUES ('sp_tool', 'tr_test', 'tool:pytest', 'tool_call', 'GP', 1.0, 2.0, 'shell', '{"command":"pytest"}', 'ok', 'completed');
        """
    )
    con.commit()
    con.close()


def test_classifies_pls_anchor_and_pollution_flags():
    record = {
        "status": "completed",
        "progress_class": "strong",
        "outcome_detected": False,
        "kb_changed": True,
        "events": [
            {"type": "tool_result", "name": "search_knowledge_nodes", "result_preview": "found"},
            {"type": "tool_result", "name": "record_point", "result_preview": "✅ POINT [P_NEW] 'new point'"},
            {"type": "tool_result", "name": "record_line", "result_preview": "✅ LINE: P_NEW --[based_on]--> P_OLD [异轮]"},
        ],
        "pls_telemetry": {"points_created": 1, "lines_created": 1},
        "round_topology": {"timeout_risk_shape": False},
        "state_freshness": {"state_stale": False},
        "c_phase_summary": {"supplements": 1},
    }

    assert classify_route_family(record) == "pls_point_line_anchor"
    labels = weak_outcome_labels(record)
    assert "outcome:no_sandbox_diff" in labels
    assert "kb:changed" in labels
    assert "c_phase:supplemented" in labels
    flags = pollution_flags(record)
    assert "strong_is_activity_proxy_not_success" in flags
    assert "kb_changed_not_semantic_ground_truth" in flags
    assert "completed_not_task_success_ground_truth" in flags


def test_build_report_counts_coverage_route_outcomes_and_external_sources(tmp_path):
    auto_dir = tmp_path / "auto_reports"
    traces_db = tmp_path / "traces.db"
    shadow_log = tmp_path / "v6_shadow_predictions.jsonl"
    make_traces_db(traces_db)
    shadow_log.write_text(
        json.dumps({"mode": "shadow_only", "fields": ["error_kind", "runtime"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
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
            "kb_changed": True,
            "knowledge_state": {"issue": "debug"},
            "frontier_state": {"candidate_issue": "debug"},
            "events": [{"type": "tool_result", "name": "shell", "result_preview": "pytest ok"}],
            "phase_trace": {"current_state_preview": {"active_nodes": [{"node_id": "P1", "roles": ["tool_opened"]}]}},
            "kb_delta": {"new_nodes": [], "updated_nodes": []},
            "pls_telemetry": {"points_created": 0, "lines_created": 0},
            "round_topology": {"timeout_risk_shape": False},
            "state_freshness": {"state_stale": False},
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
            "kb_changed": False,
            "knowledge_state": {"issue": "inspect"},
            "frontier_state": {"candidate_issue": "inspect"},
            "events": [{"type": "tool_result", "name": "read_file", "result_preview": "content"}],
            "phase_trace": {"current_state_preview": {"active_nodes": []}},
            "kb_delta": {"new_nodes": [], "updated_nodes": []},
            "pls_telemetry": {"points_created": 0, "lines_created": 0},
            "round_topology": {"timeout_risk_shape": False},
            "state_freshness": {"state_stale": False},
        },
    )

    report = build_report(auto_reports_dir=auto_dir, traces_db=traces_db, shadow_log=shadow_log)

    assert report["mode"] == "read_only_audit"
    assert report["decision"] == "PROCEED_TO_OFFLINE_SAO_CANONICALIZER"
    assert report["rounds"]["total_loaded"] == 2
    assert report["rounds"]["coverage"]["group_minimums"]["state"] == 1.0
    assert report["rounds"]["coverage"]["group_minimums"]["outcome"] == 1.0
    stability = report["rounds"]["schema_stability"]
    assert stability["stable_rounds"] == 2
    assert stability["legacy_or_incomplete_rounds"] == 0
    assert stability["stable_ratio"] == 1.0
    assert stability["candidate_sessions"][0]["session_id"] == "s1"
    assert stability["candidate_sessions"][0]["stable_rounds"] == 2
    route_counts = {item["value"]: item["count"] for item in report["rounds"]["route_families"]}
    assert route_counts["test_or_doctor_verify"] == 1
    assert route_counts["inspect_only"] == 1
    flags = {item["value"]: item["count"] for item in report["rounds"]["pollution_flags"]}
    assert flags["completed_not_task_success_ground_truth"] == 2
    assert report["traces_db"]["available"] is True
    assert report["traces_db"]["tool_label_nonempty_ratio"] == 1.0
    assert report["shadow_log"]["records"] == 1


def test_schema_stability_detects_legacy_or_incomplete_rounds(tmp_path):
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
            "knowledge_state": {"issue": "old"},
            "frontier_state": {"candidate_issue": "old"},
            "events": [{"type": "tool_result", "name": "read_file", "result_preview": "content"}],
            "phase_trace": {"current_state_preview": {"active_nodes": []}},
            "kb_delta": {"new_nodes": [], "updated_nodes": []},
        },
    )

    record = json.loads((auto_dir / "legacy" / "round_001.json").read_text(encoding="utf-8"))
    profile = round_schema_profile(record)
    assert profile["stable"] is False
    assert profile["groups"]["state"] is True
    assert profile["groups"]["action"] is False
    assert profile["groups"]["outcome"] is False
    assert profile["groups"]["connection"] is False
    assert "round_topology" in profile["missing"]["action"]
    assert "outcome_detected_bool" in profile["missing"]["outcome"]
    assert "pls_telemetry" in profile["missing"]["connection"]

    report = build_report(auto_reports_dir=auto_dir, traces_db=tmp_path / "missing_traces.db", shadow_log=tmp_path / "missing_shadow.jsonl")
    stability = report["rounds"]["schema_stability"]
    assert report["decision"] == "COLLECT_MORE_SCHEMA_STABLE_ROUNDS"
    assert stability["stable_rounds"] == 0
    assert stability["legacy_or_incomplete_rounds"] == 1
    missing = {item["value"]: item["count"] for item in stability["top_missing_requirements"]}
    assert missing["action:round_topology"] == 1
    assert missing["outcome:outcome_detected_bool"] == 1
    assert missing["connection:pls_telemetry"] == 1


def test_current_auto_mode_helpers_can_emit_schema_stable_completed_round(monkeypatch):
    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = object
    sys.modules.setdefault("discord", discord_stub)

    from genesis.auto_mode import _build_pls_telemetry, _build_round_topology, _classify_auto_round_progress

    round_events = [
        {"t": 1.0, "type": "llm_call_start", "phase": "GP_PHASE", "data": {"phase": "GP_PHASE"}},
        {"t": 2.0, "type": "tool_result", "name": "search_knowledge_nodes", "result_preview": "found P_OLD"},
        {"t": 3.0, "type": "tool_result", "name": "record_point", "args": {"node_id": "P_NEW"}, "result_preview": "✅ POINT [P_NEW] new finding"},
        {"t": 4.0, "type": "tool_result", "name": "record_line", "args": {"new_point_id": "P_NEW", "basis_point_id": "P_OLD"}, "result_preview": "✅ LINE: P_NEW --[RELATED_TO]--> P_OLD [异轮]"},
    ]
    kb_delta = {"new_nodes": ["P_NEW"], "updated_nodes": [], "error": ""}
    progress = _classify_auto_round_progress(
        response="recorded a point and anchored it to prior evidence",
        round_events=round_events,
        kb_changed=True,
        outcome_detected=True,
    )
    round_record = {
        "status": "completed",
        "progress_class": progress["progress_class"],
        "outcome_detected": progress["outcome_detected"],
        "kb_delta": kb_delta,
        "knowledge_state": {"issue": "schema stability support"},
        "frontier_state": {"candidate_issue": "schema stability support"},
        "events": round_events,
        "phase_trace": {
            "current_state_preview": {
                "active_nodes": [{"node_id": "P_OLD", "roles": ["routing_seed", "tool_opened"]}],
            },
        },
        "pls_telemetry": _build_pls_telemetry(round_events, kb_delta),
        "round_topology": _build_round_topology(round_events, duration_s=5.0),
    }

    profile = round_schema_profile(round_record)

    assert profile["stable"] is True
    assert round_record["outcome_detected"] is True
    assert round_record["pls_telemetry"]["points_created"] == 1
    assert round_record["pls_telemetry"]["lines_created"] == 1
    assert round_record["round_topology"]["anchored"] is True
    assert round_record["round_topology"]["classification"] == "anchored_compact"


def test_training_readiness_marks_arena_env_and_contradiction_risks_for_review():
    record = {
        "status": "completed",
        "progress_class": "strong",
        "outcome_detected": True,
        "kb_changed": True,
        "knowledge_state": {"issue": "ENV_FACT cwd 与当前运行环境可能矛盾"},
        "frontier_state": {"candidate_issue": "CONTRADICTS conflict needs review"},
        "events": [
            {"type": "tool_result", "name": "read_file", "result_preview": "checked environment fact and contradiction"},
        ],
        "phase_trace": {
            "current_state_preview": {
                "active_nodes": [{"node_id": "P_ENV", "roles": ["routing_seed"]}],
            },
        },
        "kb_delta": {"new_nodes": [], "updated_nodes": []},
        "pls_telemetry": {"points_created": 0, "lines_created": 0},
        "round_topology": {"timeout_risk_shape": False},
    }

    readiness = training_readiness(record)

    assert readiness["schema_stable"] is True
    assert readiness["route_policy_candidate"] is True
    assert readiness["per_node_credit_candidate"] is False
    assert readiness["review_required"] is True
    assert "arena_collective_attribution_risk" in readiness["pollution_flags"]
    assert "env_fact_state_risk" in readiness["pollution_flags"]
    assert "contradiction_conflict_risk" in readiness["pollution_flags"]
    assert "per_node_credit_requires_attribution_audit" in readiness["review_reasons"]
    assert "environment_state_requires_freshness_check" in readiness["review_reasons"]
    assert "conflict_sensitive_sample_requires_contradiction_flag" in readiness["review_reasons"]


def test_report_training_readiness_summarizes_exclusions_and_review_reasons(tmp_path):
    auto_dir = tmp_path / "auto_reports"
    stable_risky = {
        "session_id": "s1",
        "round": 1,
        "status": "completed",
        "progress_class": "strong",
        "outcome_detected": True,
        "kb_changed": True,
        "knowledge_state": {"issue": "ENV_FACT needs checking"},
        "frontier_state": {"candidate_issue": "CONTRADICTS should be flagged"},
        "events": [{"type": "tool_result", "name": "read_file", "result_preview": "environment fact contradiction"}],
        "phase_trace": {"current_state_preview": {"active_nodes": [{"node_id": "P1", "roles": ["routing_seed"]}]}},
        "kb_delta": {"new_nodes": [], "updated_nodes": []},
        "pls_telemetry": {"points_created": 0, "lines_created": 0},
        "round_topology": {"timeout_risk_shape": False},
    }
    legacy = {
        "session_id": "s1",
        "round": 2,
        "status": "completed",
        "progress_class": "strong",
        "knowledge_state": {"issue": "legacy"},
        "frontier_state": {"candidate_issue": "legacy"},
        "events": [{"type": "tool_result", "name": "read_file", "result_preview": "content"}],
        "phase_trace": {"current_state_preview": {"active_nodes": []}},
        "kb_delta": {"new_nodes": [], "updated_nodes": []},
    }
    write_round(auto_dir, "s1", "round_001.json", stable_risky)
    write_round(auto_dir, "s1", "round_002.json", legacy)

    report = build_report(auto_reports_dir=auto_dir, traces_db=tmp_path / "missing.db", shadow_log=tmp_path / "missing.jsonl")
    readiness = report["rounds"]["training_readiness"]

    assert readiness["route_policy_candidates"] == 1
    assert readiness["per_node_credit_candidates"] == 0
    assert readiness["review_required"] == 1
    exclusions = {item["value"]: item["count"] for item in readiness["top_exclusion_reasons"]}
    reviews = {item["value"]: item["count"] for item in readiness["top_review_reasons"]}
    assert exclusions["schema_not_stable"] == 1
    assert reviews["per_node_credit_requires_attribution_audit"] == 1
    assert reviews["environment_state_requires_freshness_check"] == 1
    assert reviews["conflict_sensitive_sample_requires_contradiction_flag"] == 1
