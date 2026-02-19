
from typing import Dict, Any
from genesis.core.base import Tool
from genesis.core.diagnostic import DiagnosticManager

class SystemHealthTool(Tool):
    """系统健康检查工具 - 允许 Agent 进行自检"""
    
    def __init__(self, provider_router=None, memory_store=None, tool_registry=None, context=None, scheduler=None):
        self.manager = DiagnosticManager(provider_router, memory_store, tool_registry, context, scheduler)
        
    @property
    def name(self) -> str:
        return "system_health"
    
    @property
    def description(self) -> str:
        return """Perform a system health check (Network, Provider, Memory, Disk).
        Use this tool when you encounter repeated errors, connection timeouts, or suspect system issues.
        It returns a diagnostic report with status of key components."""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }
    
    async def execute(self, **kwargs) -> str:
        try:
            report = await self.manager.run_all_checks()
            
            # Format report for LLM consumption (Compact)
            # Format report for LLM consumption (Compact)
            lines = [f"诊断报告 (状态: {report['status']})"]
            
            checks = report.get('checks', {})
            
            if 'network' in checks:
                net = checks['network']
                lines.append(f"- 网络: {net.get('status')}")
                if net.get('status') != 'ok':
                    lines.append(f"  错误详情: {net.get('details')}")

            if 'provider' in checks:
                prov = checks['provider']
                if prov.get('status') == 'ok':
                     stream_icon = "✅" if prov.get('streaming_ok') else "❌"
                     lines.append(f"- 模型服务: 正常 ({prov.get('provider')}, {prov.get('latency_ms', 0):.0f}ms)")
                     lines.append(f"  - 流式传输: {stream_icon} (延迟: {prov.get('stream_latency_ms', 0):.0f}ms)")
                else:
                     lines.append(f"- 模型服务: 错误 ({prov.get('error')})")

            if 'memory' in checks:
                mem = checks['memory']
                if mem.get('status') == 'ok':
                    bc = mem.get('block_count', 0)
                    vc = mem.get('vector_count', -1)
                    enc = mem.get('encoder_status', 'unknown')
                    vec_status = f"{vc} 条" if vc >= 0 else "未启用"
                    lines.append(f"- 记忆系统: 正常 ({mem.get('item_count')} 条短时, {bc} 个长时区块)")
                    lines.append(f"  - 联想记忆(Vector): {vec_status} (模型: {enc})")
                else:
                    lines.append(f"- 记忆系统: 错误 ({mem.get('error')})")
                    
            if 'tools' in checks:
                t = checks['tools']
                if t.get('status') != 'skipped':
                    lines.append(f"- 工具组件: 已加载 {t.get('count')} 个工具")
                    if t.get('missing'):
                         lines.append(f"  ⚠️ 警告: 缺失核心工具 {t.get('missing')}")
                    
            if 'context' in checks:
                ctx = checks['context']
                if ctx.get('status') == 'ok':
                    lines.append(f"- 上下文: 正常 (系统画像已加载)")
                else:
                    lines.append(f"- 上下文: ⚠️ 警告 ({ctx.get('issues')})")
                    
            if 'scheduler' in checks:
                sch = checks['scheduler']
                run_status = "运行中" if sch.get('is_running') else "休眠"
                lines.append(f"- 调度器: {run_status} ({sch.get('job_count')} 任务)")
                
            if 'disk' in checks:
                disk = checks['disk']
                lines.append(f"- 磁盘: {disk.get('free_gb')} GB 剩余 ({disk.get('status')})")
                
            return "\n".join(lines)
            
        except Exception as e:
            return f"Diagnostic Failed: {e}"
