import sqlite3
import time


def test_assess_evidence_dry_run_does_not_mutate_arena_counts(tmp_path, monkeypatch):
    import genesis.v4.manager as manager
    from genesis.v4.trace_pipeline import entity_store
    from genesis.v4.trace_pipeline.evidence_assessor import assess_evidence

    vault_path = tmp_path / "workshop_v4.sqlite"
    vault_conn = sqlite3.connect(str(vault_path))
    try:
        vault_conn.execute(
            "CREATE TABLE knowledge_nodes ("
            "node_id TEXT PRIMARY KEY, title TEXT, type TEXT, resolves TEXT, "
            "usage_success_count INTEGER DEFAULT 0, usage_fail_count INTEGER DEFAULT 0, "
            "updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        vault_conn.execute(
            "INSERT INTO knowledge_nodes "
            "(node_id, title, type, resolves, usage_success_count, usage_fail_count) "
            "VALUES ('LESSON_PASSIVE', 'passive evidence lesson', 'LESSON', 'alpha beta failure', 0, 0)"
        )
        vault_conn.commit()
    finally:
        vault_conn.close()

    monkeypatch.setattr(manager, "DB_PATH", vault_path)
    monkeypatch.setattr(manager, "_LEGACY_DB_PATH", tmp_path / "legacy.sqlite")
    monkeypatch.setattr(entity_store, "_DB_PATH", tmp_path / "trace_entities.sqlite")

    store = entity_store.TraceEntityStore()
    try:
        trace_conn = store._get_conn()
        old_ts = time.time() - 10 * 86400
        trace_conn.execute(
            "INSERT INTO canonical_entities "
            "(entity_type, value, first_seen_at, last_seen_at, occurrence_count, session_count, avg_confidence) "
            "VALUES ('ERROR', 'alpha beta failure', ?, ?, 1, 1, 1.0)",
            (old_ts, old_ts),
        )
        trace_conn.commit()
    finally:
        store.close()

    result = assess_evidence()

    assert result["write_mode"] == "dry_run"
    assert result["reinforced"][0]["node_id"] == "LESSON_PASSIVE"
    assert result["reinforced"][0]["applied"] is False
    assert result["reinforced"][0]["source"] == "passive_evidence"

    check_conn = sqlite3.connect(str(vault_path))
    try:
        counts = check_conn.execute(
            "SELECT usage_success_count, usage_fail_count FROM knowledge_nodes WHERE node_id = 'LESSON_PASSIVE'"
        ).fetchone()
    finally:
        check_conn.close()
    assert counts == (0, 0)


def test_assess_evidence_empty_lesson_set_still_reports_dry_run(tmp_path, monkeypatch):
    import genesis.v4.manager as manager
    from genesis.v4.trace_pipeline import entity_store
    from genesis.v4.trace_pipeline.evidence_assessor import assess_evidence

    vault_path = tmp_path / "workshop_v4.sqlite"
    vault_conn = sqlite3.connect(str(vault_path))
    try:
        vault_conn.execute(
            "CREATE TABLE knowledge_nodes ("
            "node_id TEXT PRIMARY KEY, title TEXT, type TEXT, resolves TEXT, "
            "usage_success_count INTEGER DEFAULT 0, usage_fail_count INTEGER DEFAULT 0)"
        )
        vault_conn.commit()
    finally:
        vault_conn.close()

    monkeypatch.setattr(manager, "DB_PATH", vault_path)
    monkeypatch.setattr(manager, "_LEGACY_DB_PATH", tmp_path / "legacy.sqlite")
    monkeypatch.setattr(entity_store, "_DB_PATH", tmp_path / "trace_entities.sqlite")

    result = assess_evidence()

    assert result == {"reinforced": [], "weakened": [], "neutral_count": 0, "write_mode": "dry_run"}
