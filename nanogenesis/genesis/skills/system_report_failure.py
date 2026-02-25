import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class SystemReportFailure(Tool):
    @property
    def name(self) -> str:
        return "system_report_failure"
        
    @property
    def description(self) -> str:
        return "当无法匹配到合适工具时报告失败原因"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "失败原因描述"}
            },
            "required": ["reason"]
        }
        
    async def execute(self, reason: str) -> str:
        return f"系统报告失败：{reason}"