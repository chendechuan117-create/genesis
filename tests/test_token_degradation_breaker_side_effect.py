"""
契约测试：token_degradation breaker 环境变量副作用

验证 _breaker_token_degradation 通过 os.environ 修改全局状态的行为
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from genesis.v4.diagnostics import PipelineDiagnostics


def test_token_degradation_breaker_modifies_env():
    """验证 breaker 触发后会修改 GENESIS_GP_MAX_ITERATIONS_OVERRIDE 环境变量"""
    # 清除环境变量，模拟初始状态
    os.environ.pop("GENESIS_GP_MAX_ITERATIONS_OVERRIDE", None)
    
    sig = PipelineDiagnostics.token_efficiency_degradation
    
    # 直接触发 breaker（绕过信号阈值检查）
    sig._on_fire(sig)
    
    # 验证环境变量被设置
    assert "GENESIS_GP_MAX_ITERATIONS_OVERRIDE" in os.environ
    assert os.environ["GENESIS_GP_MAX_ITERATIONS_OVERRIDE"] == "10"  # 默认 20 -> 10


def test_token_degradation_breaker_degrades_progressively():
    """验证 breaker 多次触发会逐步降级，直到下限 5"""
    # 从已知状态开始
    os.environ["GENESIS_GP_MAX_ITERATIONS_OVERRIDE"] = "20"
    
    sig = PipelineDiagnostics.token_efficiency_degradation
    
    # 第一次触发: 20 -> 10
    sig._on_fire(sig)
    assert os.environ["GENESIS_GP_MAX_ITERATIONS_OVERRIDE"] == "10"
    
    # 第二次触发: 10 -> 5
    sig._on_fire(sig)
    assert os.environ["GENESIS_GP_MAX_ITERATIONS_OVERRIDE"] == "5"
    
    # 第三次触发: 保持 5（下限）
    sig._on_fire(sig)
    assert os.environ["GENESIS_GP_MAX_ITERATIONS_OVERRIDE"] == "5"


def test_token_degradation_breaker_env_is_process_global():
    """验证 breaker 修改的环境变量是进程级全局的"""
    os.environ.pop("GENESIS_GP_MAX_ITERATIONS_OVERRIDE", None)
    
    # 触发 breaker
    PipelineDiagnostics.token_efficiency_degradation._on_fire(
        PipelineDiagnostics.token_efficiency_degradation
    )
    
    # 验证在 Python 层面可见
    assert os.environ.get("GENESIS_GP_MAX_ITERATIONS_OVERRIDE") == "10"
    
    # 验证对后续代码可见（模拟 V4Loop 读取）
    import subprocess
    result = subprocess.run(
        ["python3", "-c", "import os; print(os.environ.get('GENESIS_GP_MAX_ITERATIONS_OVERRIDE', 'NOT_SET'))"],
        capture_output=True,
        text=True
    )
    # 子进程继承环境变量
    assert result.stdout.strip() == "10"


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
