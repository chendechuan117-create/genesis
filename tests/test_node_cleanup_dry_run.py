import sqlite3
from datetime import datetime, timedelta


def _create_cleanup_schema(conn):
    conn.execute(
        "CREATE TABLE knowledge_nodes ("
        "node_id TEXT PRIMARY KEY, type TEXT, title TEXT, usage_count INTEGER, "
        "usage_success_count INTEGER DEFAULT 0, usage_fail_count INTEGER DEFAULT 0, "
        "trust_tier TEXT, created_at TEXT)"
    )
    conn.execute("CREATE TABLE node_contents (node_id TEXT PRIMARY KEY, full_content TEXT)")
    conn.execute("CREATE TABLE node_edges (source_id TEXT, target_id TEXT, relation TEXT)")


def test_node_cleanup_dry_run_reports_candidates_without_deleting(tmp_path):
    from genesis.v4.trace_pipeline.node_cleanup import cleanup

    db_path = tmp_path / "workshop_v4.sqlite"
    old_created_at = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(str(db_path))
    try:
        _create_cleanup_schema(conn)
        conn.execute(
            "INSERT INTO knowledge_nodes (node_id, type, title, usage_count, trust_tier, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("LESSON_OLD", "LESSON", "old unused", 0, "REFLECTION", old_created_at),
        )
        conn.execute(
            "INSERT INTO node_contents (node_id, full_content) VALUES (?, ?)",
            ("LESSON_OLD", "content"),
        )
        conn.commit()
    finally:
        conn.close()

    result = cleanup(dry_run=True, db_path=db_path)

    assert result["dry_run"] is True
    assert result["would_delete"] == 1
    assert result["hard_deleted"] == 0

    conn = sqlite3.connect(str(db_path))
    try:
        remaining = conn.execute("SELECT COUNT(*) FROM knowledge_nodes WHERE node_id = ?", ("LESSON_OLD",)).fetchone()[0]
    finally:
        conn.close()

    assert remaining == 1


def test_purge_forgotten_knowledge_dry_run_does_not_delete(tmp_path):
    from genesis.v4.manager import NodeVault

    NodeVault._instance = None
    db_path = tmp_path / "vault.sqlite"
    db_path.touch()
    vault = NodeVault(db_path=db_path, skip_vector_engine=True)
    old_created_at = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    vault._conn.execute(
        "INSERT INTO knowledge_nodes (node_id, type, title, human_translation, usage_count, trust_tier, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("LESSON_PURGE_DRY", "LESSON", "purge dry", "purge dry", 0, "REFLECTION", old_created_at),
    )
    vault._conn.commit()

    try:
        candidates = vault.purge_forgotten_knowledge(days_threshold=7, dry_run=True)
        remaining = vault._conn.execute(
            "SELECT COUNT(*) FROM knowledge_nodes WHERE node_id = ?",
            ("LESSON_PURGE_DRY",),
        ).fetchone()[0]
    finally:
        vault._conn.close()
        NodeVault._instance = None

    assert candidates == 1
    assert remaining == 1
