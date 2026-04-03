import asyncio
import io
import json
import logging
import sys
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _stub_provider_stack():
    if 'httpx' not in sys.modules:
        sys.modules['httpx'] = types.ModuleType('httpx')


def _stub_vector_stack():
    if 'numpy' not in sys.modules:
        numpy_mod = types.ModuleType('numpy')
        numpy_mod.ndarray = list
        numpy_mod.array = lambda x, *a, **k: x
        numpy_mod.asarray = lambda x, *a, **k: x
        numpy_mod.float32 = float
        numpy_mod.dot = lambda a, b: 0.0
        numpy_mod.linalg = types.SimpleNamespace(norm=lambda x: 1.0)
        sys.modules['numpy'] = numpy_mod

    if 'torch' not in sys.modules:
        torch_mod = types.ModuleType('torch')
        class _NoGrad:
            def __enter__(self):
                return None
            def __exit__(self, exc_type, exc, tb):
                return False
        torch_mod.no_grad = lambda: _NoGrad()
        torch_mod.cuda = types.SimpleNamespace(is_available=lambda: False)
        torch_mod.device = lambda name: name
        sys.modules['torch'] = torch_mod

    if 'transformers' not in sys.modules:
        tr = types.ModuleType('transformers')
        class _Auto:
            @classmethod
            def from_pretrained(cls, *args, **kwargs):
                return cls()
            def to(self, *args, **kwargs):
                return self
            def eval(self):
                return self
            def __call__(self, *args, **kwargs):
                return types.SimpleNamespace(last_hidden_state=[])
        tr.AutoTokenizer = _Auto
        tr.AutoModel = _Auto
        tr.AutoModelForSequenceClassification = _Auto
        sys.modules['transformers'] = tr

    if 'sentence_transformers' not in sys.modules:
        st = types.ModuleType('sentence_transformers')
        class _CrossEncoder:
            def __init__(self, *args, **kwargs):
                pass
            def predict(self, pairs):
                return [0.5 for _ in pairs]
        st.CrossEncoder = _CrossEncoder
        sys.modules['sentence_transformers'] = st


class DummyResponse:
    def __init__(self, content='', tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.prompt_cache_hit_tokens = 0


class ScenarioProvider:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.calls = 0

    async def chat(self, messages, tools=None, stream=False, stream_callback=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return DummyResponse(content='C step', tool_calls=self.tool_calls)
        return DummyResponse(content='NO_ACTION', tool_calls=[])

    def get_default_model(self):
        return 'dummy'


class CallbackCapture:
    def __init__(self):
        self.events = []

    async def __call__(self, event, payload):
        self.events.append((event, payload))


class CPhaseLessonWritebackVisibilityTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        _stub_provider_stack()
        _stub_vector_stack()
        import genesis.v4.loop as loop_mod
        from genesis.core.base import Tool, ToolCall

        self.loop_mod = loop_mod
        self.ToolCall = ToolCall

        class SilentNodeVault:
            def __init__(self, *args, **kwargs):
                pass
            def infer_metadata_signature(self, text):
                return {}
            def merge_metadata_signatures(self, *parts):
                merged = {}
                for p in parts:
                    if isinstance(p, dict):
                        merged.update(p)
                return merged
            def infer_metadata_signature_from_artifacts(self, artifacts):
                return {}
            def expand_signature_from_node_ids(self, node_ids):
                return {}
            def learn_signature_marker(self, *args, **kwargs):
                return None
            def get_node_briefs(self, ids):
                return {}

        class SilentFactoryManager:
            def __init__(self, *args, **kwargs):
                pass

        class SilentBlackboard:
            entries = []
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
        self.V4Loop = loop_mod.V4Loop
        self.Tool = Tool

    async def _run_case(self, tool_result):
        Tool = self.Tool
        ToolCall = self.ToolCall

        class ProbeLessonTool(Tool):
            @property
            def name(self):
                return 'record_lesson_node'
            @property
            def description(self):
                return 'probe'
            @property
            def parameters(self):
                return {'type': 'object', 'properties': {'node_id': {'type': 'string'}}}
            async def execute(self, **kwargs):
                return tool_result

        class MiniRegistry:
            def __init__(self, tool):
                self.tool = tool
            def get(self, name):
                return self.tool if name == self.tool.name else None
            async def execute(self, name, args, source=None):
                return await self.tool.execute(**(args or {}))

        provider = ScenarioProvider([
            ToolCall(
                id='tc1',
                name='record_lesson_node',
                arguments={
                    'node_id': 'LESSON_WRITEBACK_VIS',
                    'title': 'writeback visibility',
                    'trigger_verb': 'debug',
                    'trigger_noun': 'record_lesson_node',
                    'trigger_context': 'doctor_test',
                    'action_steps': ['attempt writeback'],
                    'because_reason': 'exercise c-phase writeback status',
                    'resolves': 'record_lesson_node missing required positional arguments',
                },
            )
        ])
        loop = self.V4Loop(tools=MiniRegistry(ProbeLessonTool()), provider=provider, c_phase_blocking=True)
        loop.user_input = 'self improvement probe'
        loop.inferred_signature = {}
        loop.execution_reports = [{'summary': 's', 'findings': 'f', 'changes_made': [], 'artifacts': [], 'open_questions': [], 'raw_output': ''}]
        loop.execution_messages = []
        loop.execution_active_nodes = []
        loop._op_tool_outcomes = []
        loop.blackboard = None
        loop._phase_count = 0
        loop._llm_call_count = 0
        loop._tool_call_count = 0

        cb = CallbackCapture()
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        root = logging.getLogger()
        root.addHandler(handler)
        old_level = root.level
        root.setLevel(logging.INFO)
        try:
            await loop._run_c_phase(step_callback=cb, mode='FULL', g_final_response='done')
        finally:
            root.removeHandler(handler)
            root.setLevel(old_level)

        return cb.events, log_stream.getvalue()

    async def test_failed_record_lesson_node_is_exposed_in_c_phase_done(self):
        events, logs = await self._run_case('Error: Missing required parameters: title')
        done_payloads = [payload for event, payload in events if event == 'c_phase_done']
        self.assertTrue(done_payloads)
        payload = done_payloads[-1]
        self.assertEqual(payload.get('writeback_status'), 'failed')
        self.assertEqual(payload['writeback_failures'][0]['node_id'], 'LESSON_WRITEBACK_VIS')
        self.assertIn('Missing required parameters', payload['writeback_failures'][0]['result'])
        self.assertIn('[C_WRITEBACK_FAILED]', logs)

    async def test_successful_record_lesson_node_marks_persisted(self):
        events, logs = await self._run_case('✅ LESSON节点 [LESSON_WRITEBACK_VIS] 写入成功。')
        done_payloads = [payload for event, payload in events if event == 'c_phase_done']
        self.assertTrue(done_payloads)
        payload = done_payloads[-1]
        self.assertEqual(payload.get('writeback_status'), 'persisted')
        self.assertNotIn('writeback_failures', payload)
        self.assertNotIn('[C_WRITEBACK_FAILED]', logs)


if __name__ == '__main__':
    unittest.main()
