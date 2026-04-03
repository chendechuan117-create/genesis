#!/usr/bin/env python3
import asyncio
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path('/home/chendechusn/Genesis/Genesis')
sys.path.insert(0, str(PROJECT_ROOT))

from genesis.core.registry import ToolRegistry
from genesis.tools.node_tools import RecordLessonNodeTool, SearchKnowledgeNodesTool
from genesis.core.base import Tool

class EchoObjectTool(Tool):
    @property
    def name(self) -> str:
        return 'echo_object_tool'

    @property
    def description(self) -> str:
        return 'test helper tool'

    @property
    def parameters(self) -> dict:
        return {
            'type': 'object',
            'properties': {
                'message': {'type': 'string'}
            },
            'required': ['message']
        }

    async def execute(self, message: str) -> str:
        return f'ECHO:{message}'

async def main():
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
    reg = ToolRegistry()
    reg.register(RecordLessonNodeTool())
    reg.register(SearchKnowledgeNodesTool())
    reg.register(EchoObjectTool())

    cases = {
        'A_missing_7': ('record_lesson_node', {'node_id': 'LESSON_DOCTOR_MISS_001'}),
        'B_valid_minimal': ('record_lesson_node', {
            'node_id': 'LESSON_DOCTOR_PREFLIGHT_MIN_OK',
            'title': 'Doctor preflight minimal valid sample',
            'trigger_verb': 'debug',
            'trigger_noun': 'registry',
            'trigger_context': 'doctor_sandbox_preflight_probe',
            'action_steps': ['inspect registry required gate', 'verify structured error before execute'],
            'because_reason': '证明缺参在 registry 层被结构化拦截，合法路径保持可用',
            'prerequisites': [],
            'resolves': 'record_lesson_node missing required positional arguments'
        }),
        'C_other_smoke': ('echo_object_tool', {'message': 'ok'})
    }

    results = {}
    for label, (name, args) in cases.items():
        results[label] = await reg.execute(name, args)

    print(json.dumps(results, ensure_ascii=False, indent=2))

asyncio.run(main())
