import logging
from typing import Dict, Any
from genesis.core.base import Tool
from genesis.tools.sub_agent_manager import SubAgentManager

logger = logging.getLogger(__name__)

class CheckSubAgentTool(Tool):
    """
    Checks the status of an asynchronously spawned Sub-Agent.
    """
    
    @property
    def name(self) -> str:
        return "check_sub_agent"
    
    @property
    def description(self) -> str:
        return """查询之前派生的子代理 (Sub-Agent) 的执行状态和最终结果。
当您使用 spawn_sub_agent 派发了后台任务后，会获得一个 task_id。
请使用此工具传入 task_id 来获取子代理的汇报。如果任务仍在执行中，它会告知您继续等待。
如果任务已完成，它会返回子代理的深度执行摘要与代价复盘。"""
        
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "SpawnSubAgentTool 返回的唯一任务标识符 (Task ID)"
                }
            },
            "required": ["task_id"]
        }
        
    async def execute(self, task_id: str) -> str:
        manager = SubAgentManager()
        status_info = manager.get_status(task_id)
        
        status = status_info.get("status")
        if status == "completed":
            result = status_info.get("result", "")
            return f"✅ 子代理任务 '{task_id}' 已完成。\n\n[深度执行摘要与代价复盘]:\n{result}"
        elif status == "failed":
            error = status_info.get("error", "Unknown Error")
            return f"❌ 子代理任务 '{task_id}' 执行崩溃。\n错误原因: {error}"
        elif status == "not_found":
            return f"⚠️ 找不到任务 '{task_id}'。请确认 ID 是否正确拼写。"
        else: # running
            return f"⏳ 子代理任务 '{task_id}' 仍在疯狂计算/执行中。请稍后再使用 check_sub_agent 查询，或先处理您的其他事务。"
