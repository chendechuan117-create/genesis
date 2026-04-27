
import inspect
import json
import sys
import types
import unittest
from unittest.mock import patch


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


class _DummyVectorEngine:
    is_ready = False
    def search(self, *args, **kwargs):
        return []
    def rerank(self, query, rows):
        return rows


class _DummyVault:
    def __init__(self):
        self.vector_engine = _DummyVectorEngine()
        self.created = []
        self.updated = []
        self.edges = []
    def create_node(self, **kwargs):
        self.created.append(kwargs)
    def update_node_content(self, *args, **kwargs):
        self.updated.append((args, kwargs))
    def promote_node_confidence(self, *args, **kwargs):
        pass
    def get_node_briefs(self, ids):
        return {}
    def add_edge(self, *args, **kwargs):
        self.edges.append((args, kwargs))


class DoctorRLNEnvelopeBoundaryTest(unittest.IsolatedAsyncioTestCase):
    async def test_record_lesson_node_boundary_unwraps_arguments_and_input(self):
        _stub_provider_stack()
        _stub_vector_stack()
        from factory import create_agent

        full = {
            'node_id': 'LESSON_DOCTOR_BOUNDARY',
            'title': 'Doctor boundary unwrap',
            'trigger_verb': 'debug',
            'trigger_noun': 'registry',
            'trigger_context': 'doctor_envelope_boundary',
            'action_steps': ['probe envelope', 'unwrap at boundary'],
            'because_reason': 'prefer contract-safe normalization over leaking raw execute kwargs',
        }

        with patch('genesis.tools.node_tools.NodeVault', _DummyVault):
            agent = create_agent(api_key='x', base_url='http://127.0.0.1', model='dummy')
            reg = agent.tools
            tool = reg.get('record_lesson_node')

            self.assertIsNotNone(tool)
            self.assertTrue(inspect.ismethod(tool.execute))

            ok_direct = await reg.execute('record_lesson_node', dict(full))
            ok_arguments = await reg.execute('record_lesson_node', {'arguments': dict(full)})
            ok_input = await reg.execute('record_lesson_node', {'input': dict(full)})
            bad_kwargs = await reg.execute('record_lesson_node', {'kwargs': dict(full)})

            self.assertIn('写入成功', ok_direct)
            self.assertIn('写入成功', ok_arguments)
            self.assertIn('写入成功', ok_input)
            self.assertIn('不支持 kwargs envelope', bad_kwargs)
            self.assertNotIn('unexpected keyword argument', bad_kwargs)

            created_ids = [item['node_id'] for item in tool.vault.created]
            self.assertEqual(
                created_ids,
                ['LESSON_DOCTOR_BOUNDARY', 'LESSON_DOCTOR_BOUNDARY', 'LESSON_DOCTOR_BOUNDARY'],
            )

            print(json.dumps({
                'registry_class': reg.__class__.__module__ + '.' + reg.__class__.__name__,
                'tool_class': tool.__class__.__module__ + '.' + tool.__class__.__name__,
                'execute_signature': str(inspect.signature(tool.execute)),
                'ok_direct': ok_direct,
                'ok_arguments': ok_arguments,
                'ok_input': ok_input,
                'bad_kwargs': bad_kwargs,
                'created_ids': created_ids,
            }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    unittest.main()
