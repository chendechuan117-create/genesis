"""
dispatch_to_op 注册工具

将 dispatch_to_op 从 loop.py 中的幽灵 Schema 常量变为 ToolRegistry 中的注册工具。
V4Loop 仍然在工具调度前拦截该调用并路由到 Op-Process，但 Schema 来源统一为 ToolRegistry。
"""

from typing import Dict, Any
from genesis.core.base import Tool


class DispatchTool(Tool):
    """派发任务给 Op-Process 的虚拟工具。

    LLM 通过 function calling 调用此工具，但 V4Loop 在执行前拦截并路由到 Op-Phase。
    此工具的 execute() 不应被直接调用。
    """

    @property
    def name(self) -> str:
        return "dispatch_to_op"

    @property
    def description(self) -> str:
        return (
            "派发任务给执行器 Op-Process。当你完成思考和信息收集，需要 Op 去执行具体操作"
            "（如读写文件、运行命令、网络请求等）时，调用此工具。调用后系统会挂起你的运行，"
            "将参数交给 Op 执行，执行完毕后结果会作为此工具的返回值回传给你。"
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "op_intent": {
                    "type": "string",
                    "description": "对 Op 目标的一句话明确指令"
                },
                "active_nodes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需要挂载给 Op 参考的节点 ID 列表（如 CTX_XXX, LESSON_XXX）。没有则传空数组 []"
                },
                "instructions": {
                    "type": "string",
                    "description": "给 Op 的详细执行步骤和上下文信息"
                }
            },
            "required": ["op_intent", "instructions"]
        }

    async def execute(self, **kwargs) -> str:
        raise RuntimeError(
            "dispatch_to_op should be intercepted by V4Loop, not executed directly. "
            "If you see this error, the loop dispatch interception logic is broken."
        )
