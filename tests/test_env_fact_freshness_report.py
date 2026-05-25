import json
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


def create_env_fact(vault, node_id, subject, description, last_verified_at=None):
    vault.create_node(
        node_id=node_id,
        ntype="DISCOVERY",
        title=f"[ENV_FACT] {subject}: {description}",
        human_translation=f"{subject}: {description}",
        tags="discovery,env_fact,test",
        full_content=json.dumps({
            "category": "ENV_FACT",
            "subject": subject,
            "description": description,
            "evidence_tool": "shell",
        }),
        resolves=subject,
        metadata_signature={
            "category": "ENV_FACT",
            "subject": subject,
            "evidence_tool": "shell",
            "observed_at": "2026-05-01 00:00",
        },
        last_verified_at=last_verified_at,
        verification_source="shell" if last_verified_at else None,
    )


def test_env_fact_freshness_report_counts_unverified_and_mismatch_without_writes(tmp_path):
    vault = make_vault(tmp_path)
    try:
        create_env_fact(
            vault,
            "DISC_ENV_OLD_CWD",
            "runtime.cwd",
            "cwd=/old/workspace user=olduser",
        )
        before = vault._conn.execute(
            "SELECT updated_at, last_verified_at FROM knowledge_nodes WHERE node_id = ?",
            ("DISC_ENV_OLD_CWD",),
        ).fetchone()

        report = vault.env_fact_freshness_report(
            stale_days=7,
            current_runtime={
                "cwd": "/home/yoga/Genesis",
                "home": "/home/yoga",
                "user": "yoga",
                "host": "yoga",
            },
        )

        after = vault._conn.execute(
            "SELECT updated_at, last_verified_at FROM knowledge_nodes WHERE node_id = ?",
            ("DISC_ENV_OLD_CWD",),
        ).fetchone()
        assert dict(before) == dict(after)
        assert report["dry_run"] is True
        assert report["signal_kind"] == "env_fact_freshness_not_revalidation"
        assert report["total"] == 1
        assert report["unverified_count"] == 1
        assert report["stale_or_unverified_count"] == 1
        assert report["current_anchor_count"] == 1
        assert report["mismatch_candidate_count"] == 1
        fields = {m["field"] for m in report["mismatch_candidates"][0]["mismatches"]}
        assert "cwd" in fields
        assert "user" in fields
    finally:
        reset_vault()


def test_env_fact_freshness_report_counts_stale_verified_fact(tmp_path):
    vault = make_vault(tmp_path)
    try:
        old_verified_at = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        create_env_fact(
            vault,
            "DISC_ENV_STALE_HOME",
            "runtime.home",
            "home=/home/yoga",
            last_verified_at=old_verified_at,
        )

        report = vault.env_fact_freshness_report(
            stale_days=7,
            current_runtime={
                "cwd": "/home/yoga/Genesis",
                "home": "/home/yoga",
                "user": "yoga",
                "host": "yoga",
            },
        )

        assert report["total"] == 1
        assert report["unverified_count"] == 0
        assert report["stale_verified_count"] == 1
        assert report["stale_or_unverified_count"] == 1
        sample = report["stale_or_unverified_samples"][0]
        assert sample["node_id"] == "DISC_ENV_STALE_HOME"
        assert sample["freshness_state"] == "stale"
    finally:
        reset_vault()


def test_env_fact_freshness_report_ignores_non_env_discovery(tmp_path):
    vault = make_vault(tmp_path)
    try:
        vault.create_node(
            node_id="DISC_TOOL_BEHAVIOR",
            ntype="DISCOVERY",
            title="[TOOL_BEHAVIOR] shell: ok",
            human_translation="shell ok",
            tags="discovery,tool_behavior,test",
            full_content=json.dumps({
                "category": "TOOL_BEHAVIOR",
                "subject": "shell.exec",
                "description": "ok",
                "evidence_tool": "shell",
            }),
            resolves="shell.exec",
            metadata_signature={"category": "TOOL_BEHAVIOR", "subject": "shell.exec"},
        )

        report = vault.env_fact_freshness_report(stale_days=7)

        assert report["total"] == 0
        assert report["stale_or_unverified_samples"] == []
        assert report["mismatch_candidates"] == []
    finally:
        reset_vault()
