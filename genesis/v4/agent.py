"""
Genesis V4 (Glassbox) Agent 实例
"""

import logging
from typing import Dict, Any, Optional

from genesis.core.base import LLMProvider, PerformanceMetrics
from genesis.core.registry import ToolRegistry
from genesis.v4.loop import V4Loop

logger = logging.getLogger(__name__)

class GenesisV4:
    """V4 白盒认知装配师"""

    def __init__(
        self,
        tools: ToolRegistry,
        provider: LLMProvider,
        max_iterations: int = 200,
        enable_logging: bool = True
    ):
        self.tools = tools
        self.provider = provider
        self.max_iterations = max_iterations
        self.enable_logging = enable_logging

    async def process(self, user_input: str, step_callback: Optional[Any] = None, image_paths: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        处理单轮会话，V4 的管线：
        1. 交由 V4Loop 运行（强制 JSON Blueprint -> 工具调用序列）
        """
        logger.info("============== GENESIS V4 PROCESS START ==============")
        
        loop = V4Loop(
            tools=self.tools,
            provider=self.provider,
            max_iterations=self.max_iterations,
        )

        try:
            final_response, metrics = await loop.run(
                user_input=user_input,
                step_callback=step_callback,
                image_paths=image_paths,
            )
        except Exception as e:
            logger.error(f"V4 execution failed: {e}", exc_info=True)
            final_response = f"V4 Execution Error: {e}"
            metrics = PerformanceMetrics(success=False, total_time=0)

        logger.info(f"V4 Process Complete. Success: {metrics.success}, Iters: {metrics.iterations}")
        
        return {
            "response": final_response,
            "metrics": metrics,
        }
