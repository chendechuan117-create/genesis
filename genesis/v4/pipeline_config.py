"""
Genesis V4 - 管线配置契约 (Pipeline Config)

所有散布在 loop.py / lens_phase.py / manager.py / diagnostics.py 中的魔法数字，
统一收口到一个 typed dataclass。各模块通过引用此配置来获取常量。
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class PipelineConfig:
    """V4 管线全局配置。frozen=True 保证运行时不可变。"""

    # ── G-Phase ──────────────────────────────────
    g_max_iterations: int = 20
    g_max_consecutive_errors: int = 3

    # ── Op-Phase ──────────────────────────────────
    op_max_iterations: int = 60
    op_max_consecutive_errors: int = 3

    # ── C-Phase ──────────────────────────────────
    c_phase_max_iter: Dict[str, int] = field(default_factory=lambda: {
        "FULL": 30, "LIGHT": 5, "SKIP": 0
    })

    # ── Tool Execution ──────────────────────────────────
    tool_exec_timeout: int = 300  # 秒

    # ── Lens (Multi-G) ──────────────────────────────────
    lens_max_iterations: int = 2
    lens_timeout_secs: int = 120
    lens_concurrency: int = 2  # 并发透镜数
    lens_min_input_chars: int = 50  # 输入太短则跳过透镜

    # ── Token Diagnostics ──────────────────────────────────
    token_window_size: int = 10
    token_degradation_multiplier: float = 2.0  # 超过均值 N 倍视为退化

    # ── Signature Engine ──────────────────────────────────
    dim_freshness_days: int = 7
    dim_min_freq: int = 3
    max_custom_dims_per_node: int = 5
    learned_marker_max_per_key: int = 10

    # ── Node Versioning ──────────────────────────────────
    version_keep_limit: int = 5

    # ── Diagnostic Signals ──────────────────────────────────
    diag_default_window: int = 5
    diag_default_threshold: float = 0.6


# 全局单例 — 模块通过 `from genesis.v4.pipeline_config import PIPELINE_CONFIG` 引用
PIPELINE_CONFIG = PipelineConfig()
