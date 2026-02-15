"""
NanoGenesis - 自进化的轻量级智能 Agent

三者融合：
- nanobot: 极简架构
- Genesis: 智能诊断
- OpenClaw: 工具生态
"""

__version__ = "0.1.0"

from .core import (
    ToolRegistry,
    AgentLoop,
    SimpleContextBuilder,
    LiteLLMProvider,
    MockLLMProvider,
)

from .agent import NanoGenesis

__all__ = [
    'NanoGenesis',
    'ToolRegistry',
    'AgentLoop',
    'SimpleContextBuilder',
    'LiteLLMProvider',
    'MockLLMProvider',
]
