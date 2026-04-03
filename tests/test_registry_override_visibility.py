import logging

import pytest

from genesis.core.base import Tool
from genesis.core.registry import ToolRegistry, _tool_fingerprint


class GoodRecordLessonTool(Tool):
    @property
    def name(self) -> str:
        return "record_lesson_node"

    @property
    def description(self) -> str:
        return "good tool"

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

    async def execute(
        self,
        node_id=None,
        title=None,
        trigger_verb=None,
        trigger_noun=None,
        trigger_context=None,
        action_steps=None,
        because_reason=None,
        **_,
    ) -> str:
        return f"OK:{node_id}:{title}:{trigger_verb}:{trigger_noun}:{trigger_context}:{len(action_steps or [])}:{because_reason}"


class LegacyArityRecordLessonTool(Tool):
    @property
    def name(self) -> str:
        return "record_lesson_node"

    @property
    def description(self) -> str:
        return "legacy arity tool"

    @property
    def parameters(self) -> dict:
        return GoodRecordLessonTool().parameters

    async def execute(
        self,
        node_id,
        title,
        trigger_verb,
        trigger_noun,
        trigger_context,
        action_steps,
        because_reason,
    ) -> str:
        return "LEGACY"


class ClassObjectPollutionTool(GoodRecordLessonTool):
    pass


@pytest.mark.asyncio
async def test_registry_duplicate_registration_logs_before_after_fingerprints(caplog):
    reg = ToolRegistry()
    good = GoodRecordLessonTool()
    bad = LegacyArityRecordLessonTool()

    reg.register(good)
    with caplog.at_level(logging.WARNING):
        reg.register(bad)

    joined = "\n".join(caplog.messages)
    assert "已存在，将被覆盖" in joined
    assert "before={" in joined
    assert "after={" in joined
    assert "execute_signature" in joined
    assert "schema_required" in joined
    assert "GoodRecordLessonTool" in joined
    assert "LegacyArityRecordLessonTool" in joined


@pytest.mark.asyncio
async def test_registry_execute_logs_active_fingerprint_for_legacy_override_arity(caplog):
    reg = ToolRegistry()
    reg.register(GoodRecordLessonTool())
    reg.register(LegacyArityRecordLessonTool())

    payload = {
        "node_id": "N1",
        "title": "T",
        "trigger_verb": "audit",
        "trigger_noun": "registry",
        "trigger_context": "doctor",
        "action_steps": ["step"],
        "because_reason": "why",
    }

    with caplog.at_level(logging.ERROR):
        result = await reg.execute("record_lesson_node", payload)

    assert "unexpected keyword argument 'node_id'" in result
    joined = "\n".join(caplog.messages)
    assert "active_tool={" in joined
    assert "LegacyArityRecordLessonTool" in joined
    assert "execute_signature" in joined
    assert "(node_id, title, trigger_verb, trigger_noun, trigger_context, action_steps, because_reason)" in joined


@pytest.mark.asyncio
async def test_registry_execute_logs_active_fingerprint_for_class_object_pollution(caplog):
    reg = ToolRegistry()
    reg.register(GoodRecordLessonTool())
    reg.register(ClassObjectPollutionTool)

    payload = {
        "node_id": "N1",
        "title": "T",
        "trigger_verb": "audit",
        "trigger_noun": "registry",
        "trigger_context": "doctor",
        "action_steps": ["step"],
        "because_reason": "why",
    }

    with caplog.at_level(logging.ERROR):
        result = await reg.execute("record_lesson_node", payload)

    assert "missing 1 required positional argument: 'self'" in result
    joined = "\n".join(caplog.messages)
    assert "tool_type" in joined
    assert "type" in joined
    assert "execute_is_bound" in joined
    assert "False" in joined


def test_tool_fingerprint_reports_bound_and_unbound_shapes():
    good_fp = _tool_fingerprint(GoodRecordLessonTool())
    class_fp = _tool_fingerprint(ClassObjectPollutionTool)

    assert good_fp["execute_is_bound"] is True
    assert class_fp["execute_is_bound"] is False
    assert "GoodRecordLessonTool.execute" in str(good_fp["execute_func_qualname"])
    assert class_fp["tool_type"] == "ABCMeta"
