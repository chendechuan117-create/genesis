import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _stub_vector_stack():
    if 'numpy' not in sys.modules:
        numpy_mod = types.ModuleType('numpy')
        numpy_mod.ndarray = list
        numpy_mod.array = lambda x, *a, **k: x
        numpy_mod.asarray = lambda x, *a, **k: x
        numpy_mod.float32 = float
        sys.modules['numpy'] = numpy_mod


class DummyMetrics:
    success = True
    iterations = 1
    total_time = 0.25
    input_tokens = 1
    output_tokens = 2
    total_tokens = 3
    g_tokens = 0
    op_tokens = 0
    c_tokens = 0


class UnifiedResponseTextNormalizationTest(unittest.TestCase):
    def test_from_op_result_normalizes_public_text_fields(self):
        _stub_vector_stack()
        from genesis.v4.unified_response import UnifiedResponse

        response = UnifiedResponse.from_op_result(
            response_text='ok',
            metrics=DummyMetrics(),
            trace_id=789,
            partial_reason=123,
            op_result={'status': 'SUCCESS', 'findings': ['alpha', 2]},
            error_info={'type': {'kind': 'boundary'}, 'detail': ['bad', 7]},
        )

        self.assertEqual(response.trace_id, '789')
        self.assertEqual(response.partial_reason, '123')
        self.assertEqual(response.findings, 'alpha; 2')
        self.assertEqual(response.error_type, "{'kind': 'boundary'}")
        self.assertEqual(response.error_detail, 'bad; 7')


if __name__ == '__main__':
    unittest.main()
