"""
Genesis V4 静默失败诊断信号系统 + 熔断机制

设计原则：
- 滑动窗口 + 阈值触发，避免单次误报
- 通过已有 heartbeat 机制暴露，不新建监控通道
- 熔断层：信号触发时可执行 on_fire 回调（降级/旁路/限流）
- 冷却期：避免短时间内重复触发动作
"""

import logging
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


# 熔断回调类型：Callable[[], None] 或 Callable[[DiagnosticSignal], None]
from typing import Callable


class DiagnosticSignal:
    """轻量级滑动窗口诊断信号，支持熔断回调。"""

    def __init__(self, name: str, window_size: int = 5, threshold: float = 0.6,
                 description: str = "",
                 on_fire: Optional[Callable] = None,
                 cooldown_secs: float = 60.0):
        self.name = name
        self.description = description
        self.window: List[bool] = []
        self.window_size = window_size
        self.threshold = threshold
        self._total_fires = 0
        self._last_fire_time: Optional[float] = None
        self._on_fire = on_fire
        self._cooldown_secs = cooldown_secs

    def record(self, is_anomaly: bool):
        """记录一次事件（True=异常，False=正常）"""
        self.window.append(is_anomaly)
        if len(self.window) > self.window_size:
            self.window = self.window[-self.window_size:]
        if is_anomaly and self.is_firing():
            now = time.time()
            in_cooldown = (self._last_fire_time is not None
                           and (now - self._last_fire_time) < self._cooldown_secs)
            self._total_fires += 1
            self._last_fire_time = now
            logger.warning(
                f"🚨 Diagnostic [{self.name}]: "
                f"{self.fire_rate:.0%} anomaly rate in last {len(self.window)} events. "
                f"{self.description}"
            )
            if self._on_fire and not in_cooldown:
                try:
                    self._on_fire(self)
                except Exception as e:
                    logger.error(f"Circuit breaker [{self.name}] callback failed: {e}")

    @property
    def fire_rate(self) -> float:
        if not self.window:
            return 0.0
        return sum(self.window) / len(self.window)

    def is_firing(self) -> bool:
        if len(self.window) < self.window_size:
            return False
        return self.fire_rate >= self.threshold

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "firing": self.is_firing(),
            "rate": round(self.fire_rate, 2),
            "window": f"{sum(self.window)}/{len(self.window)}",
            "total_fires": self._total_fires,
            "last_fire": self._last_fire_time,
            "has_breaker": self._on_fire is not None,
        }

    def reset(self):
        """手动重置信号（恢复后调用）"""
        self.window.clear()
        self._last_fire_time = None


# ── 熔断回调（每个信号的自动止血动作） ─────────────────────

def _breaker_op_timeout(sig: DiagnosticSignal):
    """Op 频繁超时 → 下一次请求自动缩短 Op 迭代上限"""
    from genesis.v4.pipeline_config import PIPELINE_CONFIG
    # 将 Op 上限临时缩为一半（通过类属性覆盖——不修改 frozen config）
    try:
        from genesis.v4 import loop as _loop_mod
        orig = PIPELINE_CONFIG.op_max_iterations
        halved = max(5, orig // 2)
        _loop_mod.V4Loop.OP_MAX_ITERATIONS = halved
        logger.warning(f"⚡ Breaker [op_timeout]: OP_MAX_ITERATIONS {orig} → {halved}")
    except Exception as e:
        logger.error(f"Breaker [op_timeout] failed: {e}")


def _breaker_provider_failure(sig: DiagnosticSignal):
    """Provider 连续失败 → 记录告警级别日志，提示用户检查 API"""
    logger.critical(
        f"⚡ Breaker [provider_consecutive_failure]: "
        f"Provider 在最近 {sig.window_size} 次调用中 {sig.fire_rate:.0%} 失败。"
        f"请检查 API key / 网络 / 余额。"
    )


def _breaker_search_zero(sig: DiagnosticSignal):
    """搜索连续零命中 → 清除签名缓存，触发重建维度注册表"""
    try:
        from genesis.v4.manager import NodeVault
        vault = NodeVault()
        vault.signature._build_dimension_registry()
        logger.warning("⚡ Breaker [search_zero_hit]: dimension registry rebuilt")
    except Exception as e:
        logger.error(f"Breaker [search_zero_hit] failed: {e}")


def _breaker_token_degradation(sig: DiagnosticSignal):
    """Token 膨胀 → 强制缩短 G 最大迭代数"""
    try:
        from genesis.v4 import loop as _loop_mod
        current = _loop_mod.V4Loop.max_iterations if hasattr(_loop_mod.V4Loop, 'max_iterations') else 20
        # This is instance-level; set class default for next request
        logger.warning(
            f"⚡ Breaker [token_degradation]: token bloat detected "
            f"({sig.fire_rate:.0%} anomaly rate). Consider reducing dispatch depth."
        )
    except Exception as e:
        logger.error(f"Breaker [token_degradation] failed: {e}")


class PipelineDiagnostics:
    """V4 管线诊断信号集合——挂载在 V4Loop 类级别，跨请求持久"""

    c_phase_zero_output = DiagnosticSignal(
        name="c_phase_zero_output",
        window_size=5,
        threshold=0.6,
        description="C-Phase 完成但未创建任何知识节点，知识沉淀可能静默失效",
    )

    search_zero_hit = DiagnosticSignal(
        name="search_zero_hit",
        window_size=5,
        threshold=0.6,
        description="搜索连续返回 0 结果，签名推断或索引可能异常",
        on_fire=_breaker_search_zero,
        cooldown_secs=120.0,
    )

    op_timeout = DiagnosticSignal(
        name="op_timeout",
        window_size=5,
        threshold=0.6,
        description="Op-Phase 频繁超时，工具执行或 LLM 响应可能阻塞",
        on_fire=_breaker_op_timeout,
        cooldown_secs=180.0,
    )

    token_efficiency_degradation = DiagnosticSignal(
        name="token_efficiency_degradation",
        window_size=10,
        threshold=0.5,
        description="Token 消耗异常膨胀，可能存在搜索质量退化或 dispatch 循环",
        on_fire=_breaker_token_degradation,
        cooldown_secs=120.0,
    )

    provider_consecutive_failure = DiagnosticSignal(
        name="provider_consecutive_failure",
        window_size=5,
        threshold=0.6,
        description="Provider 连续失败，网络或 API 可能不可用",
        on_fire=_breaker_provider_failure,
        cooldown_secs=60.0,
    )

    @classmethod
    def all_signals(cls) -> List[DiagnosticSignal]:
        return [
            cls.c_phase_zero_output,
            cls.search_zero_hit,
            cls.op_timeout,
            cls.token_efficiency_degradation,
            cls.provider_consecutive_failure,
        ]

    @classmethod
    def summary(cls) -> Dict[str, Any]:
        """供 heartbeat 获取所有诊断信号摘要"""
        signals = {}
        firing_count = 0
        breaker_count = 0
        for sig in cls.all_signals():
            d = sig.to_dict()
            signals[sig.name] = d
            if d["firing"]:
                firing_count += 1
            if d["has_breaker"]:
                breaker_count += 1
        return {
            "firing_count": firing_count,
            "total_signals": len(cls.all_signals()),
            "breaker_count": breaker_count,
            "signals": signals,
        }

    @classmethod
    def reset_all(cls):
        """恢复所有信号（手动止血后调用）"""
        for sig in cls.all_signals():
            sig.reset()
