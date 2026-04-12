"""
Genesis V4 结构化数据模型 — Pydantic 强类型
替代代码中到处飞的 Dict[str, Any]，在编码阶段就捕获类型错误。
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class KnowledgeState(BaseModel):
    issue: str = Field(default="", description="当前聚焦的问题")
    verified_facts: List[str] = Field(default_factory=list, description="已被外部观测证实的事实")
    failed_attempts: List[str] = Field(default_factory=list, description="已证伪或已失败的尝试")
    next_checks: List[str] = Field(default_factory=list, description="下一步最值得做的检查")


class CallbackEvent(BaseModel):
    """UI 回调事件（防止 dict/str 类型混淆）"""
    event_type: str = Field(description="事件类型: loop_start, tool_start, tool_result, search_result, blueprint, thinking")
    phase: Optional[str] = Field(default=None, description="当前阶段: GP_PHASE / C_PHASE")
    name: Optional[str] = Field(default=None, description="工具名称")
    args: Optional[Dict[str, Any]] = Field(default=None, description="工具参数")
    result: Optional[str] = Field(default=None, description="工具结果（始终为 str）")

    @classmethod
    def from_raw(cls, event_type: str, data: Any) -> "CallbackEvent":
        """从原始 callback(event, data) 参数安全构造"""
        if isinstance(data, dict):
            return cls(
                event_type=event_type,
                phase=data.get("phase"),
                name=data.get("name"),
                args=data.get("args"),
                result=str(data.get("result", "")) if "result" in data else None
            )
        return cls(event_type=event_type, result=str(data) if data else None)


class MetadataSignature(BaseModel):
    """知识节点的元数据签名"""
    os_family: Optional[str] = None
    runtime: Optional[str] = None
    language: Optional[str] = None
    framework: Optional[str] = None
    environment_scope: Optional[str] = None
    task_kind: Optional[str] = None
    error_kind: Optional[str] = None
    validation_status: Optional[str] = None
    verification_source: Optional[str] = None
    last_verified_at: Optional[str] = None

    def to_search_dict(self) -> Dict[str, Any]:
        """转为搜索用的字典（排除 None 值）"""
        return {k: v for k, v in self.model_dump().items() if v is not None}


class ProviderConfig(BaseModel):
    """LLM 提供商配置"""
    name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    default_model: str = "deepseek-chat"
    connect_timeout: int = 10
    request_timeout: int = 120


class TraceInfo(BaseModel):
    """追踪信息，附加到 LLM 调用上"""
    trace_id: str = ""
    phase: str = ""
    parent_span: Optional[str] = None
