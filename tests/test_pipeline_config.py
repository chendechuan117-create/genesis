"""
契约测试：PipelineConfig

验证：
1. 单例不可变（frozen dataclass）
2. 所有字段有合理默认值
3. 字段类型正确
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from genesis.v4.pipeline_config import PipelineConfig, PIPELINE_CONFIG


def test_frozen_immutable():
    try:
        PIPELINE_CONFIG.op_max_iterations = 999
        assert False, "Should raise FrozenInstanceError"
    except AttributeError:
        pass  # Expected: frozen dataclass


def test_singleton_is_pipeline_config():
    assert isinstance(PIPELINE_CONFIG, PipelineConfig)


def test_g_phase_defaults():
    assert PIPELINE_CONFIG.g_max_iterations == 20
    assert PIPELINE_CONFIG.g_max_consecutive_errors == 3


def test_op_phase_defaults():
    assert PIPELINE_CONFIG.op_max_iterations == 60
    assert PIPELINE_CONFIG.op_max_consecutive_errors == 3


def test_c_phase_defaults():
    assert PIPELINE_CONFIG.c_phase_max_iter["FULL"] == 30
    assert PIPELINE_CONFIG.c_phase_max_iter["LIGHT"] == 5
    assert PIPELINE_CONFIG.c_phase_max_iter["SKIP"] == 0


def test_tool_timeout():
    assert PIPELINE_CONFIG.tool_exec_timeout == 300


def test_lens_defaults():
    assert PIPELINE_CONFIG.lens_max_iterations == 2
    assert PIPELINE_CONFIG.lens_timeout_secs == 120
    assert PIPELINE_CONFIG.lens_concurrency == 2
    assert PIPELINE_CONFIG.lens_min_input_chars == 50


def test_signature_defaults():
    assert PIPELINE_CONFIG.dim_freshness_days == 7
    assert PIPELINE_CONFIG.dim_min_freq == 3
    assert PIPELINE_CONFIG.max_custom_dims_per_node == 5
    assert PIPELINE_CONFIG.learned_marker_max_per_key == 10


def test_all_values_positive():
    """所有数值型配置应为正数"""
    for field_name in ['g_max_iterations', 'g_max_consecutive_errors',
                       'op_max_iterations', 'op_max_consecutive_errors',
                       'tool_exec_timeout', 'lens_max_iterations',
                       'lens_timeout_secs', 'lens_concurrency',
                       'lens_min_input_chars', 'token_window_size',
                       'dim_freshness_days', 'dim_min_freq',
                       'max_custom_dims_per_node', 'learned_marker_max_per_key',
                       'version_keep_limit', 'diag_default_window']:
        val = getattr(PIPELINE_CONFIG, field_name)
        assert val > 0, f"{field_name} should be positive, got {val}"


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"  ✅ {t.__name__}")
        except Exception as e:
            print(f"  ❌ {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
