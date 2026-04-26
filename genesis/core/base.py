"""
NanoGenesis 核心基础类
低耦合、高内聚的基础架构
"""

from abc import ABC, abstractmethod
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
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
    # content 支持纯文本(str) 或多模态内容块列表(List[Dict])，用于视觉能力
    content: Union[str, List[Dict[str, Any]]]
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None # 新增支持 assistant 的 tool_calls
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            "role": self.role.value,
            # 多模态：list 直传；单模态：str 直传
            "content": self.content if isinstance(self.content, list) else self.content
        }
        if self.name:
            result["name"] = self.name
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            # Format tool_calls strictly to OpenAI spec
            formatted_tc = []
            for tc in self.tool_calls:
                # If it's already in the right format, keep it
                if "type" in tc and "function" in tc:
                    formatted_tc.append(tc)
                else:
                    # Convert from our internal dict (id, name, arguments)
                    formatted_tc.append({
                        "id": tc.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            # API expects arguments as string
                            "arguments": json.dumps(tc.get("arguments", {}), ensure_ascii=False) if isinstance(tc.get("arguments"), dict) else str(tc.get("arguments", ""))
                        }
                    })
            result["tool_calls"] = formatted_tc
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
    prompt_cache_hit_tokens: int = 0
    
    @property
    def has_tool_calls(self) -> bool:
        return self.tool_calls is not None and len(self.tool_calls) > 0
    
    @property
    def usage(self) -> Dict[str, int]:
        return {
            'prompt_tokens': self.input_tokens,
            'completion_tokens': self.output_tokens,
            'total_tokens': self.total_tokens,
            'prompt_cache_hit_tokens': self.prompt_cache_hit_tokens
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
    
    def is_concurrency_safe(self, arguments: Dict[str, Any]) -> bool:
        """是否可与其他工具并行执行。默认 False（保守），只读工具覆写为 True。"""
        return False
    
    def to_schema(self) -> Dict[str, Any]:
        """转换为 OpenAI Function Schema (Safe Version)"""
        params = self.parameters
        
        # Defensive Programming: Ensure parameters is a valid dict
        if params is None:
            # logger.warning(f"Tool {self.name} has None parameters. Auto-fixing to empty object.")
            params = {"type": "object", "properties": {}}
        elif not isinstance(params, dict):
            # logger.warning(f"Tool {self.name} parameters is not a dict. Auto-fixing.")
            params = {"type": "object", "properties": {}}
            
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params
            }
        }


class MetaTool(Tool):
    """元工具基类 — 从 NodeVault TOOL 节点动态加载的工具继承此类。
    携带信任水印、来源节点 ID、生命周期钩子。
    """

    _node_id: str = ""
    _trust_tier: str = "REFLECTION"
    _source: str = "dynamic"

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def trust_tier(self) -> str:
        return self._trust_tier

    @property
    def meta_info(self) -> Dict[str, Any]:
        return {"node_id": self._node_id, "trust_tier": self._trust_tier, "source": self._source}

    def pre_execute(self, **kwargs) -> Dict[str, Any]:
        """执行前钩子：可用于参数校验、日志、或拒绝执行。返回修改后的 kwargs。"""
        return kwargs

    def post_execute(self, result: str) -> str:
        """执行后钩子：可用于结果审计、截断、或记录指标。"""
        return result

    async def execute(self, **kwargs) -> str:
        kwargs = self.pre_execute(**kwargs)
        result = await self._execute_impl(**kwargs)
        return self.post_execute(result)

    async def _execute_impl(self, **kwargs) -> str:
        """子类实现实际逻辑"""
        raise NotImplementedError("MetaTool subclass must implement _execute_impl")


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


@dataclass
class PerformanceMetrics:
    """性能指标"""
    iterations: int = 0
    total_time: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    prompt_cache_hit_tokens: int = 0
    # 令牌计量表：分阶段 token 追踪
    g_tokens: int = 0
    op_tokens: int = 0
    c_tokens: int = 0
    tools_used: List[str] = field(default_factory=list)
    success: bool = True
    cache_hit: bool = False
    tool_calls: Optional[List[Dict]] = None
