import asyncio
import io
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
            return DummyResponse(content='C gardener step', tool_calls=self.tool_calls)
        return DummyResponse(content='NO_ACTION', tool_calls=[])

    def get_default_model(self):
        return 'dummy'


class CallbackCapture:
    def __init__(self):
        self.events = []

    async def __call__(self, event, payload):
        self.events.append((event, payload))


class CPhaseGardenerEdgeVisibilityTest(unittest.IsolatedAsyncioTestCase):
    """Test C-Gardener mode: C only adds edges (CONTRADICTS/RELATED_TO), never creates LESSON nodes."""

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
            def batch_get_titles(self, ids):
                return {}
            def check_ablation_candidates(self, **kw):
                return []
            def get_ablation_observing_nodes(self, **kw):
                return []
            def increment_usage(self, nodes, **kw):
                pass
            def get_multiple_contents(self, ids):
                return {}
            def sync_vector_matrix_incremental(self):
                pass
            def get_frontier_node_ids(self, **kw):
                return []
            def record_arena_result(self, *a, **kw):
                pass
            def record_usage_outcome(self, *a, **kw):
                pass
            def add_edge(self, *a, **kw):
                return True
            def get_digest(self, *a, **kw):
                return ""
            @property
            def vector_engine(self):
                return types.SimpleNamespace(is_ready=False, search=lambda *a, **k: [])

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

    async def _run_case(self, tool_result, relation='CONTRADICTS'):
        from genesis.core.base import Tool, ToolCall

        class ProbeEdgeTool(Tool):
            @property
            def name(self):
                return 'create_node_edge'
            @property
            def description(self):
                return 'probe'
            @property
            def parameters(self):
                return {
                    'type': 'object',
                    'properties': {
                        'source_id': {'type': 'string'},
                        'target_id': {'type': 'string'},
                        'relation': {'type': 'string'},
                        'weight': {'type': 'number'},
                    }
                }
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
                name='create_node_edge',
                arguments={
                    'source_id': 'LESSON_NEW_001',
                    'target_id': 'LESSON_OLD_002',
                    'relation': relation,
                    'weight': 1.0,
                },
            )
        ])
        loop = self.V4Loop(tools=MiniRegistry(ProbeEdgeTool()), provider=provider, c_phase_blocking=True)
        loop.user_input = 'gardener edge probe: testing that C-Gardener can add CONTRADICTS and RELATED_TO edges between knowledge nodes without creating new LESSON nodes'
        loop.inferred_signature = {}
        loop.execution_reports = [{'summary': 's', 'findings': 'f', 'changes_made': [], 'artifacts': [], 'open_questions': [], 'raw_output': ''}]
        loop.execution_messages = []
        loop.execution_active_nodes = ['LESSON_NEW_001', 'LESSON_OLD_002']
        loop._op_tool_outcomes = [{'tool': 'shell', 'args': {}, 'result': 'ok', 'duration_ms': 1, 'success': True}]
        loop.blackboard = None
        loop._phase_count = 0
        loop._llm_call_count = 0
        loop._tool_call_count = 0
        loop.g_messages = []

        cb = CallbackCapture()
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        root = logging.getLogger()
        root.addHandler(handler)
        old_level = root.level
        root.setLevel(logging.INFO)
        try:
            await loop._run_c_phase(step_callback=cb, mode='FULL', g_final_response='I discovered that LESSON_OLD_002 contradicts with the new finding. The old lesson says to use proxychains for all API calls, but the new evidence shows that DeepSeek API works faster with direct connection (trust_env=False). This is a clear contradiction that should be marked with a CONTRADICTS edge.')
        finally:
            root.removeHandler(handler)
            root.setLevel(old_level)

        return cb.events, log_stream.getvalue()

    async def test_successful_edge_add_reported_in_reflection_result(self):
        events, logs = await self._run_case('✅ 边建立: LESSON_NEW_001 --[CONTRADICTS]--> LESSON_OLD_002')
        done_payloads = [payload for event, payload in events if event == 'c_phase_done']
        self.assertTrue(done_payloads)
        payload = done_payloads[-1]
        reflection = payload.get('reflection', {})
        self.assertEqual(reflection.get('edges_added', 0), 1)
        self.assertIn('C-Gardener', logs)

    async def test_failed_edge_add_still_non_fatal(self):
        events, logs = await self._run_case('Error: node not found')
        done_payloads = [payload for event, payload in events if event == 'c_phase_done']
        self.assertTrue(done_payloads)
        # C-Gardener failures are non-fatal, C-Phase still completes
        payload = done_payloads[-1]
        reflection = payload.get('reflection', {})
        # Edge creation failed but C-Phase didn't crash
        self.assertIn('edges_added', reflection)

    async def test_related_to_edge_accepted(self):
        events, logs = await self._run_case('✅ 边建立: A --[RELATED_TO]--> B', relation='RELATED_TO')
        done_payloads = [payload for event, payload in events if event == 'c_phase_done']
        self.assertTrue(done_payloads)
        reflection = done_payloads[-1].get('reflection', {})
        self.assertEqual(reflection.get('edges_added', 0), 1)


if __name__ == '__main__':
    unittest.main()
