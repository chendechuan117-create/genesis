
from typing import Dict, Any, Type
from core.base import Tool
from core.scheduler import AgencyScheduler

class SchedulerTool(Tool):
    """调度器工具：允许 Agent 添加或移除后台监控任务"""
    
    def __init__(self, scheduler: AgencyScheduler):
        self.scheduler = scheduler
        
    @property
    def name(self) -> str:
        return "scheduler_tool"
    
    @property
    def description(self) -> str:
        return """管理后台任务调度 (Agency)。
        可以添加周期性执行的任务（如监控日志、定时检查）。
        这些任务会在后台静默运行，只有发现异常时才会报警。
        """
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "remove", "list"],
                    "description": "操作类型"
                },
                "command": {
                    "type": "string",
                    "description": "要执行的 Shell 命令 (仅 add 需要)"
                },
                "interval": {
                    "type": "integer",
                    "description": "执行间隔，单位秒 (仅 add 需要)"
                },
                "job_id": {
                    "type": "string",
                    "description": "任务 ID (仅 remove 需要)"
                }
            },
            "required": ["action"]
        }
    
    async def execute(self, action: str, command: str = None, interval: int = 60, job_id: str = None) -> str:
        if action == "add":
            if not command:
                return "错误: 添加任务需要提供 command"
            
            # 安全检查：是否允许执行任意命令？
            # 既然 ShellTool 已经存在且受 Sandbox 保护，这里理论上也可以。
            # 但后台任务通常应该只读 (监控)。
            
            jid = self.scheduler.add_job(command, interval)
            # 确保调度器已启动
            if not self.scheduler.running:
                await self.scheduler.start()
                
            return f"✓ 已添加后台任务 [{jid}]\n命令: {command}\n间隔: {interval}s"
            
        elif action == "remove":
            if not job_id:
                return "错误: 移除任务需要提供 job_id"
            if self.scheduler.remove_job(job_id):
                return f"✓ 已移除任务 {job_id}"
            return f"未找到任务 {job_id}"
            
        elif action == "list":
            if not self.scheduler.jobs:
                return "当前无后台任务"
            
            report = "【后台任务列表】\n"
            for j in self.scheduler.jobs.values():
                report += f"- [{j.id}] {j.command} ({j.interval}s)\n"
            return report
            
        return f"未知操作: {action}"
