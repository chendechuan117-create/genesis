"""
NanoGenesis 核心基础类
低耦合、高内聚的基础架构
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from enum import Enum


class MessageRole(Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """消息基础类"""
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None # 新增支持 assistant 的 tool_calls
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            "role": self.role.value,
            "content": self.content
        }
        if self.name:
            result["name"] = self.name
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        return result


@dataclass
class ToolCall:
    """工具调用"""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    
    @property
    def has_tool_calls(self) -> bool:
        return self.tool_calls is not None and len(self.tool_calls) > 0
    
    @property
    def usage(self) -> Dict[str, int]:
        return {
            'prompt_tokens': self.input_tokens,
            'completion_tokens': self.output_tokens,
            'total_tokens': self.total_tokens
        }


class Tool(ABC):
    """工具基类 - 所有工具的统一接口"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """工具参数 Schema (OpenAI Function Calling 格式)"""
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """执行工具"""
        pass
    
    def to_schema(self) -> Dict[str, Any]:
        """转换为 OpenAI Function Schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


class LLMProvider(ABC):
    """LLM 提供商基类"""
    
    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """发送聊天请求"""
        pass
    
    @abstractmethod
    def get_default_model(self) -> str:
        """获取默认模型"""
        pass


class ContextBuilder(ABC):
    """上下文构建器基类"""
    
    @abstractmethod
    async def build_messages(
        self,
        user_input: str,
        **kwargs
    ) -> List[Message]:
        """构建消息列表"""
        pass
    
    @abstractmethod
    def add_tool_result(
        self,
        messages: List[Message],
        tool_call_id: str,
        tool_name: str,
        result: str
    ) -> List[Message]:
        """添加工具执行结果"""
        pass


@dataclass
class Intent:
    """意图识别结果"""
    type: str
    domain: str
    needs_info: bool
    confidence: float


@dataclass
class Diagnosis:
    """诊断结果"""
    root_cause: str
    confidence: float
    suggested_solutions: List[str]
    evidence: Dict[str, Any]


@dataclass
class Strategy:
    """策略"""
    pattern: str
    root_cause: str
    solution: str
    domain: str
    dead_ends: List[str]
    confidence: float
    success_count: int = 0
    total_count: int = 0


@dataclass
class PerformanceMetrics:
    """性能指标"""
    iterations: int = 0
    total_time: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    tools_used: List[str] = None
    success: bool = True
    cache_hit: bool = False
    tool_calls: Optional[List[Dict]] = None
