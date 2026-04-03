import hashlib
import json
from genesis.core.base import Tool


class FakeRecordLessonTool(Tool):
    @property
    def name(self) -> str:
        return "record_lesson_node"

    @property
    def description(self) -> str:
        return "fake"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "title": {"type": "string"},
                "trigger_verb": {"type": "string"},
                "trigger_noun": {"type": "string"},
                "trigger_context": {"type": "string"},
                "action_steps": {"type": "array", "items": {"type": "string"}},
                "because_reason": {"type": "string"},
            },
            "required": [
                "node_id",
                "title",
                "trigger_verb",
                "trigger_noun",
                "trigger_context",
                "action_steps",
                "because_reason",
            ],
        }

    async def execute(self, **kwargs) -> str:
        return "ok"


def test_to_schema_includes_contract_fingerprint_and_source_metadata():
    schema = FakeRecordLessonTool().to_schema()
    function = schema["function"]

    assert function["x-tool-source"] == "test_record_lesson_contract_fingerprint.FakeRecordLessonTool"
    assert function["x-tool-contract-version"] == 1
    assert len(function["x-tool-contract-fingerprint"]) == 64

    stable_basis = {
        "name": function["name"],
        "description": function["description"],
        "parameters": function["parameters"],
    }
    encoded = json.dumps(stable_basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert function["x-tool-contract-fingerprint"] == hashlib.sha256(encoded.encode("utf-8")).hexdigest()
