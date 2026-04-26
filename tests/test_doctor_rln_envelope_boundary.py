"""
RLN Envelope Boundary Test
验证 registry.execute() 直接透传参数，无 arguments/input 解包
"""
import inspect
import json
import sys
import types
import unittest
from unittest.mock import patch


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
    def get_same_round_ids(self, *args, **kwargs):
        return set()
    def find_collision_candidates(self, *args, **kwargs):
        return []


class DoctorRLNEnvelopeBoundaryTest(unittest.IsolatedAsyncioTestCase):
    async def test_record_lesson_node_boundary(self):
        """验证 registry.execute() 直接透传参数，无 arguments/input 解包"""
        _stub_vector_stack()

        from genesis.core.registry import ToolRegistry
        from genesis.tools.node_tools import RecordLessonNodeTool

        reg = ToolRegistry()

        with patch('genesis.tools.node_tools.NodeVault', _DummyVault):
            tool = RecordLessonNodeTool()
            reg.register(tool)

            self.assertIsNotNone(reg.get('record_lesson_node'))
            self.assertTrue(inspect.ismethod(tool.execute))

            # Test 1: 直接传参，缺少 reasoning_basis → 前置校验失败
            direct_missing_basis = await reg.execute('record_lesson_node', {
                'node_id': 'LESSON_TEST_DIRECT',
                'title': 'Direct pass test',
                'trigger_verb': 'test',
                'trigger_noun': 'registry',
                'trigger_context': 'direct_pass',
                'action_steps': ['step1'],
                'because_reason': 'test',
                'resolves': 'test',
            })
            self.assertIn('reasoning_basis 不能为空', direct_missing_basis)

            # Test 2: 直接传参，完整参数 → 成功
            full_params = {
                'node_id': 'LESSON_TEST_FULL',
                'title': 'Full params test',
                'trigger_verb': 'test',
                'trigger_noun': 'registry',
                'trigger_context': 'full_params',
                'action_steps': ['step1'],
                'because_reason': 'test',
                'resolves': 'test',
                'reasoning_basis': [{'basis_node_id': 'P_TEST_001', 'reasoning': 'test basis'}],
            }
            ok_full = await reg.execute('record_lesson_node', full_params)
            self.assertIn('写入成功', ok_full)

            # Test 3: registry 无 arguments 解包：arguments 被当作普通 key
            with_arguments_wrapper = await reg.execute('record_lesson_node', {
                'arguments': full_params
            })
            self.assertIn('unexpected keyword argument', with_arguments_wrapper)

            # Test 4: registry 无 input 解包：input 被当作普通 key
            with_input_wrapper = await reg.execute('record_lesson_node', {
                'input': full_params
            })
            self.assertIn('unexpected keyword argument', with_input_wrapper)

            # Test 5: kwargs wrapper → Python 原生 TypeError
            bad_kwargs = await reg.execute('record_lesson_node', {
                'kwargs': full_params
            })
            self.assertIn('unexpected keyword argument', bad_kwargs)

            print(json.dumps({
                'registry_class': reg.__class__.__module__ + '.' + reg.__class__.__name__,
                'tool_class': tool.__class__.__module__ + '.' + tool.__class__.__name__,
                'execute_signature': str(inspect.signature(tool.execute)),
                'direct_missing_basis': direct_missing_basis[:100],
                'ok_full': ok_full[:100],
                'with_arguments_wrapper': with_arguments_wrapper[:100],
                'with_input_wrapper': with_input_wrapper[:100],
                'bad_kwargs': bad_kwargs[:100],
            }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    unittest.main()
