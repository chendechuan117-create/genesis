from datetime import datetime, timedelta


def make_vault(tmp_path):
    from genesis.v4.manager import NodeVault

    NodeVault._instance = None
    db_path = tmp_path / "vault.sqlite"
    db_path.touch()
    return NodeVault(db_path=db_path, skip_vector_engine=True)


def reset_vault():
    from genesis.v4.manager import NodeVault

    if NodeVault._instance is not None:
        try:
            NodeVault._instance._conn.close()
        except Exception:
            pass
    NodeVault._instance = None


def create_node(vault, node_id):
    vault.create_node(
        node_id=node_id,
        ntype="CONTEXT",
        title=node_id,
        human_translation=node_id,
        tags="test",
        full_content=node_id,
    )


def test_contradiction_audit_report_is_read_only_and_reports_unresolved_active_edges(tmp_path):
    vault = make_vault(tmp_path)
    try:
        create_node(vault, "P_CONTRA_NEW")
        create_node(vault, "P_CONTRA_OLD")
        assert vault.create_node_edge("P_CONTRA_NEW", "P_CONTRA_OLD", "CONTRADICTS")
        old_created_at = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d %H:%M:%S")
        vault._conn.execute(
            "UPDATE node_edges SET created_at = ? WHERE source_id = ? AND target_id = ? AND relation = ?",
            (old_created_at, "P_CONTRA_NEW", "P_CONTRA_OLD", "CONTRADICTS"),
        )
        vault._conn.commit()
        before_edges = vault._conn.execute("SELECT COUNT(*) FROM node_edges").fetchone()[0]

        report = vault.contradiction_audit_report(stale_days=30)

        after_edges = vault._conn.execute("SELECT COUNT(*) FROM node_edges").fetchone()[0]
        assert before_edges == after_edges
        assert report["dry_run"] is True
        assert report["signal_kind"] == "contradiction_edge_marker_not_resolution"
        assert report["total"] == 1
        assert report["stale_count"] == 1
        assert report["recent_count"] == 0
        assert report["both_active_count"] == 1
        assert report["unresolved_active_count"] == 1
        assert report["orphan_count"] == 0
        sample = report["unresolved_active_samples"][0]
        assert sample["source_id"] == "P_CONTRA_NEW"
        assert sample["target_id"] == "P_CONTRA_OLD"
    finally:
        reset_vault()


def test_contradiction_audit_report_counts_orphan_edges_without_edge_id(tmp_path):
    vault = make_vault(tmp_path)
    try:
        create_node(vault, "P_CONTRA_EXISTING")
        vault._conn.execute(
            "INSERT INTO node_edges (source_id, target_id, relation, weight, created_at) VALUES (?, ?, ?, ?, ?)",
            ("P_CONTRA_EXISTING", "P_CONTRA_MISSING", "CONTRADICTS", 1.0, "2020-01-01 00:00:00"),
        )
        vault._conn.commit()

        report = vault.contradiction_audit_report(stale_days=30)

        assert report["total"] == 1
        assert report["orphan_count"] == 1
        assert report["both_active_count"] == 0
        assert report["unresolved_active_count"] == 0
        sample = report["orphan_samples"][0]
        assert sample["source_id"] == "P_CONTRA_EXISTING"
        assert sample["target_id"] == "P_CONTRA_MISSING"
        assert sample["source_exists"] is True
        assert sample["target_exists"] is False
    finally:
        reset_vault()


def test_contradiction_audit_report_excludes_hidden_edges_from_unresolved_active(tmp_path):
    vault = make_vault(tmp_path)
    try:
        create_node(vault, "P_CONTRA_VISIBLE")
        create_node(vault, "P_CONTRA_HIDDEN")
        assert vault.create_node_edge("P_CONTRA_VISIBLE", "P_CONTRA_HIDDEN", "CONTRADICTS")
        vault._conn.execute(
            "UPDATE knowledge_nodes SET ablation_active = 2 WHERE node_id = ?",
            ("P_CONTRA_HIDDEN",),
        )
        vault._conn.execute(
            "UPDATE node_edges SET created_at = ? WHERE source_id = ? AND target_id = ? AND relation = ?",
            ("2020-01-01 00:00:00", "P_CONTRA_VISIBLE", "P_CONTRA_HIDDEN", "CONTRADICTS"),
        )
        vault._conn.commit()

        report = vault.contradiction_audit_report(stale_days=30)

        assert report["total"] == 1
        assert report["stale_count"] == 1
        assert report["both_active_count"] == 0
        assert report["unresolved_active_count"] == 0
        assert report["unresolved_active_samples"] == []
    finally:
        reset_vault()
