import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from genesis import mcp_server


class MCPServerMetadataRegressionTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old_db_dir = mcp_server.DB_DIR
        self._old_db_path = mcp_server.DB_PATH
        mcp_server.DB_DIR = Path(self._tmpdir.name)
        mcp_server.DB_PATH = Path(self._tmpdir.name) / "code_observations.sqlite"
        self.conn = mcp_server._init_db()

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass
        mcp_server.DB_DIR = self._old_db_dir
        mcp_server.DB_PATH = self._old_db_path
        self._tmpdir.cleanup()

    def _record(self, **overrides):
        payload = {
            "type": "CONSTRAINT",
            "title": "Parser assumes canonical workspace scope",
            "content": "parser.py:88 expects doctor_workspace aliases to be normalized",
            "signature": {
                "component": "parser",
                "language": "python",
                "observed_environment_scope": "doctor",
                "environment_scope": "workspace",
                "validation_status": "verified",
            },
        }
        payload.update(overrides)
        result = mcp_server.record_code_observation(self.conn, payload)
        return json.loads(result)

    def _get_observation(self, obs_id):
        result = mcp_server.get_observation(self.conn, {"id": obs_id})
        return json.loads(result)

    def test_record_normalizes_metadata_v2_fields(self):
        recorded = self._record()
        signature = recorded["signature"]

        self.assertEqual(signature.get("metadata_schema_version"), "2")
        self.assertEqual(signature.get("observed_environment_scope"), "doctor_workspace")
        self.assertEqual(signature.get("applies_to_environment_scope"), "doctor_workspace")
        self.assertEqual(signature.get("environment_scope"), "doctor_workspace")
        self.assertEqual(signature.get("validation_status"), "validated")

        fetched = self._get_observation(recorded["id"])
        self.assertEqual(fetched["signature"].get("metadata_schema_version"), "2")
        self.assertEqual(fetched["signature"].get("applies_to_environment_scope"), "doctor_workspace")

    def test_structured_search_and_digest_surface_metadata_lanes(self):
        first = self._record()
        second = self._record(
            title="Planner depends on runtime config",
            content="planner.py:42 reads runtime mode",
            signature={
                "component": "planner",
                "language": "python",
                "applies_to_environment_scope": "doctor_workspace",
                "validation_status": "partial",
            },
        )

        results = mcp_server.search_code_observations(
            self.conn,
            {
                "signature": {"component": "parser", "language": "python"},
                "observed_environment_scope": "doctor",
            },
        )
        self.assertIn(first["id"], results)
        self.assertIn("component=parser", results)
        self.assertNotIn(second["id"], results)

        digest = mcp_server.get_code_digest(self.conn, {})
        self.assertIn("Metadata Lanes:", digest)
        self.assertIn("Structured search:", digest)
        self.assertIn("component: parser(1) | planner(1)", digest)

    def test_invalidate_and_verify_keep_metadata_state_in_sync(self):
        recorded = self._record(signature={"component": "parser"})
        obs_id = recorded["id"]

        invalidated = json.loads(
            mcp_server.invalidate_observation(
                self.conn,
                {"id": obs_id, "reason": "refactor removed old parser path"},
            )
        )
        invalid_sig = invalidated["signature"]
        self.assertEqual(invalid_sig.get("invalidation_reason"), "manual_outdated")
        self.assertEqual(invalid_sig.get("validation_status"), "outdated")
        self.assertEqual(invalid_sig.get("knowledge_state"), "historical")
        self.assertEqual(invalid_sig.get("invalidation_note"), "refactor removed old parser path")

        verified = json.loads(
            mcp_server.verify_observation(
                self.conn,
                {"id": obs_id, "source": "code_review"},
            )
        )
        verified_sig = verified["signature"]
        self.assertEqual(verified_sig.get("validation_status"), "validated")
        self.assertEqual(verified_sig.get("knowledge_state"), "current")
        self.assertNotIn("invalidation_reason", verified_sig)
        self.assertNotIn("invalidation_note", verified_sig)


if __name__ == "__main__":
    unittest.main()
