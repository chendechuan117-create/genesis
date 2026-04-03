#!/usr/bin/env python3
"""C 阶段调用级探针：验证最小 trace 契约与 call_index 绑定。"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from genesis.core.base import Tool, ToolCall
from genesis.core.tracer import Tracer
import genesis.v4.loop as loop_mod

BASE = PROJECT_ROOT
DB_PATH = BASE / "runtime" / "traces.db"


class SilentNodeVault:
    def __init__(self, *args, **kwargs):
        pass

    def infer_metadata_signature(self, text: str) -> Dict[str, Any]:
        return {}

    def learn_signature_marker(self, *args, **kwargs):
        return None


class SilentFactoryManager:
    def __init__(self, *args, **kwargs):
        pass


class SilentBlackboard:
    _persona_stats = None

    @classmethod
    def load_from_db(cls):
        return None

    @classmethod
    def get_persona_stats(cls):
        return None

    @staticmethod
    def suggest_persona_swap(base, task_kind, all_personas):
        return base


loop_mod.NodeVault = SilentNodeVault
loop_mod.FactoryManager = SilentFactoryManager
loop_mod.Blackboard = SilentBlackboard
V4Loop = loop_mod.V4Loop


class DummyResponse:
    def __init__(self, content: str = "", tool_calls: List[Any] | None = None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.prompt_cache_hit_tokens = 0


class ScenarioProvider:
    def __init__(self, tool_calls: List[Any]):
        self.tool_calls = tool_calls
        self.calls = 0

    async def chat(self, messages, tools=None, stream=False, stream_callback=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return DummyResponse(content="C step", tool_calls=self.tool_calls)
        return DummyResponse(content="NO_ACTION", tool_calls=[])

    def get_default_model(self):
        return "dummy"


class ProbeRecordLessonNodeTool(Tool):
    def __init__(self, sink: List[Dict[str, Any]]):
        self.sink = sink

    @property
    def name(self) -> str:
        return "record_lesson_node"

    @property
    def description(self) -> str:
        return "probe tool for c-phase trace"

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
                "resolves": {"type": "string"},
                "run_id": {"type": "string"},
                "call_id": {"type": "string"},
            },
            "required": [
                "node_id",
                "title",
                "trigger_verb",
                "trigger_noun",
                "trigger_context",
                "action_steps",
                "because_reason",
                "resolves",
            ],
        }

    async def execute(self, **kwargs) -> str:
        payload = dict(kwargs)
        required = [
            "node_id",
            "title",
            "trigger_verb",
            "trigger_noun",
            "trigger_context",
            "action_steps",
            "because_reason",
            "resolves",
        ]
        self.sink.append(
            {
                "tool_name": self.name,
                "top_keys": sorted(payload.keys()),
                "missing_required": [k for k in required if k not in payload or payload.get(k) in (None, "")],
                "has_call_id": "call_id" in payload,
                "has_run_id": "run_id" in payload,
            }
        )
        return f"ok:{payload.get('node_id', 'unknown')}"


class MiniRegistry:
    def __init__(self, tool):
        self.tool = tool

    def get(self, name):
        return self.tool if name == self.tool.name else None

    def list_tools(self):
        return [self.tool.name]

    async def execute(self, name, args):
        if name != self.tool.name:
            raise KeyError(name)
        if isinstance(args, dict):
            return await self.tool.execute(**args)
        return await self.tool.execute()


class CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.starts = []
        self.ends = []

    def emit(self, record):
        msg = record.getMessage()
        if msg.startswith("C_TOOL_TRACE_START "):
            self.starts.append(json.loads(msg.split(" ", 1)[1]))
        elif msg.startswith("C_TOOL_TRACE_END "):
            self.ends.append(json.loads(msg.split(" ", 1)[1]))


async def run_case(label: str, args: dict) -> dict:
    tool_events: List[Dict[str, Any]] = []
    provider = ScenarioProvider([ToolCall(id=f"{label}_tc1", name="record_lesson_node", arguments=args)])
    registry = MiniRegistry(ProbeRecordLessonNodeTool(tool_events))
    loop = V4Loop(tools=registry, provider=provider, c_phase_blocking=True)
    loop.user_input = f"{label} probe"
    loop.inferred_signature = {}
    loop.execution_reports = [
        {
            "summary": f"{label} summary",
            "findings": f"{label} findings",
            "changes_made": [],
            "artifacts": [],
            "open_questions": [],
            "raw_output": "",
        }
    ]
    loop.execution_messages = []
    loop.execution_active_nodes = []
    loop._op_tool_outcomes = [{"tool": "probe", "args": {}, "result": "ok", "duration_ms": 1, "success": True}]
    loop.blackboard = None
    loop._phase_count = 0
    loop._llm_call_count = 0
    loop._tool_call_count = 0
    loop.tracer = Tracer.get_instance()
    trace_id = loop.tracer.start_trace(f"{label} input")
    loop.trace_id = trace_id

    cap = CaptureHandler()
    root = logging.getLogger()
    root.addHandler(cap)
    try:
        await loop._run_c_phase(step_callback=None, mode="FULL", g_final_response=f"{label} g final")
    finally:
        root.removeHandler(cap)
        loop.tracer.end_trace(trace_id, status="completed", final_response=f"{label} done")

    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    try:
        trace_row = db.execute(
            "SELECT trace_id, status, started_at, ended_at, phase_count, llm_call_count, tool_call_count FROM traces WHERE trace_id = ? LIMIT 1",
            (trace_id,),
        ).fetchone()
        span_rows = db.execute(
            "SELECT name, span_type, phase, status, metadata_json, tool_args_preview, tool_result_preview FROM spans WHERE trace_id = ? AND name = ? ORDER BY started_at",
            (trace_id, "c_tool_probe:record_lesson_node"),
        ).fetchall()
    finally:
        db.close()

    return {
        "label": label,
        "trace_id": trace_id,
        "provider_calls": provider.calls,
        "trace_start_count": len(cap.starts),
        "trace_end_count": len(cap.ends),
        "trace_start": cap.starts[0] if cap.starts else None,
        "trace_end": cap.ends[0] if cap.ends else None,
        "tool_events": tool_events,
        "db_trace_found": trace_row is not None,
        "db_trace_status": dict(trace_row) if trace_row else None,
        "db_span_count": len(span_rows),
        "db_span_meta": [json.loads(r["metadata_json"]) if r["metadata_json"] else {} for r in span_rows],
        "db_span_args_preview": [r["tool_args_preview"] for r in span_rows],
        "db_span_result_preview": [r["tool_result_preview"] for r in span_rows],
    }


async def main():
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(logging.WARNING)

    complete_args = {
        "node_id": "LESSON_DOCTOR_COMPLETE_001",
        "title": "complete sample",
        "trigger_verb": "debug",
        "trigger_noun": "payload",
        "trigger_context": "probe",
        "action_steps": ["step1"],
        "because_reason": "because",
        "resolves": "complete payload",
        "run_id": "manual_run_001",
        "call_id": "manual_call_001",
    }
    bad_args = {
        "node_id": "LESSON_DOCTOR_BAD_001",
        "title": "bad sample",
        "trigger_verb": "debug",
        "trigger_noun": "payload",
        "trigger_context": "probe",
        "action_steps": ["step1"],
        "because_reason": "because",
        "resolves": "bad payload without trace fields",
    }

    complete = await run_case("complete", complete_args)
    bad = await run_case("bad", bad_args)

    complete_keys = set(complete["trace_start"]["arg_keys"])
    bad_keys = set(bad["trace_start"]["arg_keys"])

    assert complete["trace_start_count"] == complete["trace_end_count"] == 1
    assert bad["trace_start_count"] == bad["trace_end_count"] == 1
    assert complete["trace_start"]["call_index"] == complete["trace_end"]["call_index"] == 1
    assert bad["trace_start"]["call_index"] == bad["trace_end"]["call_index"] == 1
    assert complete["trace_start"]["run_id"] == complete["trace_end"]["run_id"]
    assert bad["trace_start"]["run_id"] == bad["trace_end"]["run_id"]
    assert complete_keys - bad_keys == {"call_id", "run_id"}
    assert bad_keys - complete_keys == set()
    assert complete["db_span_count"] == bad["db_span_count"] == 1
    assert complete["db_span_meta"][0]["call_index"] == bad["db_span_meta"][0]["call_index"] == 1
    assert complete["db_span_meta"][0]["has_call_id"] is True
    assert complete["db_span_meta"][0]["has_run_id"] is True
    assert bad["db_span_meta"][0]["has_call_id"] is False
    assert bad["db_span_meta"][0]["has_run_id"] is False
    assert complete["tool_events"][0]["has_call_id"] is True
    assert complete["tool_events"][0]["has_run_id"] is True
    assert bad["tool_events"][0]["has_call_id"] is False
    assert bad["tool_events"][0]["has_run_id"] is False
    assert complete["db_trace_found"] and bad["db_trace_found"]

    result = {
        "complete": complete,
        "bad": bad,
        "same_call_index_observed": True,
        "trace_pairs_complete": True,
        "trace_pairs_bad": True,
        "minimal_diff": sorted(list(complete_keys - bad_keys)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
