import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "numpy" not in sys.modules:
    numpy_mod = types.ModuleType("numpy")
    numpy_mod.ndarray = list
    numpy_mod.array = lambda x, *a, **k: x
    numpy_mod.asarray = lambda x, *a, **k: x
    numpy_mod.float32 = float
    sys.modules["numpy"] = numpy_mod

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


class ManagerInvalidationReasonRegressionTest(unittest.TestCase):
    def setUp(self):
        _reset_singletons()
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmpdir.name) / "vault.sqlite"
        db_path.touch()
        self.vault = NodeVault(
            db_path=db_path,
            skip_vector_engine=True,
        )

    def tearDown(self):
        try:
            self.vault._conn.close()
        except Exception:
            pass
        self._tmpdir.cleanup()
        _reset_singletons()

    def _create_node(self, node_id, ntype, metadata_signature, verification_source=None):
        self.vault.create_node(
            node_id=node_id,
            ntype=ntype,
            title=node_id,
            human_translation=node_id,
            tags="regression",
            full_content=f"{node_id} content",
            source="reflection",
            metadata_signature=metadata_signature,
            verification_source=verification_source,
        )

    def _signature_text(self, node_id):
        row = self.vault._conn.execute(
            "SELECT metadata_signature FROM knowledge_nodes WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        return row[0] if row and row[0] else "{}"

    def _signature_dict(self, node_id):
        return json.loads(self._signature_text(node_id))

    def _seed_legacy_nodes(self):
        first = self.vault.activate_environment_epoch("doctor_workspace", origin="legacy_first")
        self.vault.activate_environment_epoch("doctor_workspace", origin="legacy_second")
        self._create_node(
            node_id="LESSON_LEGACY_AUDIT",
            ntype="LESSON",
            metadata_signature={"validation_status": "outdated"},
            verification_source="auditor_daemon",
        )
        self._create_node(
            node_id="CTX_LEGACY_ENV",
            ntype="CONTEXT",
            metadata_signature={
                "validation_status": "outdated",
                "knowledge_state": "historical",
                "applies_to_environment_scope": "doctor_workspace",
                "applies_to_environment_epoch": first["epoch_id"],
            },
        )
        return first["epoch_id"]

    def test_build_reliability_profile_infers_legacy_invalidation_reason(self):
        self._seed_legacy_nodes()
        self.assertNotIn("invalidation_reason", self._signature_text("LESSON_LEGACY_AUDIT"))
        self.assertNotIn("invalidation_reason", self._signature_text("CTX_LEGACY_ENV"))

        briefs = self.vault.get_node_briefs(["LESSON_LEGACY_AUDIT", "CTX_LEGACY_ENV"])
        audit_reliability = self.vault.build_reliability_profile(briefs["LESSON_LEGACY_AUDIT"])
        env_reliability = self.vault.build_reliability_profile(briefs["CTX_LEGACY_ENV"])

        self.assertEqual(audit_reliability["invalidation_reason"], "audit_outdated")
        self.assertEqual(env_reliability["invalidation_reason"], "superseded_env")
        self.assertTrue(env_reliability["epoch_stale"])

    def test_patch_node_metadata_backfills_audit_reason(self):
        self._create_node(
            node_id="LESSON_PATCH_TARGET",
            ntype="LESSON",
            metadata_signature={"validation_status": "validated"},
        )

        patched = self.vault.patch_node_metadata(
            "LESSON_PATCH_TARGET",
            metadata_signature={"validation_status": "outdated"},
            verification_source="auditor_daemon",
        )

        self.assertTrue(patched)
        patched_sig = self._signature_dict("LESSON_PATCH_TARGET")
        self.assertEqual(patched_sig.get("invalidation_reason"), "audit_outdated")
        self.assertEqual(patched_sig.get("validation_status"), "outdated")
        self.assertEqual(patched_sig.get("knowledge_state"), "historical")

    def test_audit_signatures_backfills_reason_and_reports_stats(self):
        self._seed_legacy_nodes()

        stats = self.vault.audit_signatures(limit=20)

        self.assertGreaterEqual(stats.get("audited", 0), 2)
        self.assertGreaterEqual(stats.get("fixed_invalidation_reason", 0), 2)
        self.assertEqual(self._signature_dict("LESSON_LEGACY_AUDIT").get("invalidation_reason"), "audit_outdated")
        self.assertEqual(self._signature_dict("CTX_LEGACY_ENV").get("invalidation_reason"), "superseded_env")


if __name__ == "__main__":
    unittest.main()
