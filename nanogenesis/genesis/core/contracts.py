"""
Genesis V2 - Core Contracts
核心接口定义：OpSpec 和 OpResult

[GENESIS_V2_SPEC.md 核心原则 #1]
管道必须是结构化的 — Manager → op 的接口是 typed dataclass，不是自然语言字符串。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class OpSpec:
    """
    Manager → OpExecutor 的结构化指令。

    由 Manager（厂长）从车间检索结果组装而来，
    是 OpExecutor 唯一的输入来源。
    """
    objective: str                          # 本次 op 的具体目标
    tool_ids: List[str]                     # 从 tool_workshop 选出的工具名称列表
    context_facts: List[str]                # 从 known_info_workshop 加载的事实字符串列表
    output_schema: Dict[str, Any]           # 从 output_format_workshop 加载的格式规范
    strategy_hint: str                      # 从 metacognition_workshop 提取的策略提示
    expected_output: str                    # 成功标准，用于 OpResult.success 判断
    max_iterations: int = 5                 # op 内部最大工具调用次数（防止死循环）
    attempt_number: int = 1                 # 第几次重组尝试（熔断计数用）
    sensory_context: str = ""               # 感知上下文（附件列表、图片描述等），供 Executor 提示 LLM


@dataclass
class OpResult:
    """
    OpExecutor → Manager 的结构化结果。

    Manager 根据此结构判断成功/失败/重组/熔断，
    不依赖 LLM 对自由文本的解读。
    """
    success: bool                           # 是否满足 expected_output 标准
    matched_expected: bool                  # 输出格式是否匹配 output_schema
    tool_outputs: List[Dict[str, Any]]      # 每次工具调用的原始结果列表（可审计）
    final_output: Any                       # 按 output_schema 结构化的最终输出
    attempt_number: int = 1                 # 对应 OpSpec.attempt_number
    error: Optional[str] = None            # 失败原因（success=False 时填充）
    entropy_triggered: bool = False         # 是否触发了 entropy 熔断
    tokens_used: int = 0                    # 本次 op 消耗的 token 数


@dataclass
class SensoryItem:
    """
    Standardized input unit for any modality (Text, Image, Audio, File).
    """
    type: str                               # 'text', 'image', 'audio', 'file'
    content: str                            # The actual text OR absolute file path
    mime_type: str = "text/plain"           # e.g., 'image/png', 'audio/wav'
    metadata: Dict[str, Any] = field(default_factory=dict) # OCR text, duration, size, etc.


@dataclass
class SensoryPacket:
    """
    A unified container for user inputs, replacing raw strings.
    The Manager receives this packet, allowing it to "see" multiple modalities naturally.
    """
    items: List[SensoryItem]
    source: str = "unknown"                 # 'discord', 'web', 'terminal'
    context_id: str = ""                    # Session/Channel ID

    def text_content(self) -> str:
        """Helper to get the main user text query."""
        return "\n".join(item.content for item in self.items if item.type == 'text')
