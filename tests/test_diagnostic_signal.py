"""
契约测试：DiagnosticSignal + PipelineDiagnostics

验证：
1. 滑动窗口正确截断
2. 阈值触发逻辑
3. fire_rate 计算
4. PipelineDiagnostics.summary() 结构
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from genesis.v4.diagnostics import DiagnosticSignal, PipelineDiagnostics


def test_window_truncation():
    sig = DiagnosticSignal("test", window_size=3, threshold=0.5)
    for _ in range(10):
        sig.record(False)
    assert len(sig.window) == 3, f"Window should be 3, got {len(sig.window)}"


def test_fire_rate_calculation():
    sig = DiagnosticSignal("test", window_size=4, threshold=0.5)
    sig.record(True)
    sig.record(False)
    sig.record(True)
    sig.record(False)
    assert sig.fire_rate == 0.5, f"Expected 0.5, got {sig.fire_rate}"


def test_not_firing_below_window_size():
    sig = DiagnosticSignal("test", window_size=5, threshold=0.6)
    sig.record(True)
    sig.record(True)
    sig.record(True)
    # Only 3 events, window_size=5 → should NOT fire
    assert not sig.is_firing(), "Should not fire with insufficient data"


def test_fires_above_threshold():
    sig = DiagnosticSignal("test", window_size=5, threshold=0.6)
    for _ in range(5):
        sig.record(True)
    assert sig.is_firing(), "Should fire at 100% anomaly rate"
    assert sig._total_fires > 0, "Should have recorded fires"


def test_stops_firing_after_recovery():
    sig = DiagnosticSignal("test", window_size=3, threshold=0.6)
    sig.record(True)
    sig.record(True)
    sig.record(True)
    assert sig.is_firing()
    # Push out anomalies with normal events
    sig.record(False)
    sig.record(False)
    sig.record(False)
    assert not sig.is_firing(), "Should stop firing after recovery"


def test_to_dict_structure():
    sig = DiagnosticSignal("test_sig", window_size=3, threshold=0.5)
    sig.record(False)
    d = sig.to_dict()
    assert d["name"] == "test_sig"
    assert "firing" in d
    assert "rate" in d
    assert "window" in d
    assert "total_fires" in d


def test_pipeline_diagnostics_summary():
    summary = PipelineDiagnostics.summary()
    assert "firing_count" in summary
    assert "total_signals" in summary
    assert summary["total_signals"] == 5
    assert "signals" in summary
    assert "c_phase_zero_output" in summary["signals"]
    assert "search_zero_hit" in summary["signals"]
    assert "op_timeout" in summary["signals"]


def test_pipeline_diagnostics_all_signals():
    signals = PipelineDiagnostics.all_signals()
    assert len(signals) == 5
    names = {s.name for s in signals}
    expected = {"c_phase_zero_output", "search_zero_hit", "op_timeout",
                "token_efficiency_degradation", "provider_consecutive_failure"}
    assert names == expected, f"Missing signals: {expected - names}"


def test_on_fire_callback():
    fired = []
    sig = DiagnosticSignal("cb_test", window_size=3, threshold=0.6,
                           on_fire=lambda s: fired.append(s.name),
                           cooldown_secs=0)  # no cooldown for test
    sig.record(True)
    sig.record(True)
    sig.record(True)
    assert len(fired) >= 1, "Callback should have been invoked"
    assert fired[0] == "cb_test"


def test_cooldown_prevents_repeat_fire():
    fired = []
    sig = DiagnosticSignal("cool_test", window_size=3, threshold=0.6,
                           on_fire=lambda s: fired.append(1),
                           cooldown_secs=9999)  # very long cooldown
    for _ in range(3):
        sig.record(True)
    first_count = len(fired)
    # Record more anomalies — should NOT fire callback again due to cooldown
    for _ in range(5):
        sig.record(True)
    assert len(fired) == first_count, f"Cooldown should block re-fire, got {len(fired)} fires"


def test_reset_clears_window():
    sig = DiagnosticSignal("reset_test", window_size=3, threshold=0.6)
    sig.record(True)
    sig.record(True)
    sig.record(True)
    assert sig.is_firing()
    sig.reset()
    assert not sig.is_firing()
    assert len(sig.window) == 0


def test_to_dict_has_breaker_field():
    sig_no = DiagnosticSignal("no_breaker", window_size=3, threshold=0.5)
    sig_yes = DiagnosticSignal("has_breaker", window_size=3, threshold=0.5,
                               on_fire=lambda s: None)
    assert sig_no.to_dict()["has_breaker"] is False
    assert sig_yes.to_dict()["has_breaker"] is True


def test_pipeline_diagnostics_summary_has_breaker_count():
    summary = PipelineDiagnostics.summary()
    assert "breaker_count" in summary
    # 4 signals have breakers (search_zero, op_timeout, token_degradation, provider_failure)
    assert summary["breaker_count"] == 4


def test_pipeline_diagnostics_reset_all():
    # Fire some signals
    PipelineDiagnostics.c_phase_zero_output.record(True)
    PipelineDiagnostics.reset_all()
    for sig in PipelineDiagnostics.all_signals():
        assert len(sig.window) == 0, f"{sig.name} should be reset"


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
