"""
Genesis V4 统一结果信封
解决内部执行状态丰富、对外交付契约被压扁的结构性缺口
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class ExecutionStatus(str, Enum):
    """执行状态枚举"""
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class UnifiedResponse(BaseModel):
    """
    统一结果信封 - 对外暴露完整的执行状态
    
    设计原则：
    1. 包含所有内部状态信息，不压扁
    2. 提供明确的成功分级（不只是布尔值）
    3. 支持降级和部分成功场景
    4. 包含追踪和调试信息
    5. 保持向后兼容性
    """
    
    # 核心状态字段
    status: ExecutionStatus = Field(default=ExecutionStatus.UNKNOWN, description="执行状态: SUCCESS/PARTIAL/FAILED/UNKNOWN")
    response: str = Field(default="", description="最终响应文本")
    
    # 降级和部分成功信息
    degraded: bool = Field(default=False, description="是否降级执行（如知识库搜索失败）")
    partial_reason: Optional[str] = Field(default=None, description="部分成功的原因（如达到迭代上限）")
    
    # 执行元数据
    success: bool = Field(default=False, description="向后兼容的布尔成功标志")
    iterations: int = Field(default=0, description="执行迭代次数")
    duration_ms: float = Field(default=0.0, description="执行总时间（毫秒）")
    
    # 追踪和调试信息
    trace_id: str = Field(default="", description="追踪ID，用于调试和复盘")
    
    # 内部执行详情（可选暴露）
    summary: Optional[str] = Field(default=None, description="执行摘要")
    findings: Optional[str] = Field(default=None, description="发现与观察")
    changes_made: Optional[List[str]] = Field(default=None, description="修改的文件/资源列表")
    artifacts: Optional[List[str]] = Field(default=None, description="产出的制品列表")
    open_questions: Optional[List[str]] = Field(default=None, description="未解决的问题")
    
    # 性能指标
    input_tokens: int = Field(default=0, description="输入token数")
    output_tokens: int = Field(default=0, description="输出token数")
    total_tokens: int = Field(default=0, description="总token数")
    g_tokens: int = Field(default=0, description="GP-Phase token数")
    op_tokens: int = Field(default=0, description="(废弃，保持兼容) 始终为0")
    c_tokens: int = Field(default=0, description="C-Phase token数")
    
    # 错误信息
    error_type: Optional[str] = Field(default=None, description="错误类型")
    error_detail: Optional[str] = Field(default=None, description="错误详情")

    # 经历轨迹：GP/C 两阶段完整对话序列，供复盘使用
    phase_trace: Optional[Dict[str, Any]] = Field(default=None, description="GP/C 阶段对话轨迹")
    knowledge_state: Optional[Dict[str, Any]] = Field(default=None, description="当前工作记忆")
     
    # 向后兼容别名
    @classmethod
    def from_op_result(cls, **kwargs) -> "UnifiedResponse":
        return cls.from_result(**kwargs)

    @classmethod
    def from_result(
        cls,
        response_text: str,
        metrics: Any,
        trace_id: str = "",
        degraded: bool = False,
        partial_reason: Optional[str] = None,
        error_info: Optional[Dict[str, str]] = None,
        phase_trace: Optional[Dict[str, Any]] = None,
        knowledge_state: Optional[Dict[str, Any]] = None,
    ) -> "UnifiedResponse":
        """
        从 GP 执行结果构建统一响应
        """
        # 确定状态
        if metrics.success:
            status = ExecutionStatus.SUCCESS
            if partial_reason:
                status = ExecutionStatus.PARTIAL
        else:
            status = ExecutionStatus.FAILED
        
        # 构建响应
        return cls(
            status=status,
            response=response_text,
            degraded=degraded,
            partial_reason=partial_reason,
            success=metrics.success,
            iterations=metrics.iterations,
            duration_ms=metrics.total_time * 1000,
            trace_id=trace_id,
            input_tokens=metrics.input_tokens,
            output_tokens=metrics.output_tokens,
            total_tokens=metrics.total_tokens,
            g_tokens=metrics.g_tokens,
            op_tokens=metrics.op_tokens,
            c_tokens=metrics.c_tokens,
            error_type=error_info.get("type") if error_info else None,
            error_detail=error_info.get("detail") if error_info else None,
            phase_trace=phase_trace,
            knowledge_state=knowledge_state,
         )
    
    @classmethod
    def from_error(cls, error_message: str, trace_id: str = "") -> "UnifiedResponse":
        """从错误构建统一响应"""
        return cls(
            status=ExecutionStatus.FAILED,
            response=f"系统错误: {error_message}",
            success=False,
            trace_id=trace_id,
            error_type="system_error",
            error_detail=error_message
        )