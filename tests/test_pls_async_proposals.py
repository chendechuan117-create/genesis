import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from genesis.v4.manager import NodeVault
from genesis.v4.vector_engine import VectorEngine


def _reset_singletons():
    inst = getattr(NodeVault, "_instance", None)
    if inst is not None:
        conn = getattr(inst, "_conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    NodeVault._instance = None
    VectorEngine._instance = None
    VectorEngine._model = None
    VectorEngine._reranker = None


class PLSAsyncProposalRegressionTest(unittest.TestCase):
    def setUp(self):
        _reset_singletons()
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmpdir.name) / "vault.sqlite"
        db_path.touch()
        self.vault = NodeVault(db_path=db_path, skip_vector_engine=True)
        row = self.vault._conn.execute(
            "SELECT node_id FROM knowledge_nodes WHERE node_id LIKE 'SEED_CTX_%' LIMIT 1"
        ).fetchone()
        self.seed_id = row[0]

    def tearDown(self):
        try:
            self.vault._conn.close()
        except Exception:
            pass
        self._tmpdir.cleanup()
        _reset_singletons()

    def _counts(self):
        return {
            table: self.vault._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in [
                "knowledge_nodes",
                "reasoning_lines",
                "node_edges",
                "potential_samples",
                "pls_proposals",
            ]
        }

    def test_staging_validation_and_preview_do_not_write_main_topology(self):
        base_counts = self._counts()
        recorded = self.vault.record_pls_proposal(
            "proposal-preview-ok",
            "branch_candidate",
            {
                "node_id": "P_ASYNC_PREVIEW_ONLY",
                "title": "Async preview proposal",
                "content": "A staged proposal that must stay dry-run until explicit commit.",
                "point_type": "CONTEXT",
                "tags": "async_proposal,test",
                "reasoning": "The existing seed is only a rechecked basis for the preview.",
            },
            basis_ids=[self.seed_id, self.seed_id],
            parent_trace_id="trace-preview",
            parent_round_seq=2,
            branch_id="basis_branch",
        )

        self.assertTrue(recorded)
        proposals = self.vault.get_pls_proposals(limit=10)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["basis_ids"], [self.seed_id])
        self.assertEqual(proposals[0]["payload"]["schema_version"], 1)
        self.assertEqual(proposals[0]["payload"]["node_id"], "P_ASYNC_PREVIEW_ONLY")
        self.assertEqual(proposals[0]["payload"]["basis_ids"], [self.seed_id])

        validation = self.vault.validate_pls_proposal("proposal-preview-ok", update_status=True)
        self.assertTrue(validation["ok"])
        self.assertEqual(validation["recommended_status"], "validated")

        preview = self.vault.preview_pls_proposal_merge("proposal-preview-ok")
        self.assertTrue(preview["ok"])
        self.assertEqual([op["op"] for op in preview["operations"]], ["planned_point_write", "planned_line_write"])
        self.assertEqual(preview["operations"][0]["point_type"], "CONTEXT")

        after_counts = self._counts()
        self.assertEqual(after_counts["pls_proposals"], base_counts["pls_proposals"] + 1)
        for table in ["knowledge_nodes", "reasoning_lines", "node_edges", "potential_samples"]:
            self.assertEqual(after_counts[table], base_counts[table], table)

    def test_payload_schema_normalizes_aliases_and_rejects_internal_metrics(self):
        recorded = self.vault.record_pls_proposal(
            "proposal-aliases",
            "branch_candidate",
            {
                "new_point_id": "P_ALIAS_NORMALIZED",
                "summary": "Alias title",
                "detail": "Alias content.",
                "line_reasoning": "Alias reasoning.",
                "target_basin": "alias basin",
                "basis_ids": [self.seed_id, self.seed_id],
            },
            parent_trace_id="trace-alias",
            parent_round_seq=4,
            branch_id="basis_branch",
        )
        self.assertTrue(recorded)
        proposal = self.vault.get_pls_proposals(branch_id="basis_branch", limit=10)[0]
        self.assertEqual(proposal["payload"]["node_id"], "P_ALIAS_NORMALIZED")
        self.assertEqual(proposal["payload"]["title"], "Alias title")
        self.assertEqual(proposal["payload"]["content"], "Alias content.")
        self.assertEqual(proposal["payload"]["point_type"], "CONTEXT")
        self.assertEqual(proposal["payload"]["reasoning"], "Alias reasoning.")
        self.assertEqual(proposal["payload"]["resolves"], "alias basin")
        self.assertEqual(proposal["basis_ids"], [self.seed_id])
        self.assertEqual(proposal["schema_issues"], [])

        rejected_metric = self.vault.record_pls_proposal(
            "proposal-metric-leak",
            "branch_candidate",
            {"node_id": "P_BAD_METRIC", "title": "Bad", "content": "Bad.", "incoming_count": 3},
            basis_ids=[self.seed_id],
            branch_id="basis_branch",
        )
        self.assertFalse(rejected_metric)

        rejected_type = self.vault.record_pls_proposal(
            "proposal-invalid-type",
            "branch_candidate",
            {"node_id": "P_BAD_TYPE", "title": "Bad", "content": "Bad.", "point_type": "FACT"},
            basis_ids=[self.seed_id],
            branch_id="basis_branch",
        )
        self.assertFalse(rejected_type)

    def test_validation_marks_missing_same_generation_and_duplicate_candidates(self):
        self.vault.record_pls_proposal(
            "proposal-missing-basis",
            "branch_candidate",
            {"node_id": "P_MISSING_BASIS", "title": "Missing basis", "content": "Missing basis."},
            basis_ids=["NO_SUCH_BASIS"],
            parent_trace_id="trace-x",
            parent_round_seq=1,
            branch_id="frontier_branch",
        )
        missing = self.vault.validate_pls_proposal("proposal-missing-basis", update_status=True)
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["recommended_status"], "needs_rebase")
        self.assertIn("missing_basis:NO_SUCH_BASIS", missing["reasons"])

        self.vault.record_node_creation_context(self.seed_id, trace_id="trace-x", round_seq=1)
        self.vault.record_pls_proposal(
            "proposal-same-generation",
            "branch_candidate",
            {"node_id": "P_SAME_GENERATION", "title": "Same generation", "content": "Same generation."},
            basis_ids=[self.seed_id],
            parent_trace_id="trace-x",
            parent_round_seq=1,
            branch_id="frontier_branch",
        )
        same_generation = self.vault.validate_pls_proposal("proposal-same-generation", update_status=True)
        self.assertFalse(same_generation["ok"])
        self.assertEqual(same_generation["recommended_status"], "unsafe_same_generation")
        self.assertIn("basis_from_same_generation", same_generation["reasons"])

        self.vault.record_pls_proposal(
            "proposal-duplicate",
            "branch_candidate",
            {"node_id": self.seed_id, "title": "Duplicate", "content": "Duplicate."},
            basis_ids=[self.seed_id],
            parent_trace_id="trace-x",
            parent_round_seq=2,
            branch_id="basis_branch",
        )
        duplicate = self.vault.validate_pls_proposal("proposal-duplicate", update_status=True)
        self.assertFalse(duplicate["ok"])
        self.assertEqual(duplicate["recommended_status"], "duplicate")
        self.assertIn("candidate_node_already_exists", duplicate["reasons"])

    def test_preview_reports_missing_payload_fields_without_writes(self):
        base_counts = self._counts()
        self.vault.record_pls_proposal(
            "proposal-incomplete",
            "branch_candidate",
            {"node_id": "P_INCOMPLETE"},
            basis_ids=[self.seed_id],
            parent_trace_id="trace-preview",
            parent_round_seq=3,
            branch_id="basis_branch",
        )
        preview = self.vault.preview_pls_proposal_merge("proposal-incomplete")
        self.assertFalse(preview["ok"])
        self.assertIn("missing_title", preview["blockers"])
        self.assertIn("missing_content", preview["blockers"])
        self.assertIn("missing_line_reasoning", preview["blockers"])

        after_counts = self._counts()
        self.assertEqual(after_counts["pls_proposals"], base_counts["pls_proposals"] + 1)
        for table in ["knowledge_nodes", "reasoning_lines", "node_edges", "potential_samples"]:
            self.assertEqual(after_counts[table], base_counts[table], table)

    def test_pls_query_proposals_is_read_only(self):
        import asyncio

        from genesis.tools.pls_query_tool import PLSQueryTool

        base_counts = self._counts()
        self.vault.record_pls_proposal(
            "proposal-query",
            "branch_candidate",
            {"node_id": "P_QUERY_PREVIEW", "title": "Query proposal", "content": "Query only.", "reasoning": "Read-only."},
            basis_ids=[self.seed_id],
            parent_trace_id="trace-query",
            parent_round_seq=5,
            branch_id="basis_branch",
        )
        result = asyncio.run(
            PLSQueryTool().execute(mode="proposals", query="basis_branch", limit=5, db_path=str(self.vault.db_path))
        )
        self.assertIn("PLS异步候选暂存", result)
        self.assertIn("proposal-query", result)
        self.assertIn("proposal 不是事实", result)
        after_counts = self._counts()
        self.assertEqual(after_counts["pls_proposals"], base_counts["pls_proposals"] + 1)
        for table in ["knowledge_nodes", "reasoning_lines", "node_edges", "potential_samples"]:
            self.assertEqual(after_counts[table], base_counts[table], table)

    def test_async_branch_worker_stages_direction_only_proposals(self):
        import asyncio

        from genesis.tools import pls_async_scout

        base_counts = self._counts()

        async def fake_collect(limit, since, modes):
            return {
                "basis": ["concept seed without numeric metrics"],
                "frontier": ["frontier gap without numeric metrics"],
            }

        with patch.object(pls_async_scout, "_collect_branch_sections", fake_collect):
            summary = asyncio.run(
                pls_async_scout.stage_pls_branch_proposals(
                    parent_trace_id="trace-worker",
                    parent_round_seq=6,
                    limit=2,
                    db_path=str(self.vault.db_path),
                )
            )
        self.assertIn("已暂存", summary)
        proposals = self.vault.get_pls_proposals(status="pending", limit=10)
        self.assertEqual(len(proposals), 2)
        self.assertEqual({p["source"] for p in proposals}, {"async_branch_worker"})
        self.assertEqual({p["payload"]["point_type"] for p in proposals}, {"CONTEXT"})
        validation = self.vault.validate_pls_proposal(proposals[0]["proposal_id"], update_status=False)
        self.assertFalse(validation["ok"])
        self.assertEqual(validation["recommended_status"], "needs_rebase")
        self.assertIn("missing_basis_ids", validation["reasons"])
        after_counts = self._counts()
        self.assertEqual(after_counts["pls_proposals"], base_counts["pls_proposals"] + 2)
        for table in ["knowledge_nodes", "reasoning_lines", "node_edges", "potential_samples"]:
            self.assertEqual(after_counts[table], base_counts[table], table)

    def test_async_branch_worker_explicit_db_path_bypasses_nodevault_singleton(self):
        import asyncio
        import sqlite3

        from genesis.tools import pls_async_scout

        other_db = Path(self._tmpdir.name) / "other.sqlite"
        other_db.touch()

        async def fake_collect(limit, since, modes):
            return {"basis": ["singleton bypass seed"]}

        with patch.object(pls_async_scout, "_collect_branch_sections", fake_collect):
            summary = asyncio.run(
                pls_async_scout.stage_pls_branch_proposals(
                    parent_trace_id="trace-singleton",
                    parent_round_seq=7,
                    limit=1,
                    db_path=str(other_db),
                )
            )
            duplicate_summary = asyncio.run(
                pls_async_scout.stage_pls_branch_proposals(
                    parent_trace_id="trace-singleton",
                    parent_round_seq=7,
                    limit=1,
                    db_path=str(other_db),
                )
            )

        self.assertIn("已暂存 1 条候选", summary)
        self.assertEqual(duplicate_summary, "")
        self.assertEqual(self.vault._conn.execute("SELECT COUNT(*) FROM pls_proposals").fetchone()[0], 0)
        conn = sqlite3.connect(other_db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM pls_proposals").fetchone()[0]
            source = conn.execute("SELECT source FROM pls_proposals").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 1)
        self.assertEqual(source, "async_branch_worker")

        result = asyncio.run(
            __import__("genesis.tools.pls_query_tool", fromlist=["PLSQueryTool"]).PLSQueryTool().execute(
                mode="proposals",
                query="all",
                db_path=str(other_db),
            )
        )
        self.assertIn("PLS异步候选暂存", result)
        self.assertIn("trace-singleton", result)

    def test_legacy_pls_proposals_table_migrates_before_indexes(self):
        import asyncio
        import sqlite3

        from genesis.tools import pls_async_scout
        from genesis.tools.pls_query_tool import PLSQueryTool

        legacy_db = Path(self._tmpdir.name) / "legacy_proposals.sqlite"
        conn = sqlite3.connect(legacy_db)
        try:
            conn.execute(
                "CREATE TABLE pls_proposals ("
                "proposal_id TEXT PRIMARY KEY, "
                "proposal_type TEXT NOT NULL, "
                "payload_json TEXT NOT NULL, "
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                ")"
            )
            conn.commit()
        finally:
            conn.close()

        async def fake_collect(limit, since, modes):
            return {"basis": ["legacy migration seed"]}

        with patch.object(pls_async_scout, "_collect_branch_sections", fake_collect):
            summary = asyncio.run(
                pls_async_scout.stage_pls_branch_proposals(
                    parent_trace_id="trace-legacy",
                    parent_round_seq=8,
                    limit=1,
                    db_path=str(legacy_db),
                )
            )

        self.assertIn("已暂存 1 条候选", summary)
        conn = sqlite3.connect(legacy_db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(pls_proposals)").fetchall()}
            indexes = {r[1] for r in conn.execute("PRAGMA index_list(pls_proposals)").fetchall()}
        finally:
            conn.close()
        self.assertTrue({"status", "branch_id", "parent_trace_id", "parent_round_seq", "basis_ids_json", "merge_result"}.issubset(cols))
        self.assertIn("idx_pls_proposals_status_created", indexes)
        result = asyncio.run(PLSQueryTool().execute(mode="proposals", query="all", db_path=str(legacy_db)))
        self.assertIn("trace-legacy", result)

    def test_potential_guardrail_metrics_are_not_branch_seeds(self):
        from genesis.tools import pls_async_scout

        raw = """
[PLS DB] /tmp/vault.sqlite
=== PLS势样本 / potential samples ===
-- lifecycle guardrails --
total=26479 missing_dedupe=26360 active_open=26008 actionable_open=2497 non_actionable_open=23511
-- distribution --
structural | open | knowledge_routing / saturation: rows=7978 seen=7978
exit | observed | search_knowledge_nodes / co_presence: rows=8 seen=8
-- recent samples --
2026-05-11 07:42:00 | actionable | open | seen=2 | search_knowledge_nodes / missing_basis | 当前面缺少基础锚点
2026-05-11 07:44:21 | actionable | open | seen=3 | last_seen=2026-05-11 07:44:21 | knowledge_routing / missing_basis | 另一个基础锚点
  dedupe: 2fbbb239e495
  detail: 需要复查 basis
"""
        compacted = pls_async_scout._compact_section("potential", raw, limit=4)
        self.assertEqual(compacted[0], "当前面缺少基础锚点")
        self.assertIn("另一个基础锚点", compacted)
        self.assertFalse(any("missing_dedupe" in item or "rows=" in item or "last_seen=" in item or "dedupe:" in item for item in compacted))
        specs = pls_async_scout._branch_specs({"potential": compacted})
        exit_specs = [spec for spec in specs if spec["branch_id"] == "exit_branch"]
        self.assertEqual(exit_specs[0]["seed"], "当前面缺少基础锚点")
        self.assertNotIn("missing_dedupe", exit_specs[0]["seed"])


if __name__ == "__main__":
    unittest.main()
