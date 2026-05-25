from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from genesis.v6.audit_yogg_signal_promotion import build_report, load_round_records, summarize_records


def write_round(root: Path, session: str, name: str, data: dict) -> Path:
    path = root / session / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def make_nodevault_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE knowledge_nodes (
            node_id TEXT PRIMARY KEY,
            type TEXT,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE node_content (
            node_id TEXT PRIMARY KEY,
            full_content TEXT
        );
        CREATE TABLE reasoning_lines (
            line_id TEXT PRIMARY KEY,
            new_point_id TEXT NOT NULL,
            basis_point_id TEXT NOT NULL,
            reasoning TEXT NOT NULL,
            trace_id TEXT,
            round_seq INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT DEFAULT 'GP',
            same_round INTEGER DEFAULT 0
        );
        CREATE TABLE node_edges (
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            relation TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (source_id, target_id, relation)
        );
        INSERT INTO knowledge_nodes (node_id, type, title, created_at, updated_at)
        VALUES ('P_NEW', 'LESSON', 'new', '2026-05-25 00:00:00', '2026-05-25 00:00:00');
        INSERT INTO reasoning_lines (line_id, new_point_id, basis_point_id, reasoning, created_at, same_round)
        VALUES ('L1', 'P_NEW', 'P_OLD', 'basis reasoning', '2026-05-25 00:00:00', 0);
        INSERT INTO node_edges (source_id, target_id, relation, created_at)
        VALUES ('P_NEW', 'P_OLD', 'RELATED_TO', '2026-05-25 00:00:00');
        """
    )
    con.commit()
    con.close()


def add_consuming_reasoning_line(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute(
        "INSERT INTO knowledge_nodes (node_id, type, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("P_LATER", "LESSON", "later", "2026-05-25 01:00:00", "2026-05-25 01:00:00"),
    )
    con.execute(
        "INSERT INTO reasoning_lines (line_id, new_point_id, basis_point_id, reasoning, created_at, same_round) VALUES (?, ?, ?, ?, ?, ?)",
        ("L2", "P_LATER", "P_NEW", "later consumes P_NEW", "2026-05-25 01:00:00", 0),
    )
    con.commit()
    con.close()


def test_load_and_summarize_round_records_detects_line_gap(tmp_path):
    auto_dir = tmp_path / "auto_reports"
    write_round(
        auto_dir,
        "s1",
        "round_001.json",
        {
            "session_id": "s1",
            "round": 1,
            "status": "completed",
            "progress_class": "soft",
            "outcome_detected": False,
            "kb_changed": True,
            "kb_delta": {"new_nodes": [{"node_id": "P_NEW"}], "updated_nodes": [], "error": None},
            "events": [
                {"type": "tool_result", "name": "record_line", "result_preview": "✅ LINE [异轮]: P_NEW --[based_on]--> P_OLD"},
            ],
            "phase_trace": {"current_state_preview": {"active_nodes": [{"node_id": "P_NEW"}]}},
            "pls_telemetry": {"points_created": 1, "lines_created": 1, "cross_round_lines": 1, "line_errors": 0},
        },
    )

    records = load_round_records(auto_dir)
    summary = summarize_records(records, sample_limit=3)

    assert summary["total_rounds"] == 1
    assert summary["kb_delta_has_line_fields"] is False
    assert summary["totals"]["lines_created"] == 1
    assert summary["event_counts"]["record_line_success"] == 1
    assert summary["activity_without_outcome_paths"]
    assert summary["knowledge_without_physical_paths"]
    assert summary["outcome_domain_distribution"]
    assert summary["line_pair_samples"][0]["new_point_id"] == "P_NEW"
    assert summary["active_context_line_hit_count"] == 1


def test_build_report_queues_activity_line_gap_and_privileged_review(tmp_path):
    auto_dir = tmp_path / "auto_reports"
    db_path = tmp_path / "workshop_v4.sqlite"
    service_file = tmp_path / "yogg-auto.service"
    sudo_snapshot = tmp_path / "sudo.txt"
    make_nodevault_db(db_path)
    add_consuming_reasoning_line(db_path)
    service_file.write_text("User=yoga\nMemoryMax=3400M\nRestart=always\nExecStart=/usr/bin/python yogg_auto.py\n", encoding="utf-8")
    sudo_snapshot.write_text("(ALL) NOPASSWD: ALL\n", encoding="utf-8")
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
            "kb_delta": {"new_nodes": [{"node_id": "P_NEW"}], "updated_nodes": [], "error": None},
            "events": [
                {"type": "tool_result", "name": "record_line", "result_preview": "✅ LINE [异轮]: P_NEW --[based_on]--> P_OLD"},
            ],
            "phase_trace": {"current_state_preview": {"active_nodes": [{"node_id": "P_NEW"}]}},
            "pls_telemetry": {"points_created": 1, "lines_created": 1, "cross_round_lines": 1, "line_errors": 0},
        },
    )

    report = build_report(
        auto_reports_dir=auto_dir,
        nodevault_db=db_path,
        service_file=service_file,
        sudo_snapshot=sudo_snapshot,
        created_since="2026-05-24 00:00:00",
    )

    assert report["dry_run"] is True
    assert report["mode"] == "read_only_audit"
    assert report["governance_mode"] == "report_only"
    assert report["consumer"] == "yogg_signal_promotion_queue"
    assert report["rounds"]["kb_delta_has_line_fields"] is False
    assert report["nodevault"]["available"] is True
    assert report["nodevault"]["counts"]["reasoning_lines"] == 2
    assert report["nodevault"]["line_consumption"]["consumed_as_basis"] == 1
    assert report["queue_counts"]["candidate"] >= 1
    assert report["queue_counts"]["needs_verification"] >= 1
    assert report["queue_counts"]["needs_resolution"] >= 1
    assert report["queue_counts"]["needs_human_review"] >= 1
    assert report["queue_counts"]["quarantined_candidate"] >= 1
    assert report["queue_counts"]["resolved"] >= 1
    assert report["constraint_surface"]["bypassable_private_channel"] is True
    assert report["constraint_surface"]["risk_level"] == "high"
    assert "do_not_modify_nodevault" in report["constraints"]
    assert "do_not_treat_activity_as_outcome" in report["constraints"]
    decisions = {item["signal_id"]: item["consumer_decision"] for item in report["queues"]["needs_resolution"]}
    assert decisions["kb_delta_node_only_line_gap"] == "define_consumer_before_runtime_fields"
    assert decisions["knowledge_outcome_without_physical_outcome"] == "separate_outcome_domains_before_runtime_behavior"
    quarantined_ids = {item["signal_id"] for item in report["queues"]["quarantined_candidate"]}
    assert "constraint_surface_private_bypass_audit" in quarantined_ids
    resolved_ids = {item["signal_id"] for item in report["queues"]["resolved"]}
    assert "reasoning_line_consumed_as_later_basis" in resolved_ids
    needs_verification_ids = {item["signal_id"] for item in report["queues"]["needs_verification"]}
    assert "reasoning_line_node_selected_into_active_context" not in resolved_ids
    assert "reasoning_line_node_selected_into_active_context" in needs_verification_ids


def test_raw_activity_without_evidence_is_ignored_not_outcome(tmp_path):
    auto_dir = tmp_path / "auto_reports"
    db_path = tmp_path / "workshop_v4.sqlite"
    make_nodevault_db(db_path)
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
            "kb_changed": False,
            "kb_delta": {"new_nodes": [], "updated_nodes": [], "error": None},
            "events": [],
            "pls_telemetry": {"points_created": 0, "lines_created": 0, "cross_round_lines": 0, "line_errors": 0},
        },
    )

    report = build_report(auto_reports_dir=auto_dir, nodevault_db=db_path)

    ignored_ids = {item["signal_id"] for item in report["queues"]["ignored"]}
    assert "raw_progress_class_activity_only" in ignored_ids
    assert report["queue_counts"]["resolved"] == 0
    assert all(item["governance_state"] != "resolved" for items in report["queues"].values() for item in items)
