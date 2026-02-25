import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class SystemTaskComplete(Tool):
    @property
    def name(self) -> str:
        return "system_task_complete"
        
    @property
    def description(self) -> str:
        return "当任务已成功且完整地执行完毕时，必须通过此工具提交最终的汇总说明来结束执行"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "任务执行完成的汇总说明或最终结果"}
            },
            "required": ["summary"]
        }
        
    async def execute(self, summary: str) -> str:
        return f"任务已完成：{summary}"
