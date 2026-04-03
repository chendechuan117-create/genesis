"""
Genesis V4 (Glassbox) Agent 实例
"""

import logging
from typing import Dict, Any, Optional, List

from genesis.core.base import LLMProvider, PerformanceMetrics
from genesis.core.registry import ToolRegistry
from genesis.core.tracer import Tracer
from genesis.v4.loop import V4Loop
from genesis.v4.unified_response import UnifiedResponse

logger = logging.getLogger(__name__)

class GenesisV4:
    """V4 白盒认知装配师"""

    def __init__(
        self,
        tools: ToolRegistry,
        provider: LLMProvider,
        max_iterations: int = 200,
        enable_logging: bool = True,
        c_phase_blocking: bool = False,
    ):
        self.tools = tools
        self.provider = provider
        self.max_iterations = max_iterations
        self.enable_logging = enable_logging
        self.c_phase_blocking = c_phase_blocking

    async def process(self, user_input: str, step_callback: Optional[Any] = None, image_paths: Optional[List[str]] = None, c_phase_blocking: Optional[bool] = None, loop_config: Optional[Dict[str, Any]] = None, initial_knowledge_state: Optional[Dict[str, Any]] = None) -> UnifiedResponse:
        """
        处理单轮会话，V4 的管线：
        1. 交由 V4Loop 运行（强制 JSON Blueprint -> 工具调用序列）
        2. 将内部结果转换为统一响应信封
        """
        logger.info("============== GENESIS V4 PROCESS START ==============")
        
        tracer = Tracer.get_instance()
        trace_id = tracer.start_trace(user_input)
        
        effective_blocking = c_phase_blocking if c_phase_blocking is not None else self.c_phase_blocking
        loop = V4Loop(
            tools=self.tools,
            provider=self.provider,
            max_iterations=self.max_iterations,
            c_phase_blocking=effective_blocking,
        )

        try:
            final_response, metrics = await loop.run(
                user_input=user_input,
                step_callback=step_callback,
                image_paths=image_paths,
                loop_config=loop_config,
                initial_knowledge_state=initial_knowledge_state,
            )
            
            # 结束追踪
            tracer.end_trace(trace_id, final_response=final_response)
            
            logger.info(f"V4 Process Complete. Success: {metrics.success}, Iters: {metrics.iterations}")
            
            # 检测部分成功场景
            partial_reason = None
            status = "SUCCESS"
            if metrics.iterations >= self.max_iterations:
                partial_reason = f"达到最大迭代上限 ({self.max_iterations})"
                status = "PARTIAL"
            elif not metrics.success:
                status = "FAILED"
            
            return UnifiedResponse.from_op_result(
                response_text=final_response,
                metrics=metrics,
                trace_id=trace_id,
                partial_reason=partial_reason,
                degraded=False,
                phase_trace=loop.get_phase_trace(),
                knowledge_state=loop.get_knowledge_state(),
            )
            
        except Exception as e:
            logger.error(f"V4 execution failed: {e}", exc_info=True)
            tracer.end_trace(trace_id, error=str(e))
            
            # 创建失败的 metrics
            metrics = PerformanceMetrics(success=False, total_time=0)
            
            return UnifiedResponse.from_op_result(
                response_text=f"V4 Execution Error: {e}",
                metrics=metrics,
                trace_id=trace_id,
                error_info={"type": "execution_error", "detail": str(e)}
            )