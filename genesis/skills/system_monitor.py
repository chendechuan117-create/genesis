import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class SystemMonitor(Tool):
    @property
    def name(self) -> str:
        return "system_monitor"
        
    @property
    def description(self) -> str:
        return "监控系统资源使用情况，包括CPU、内存、磁盘、运行进程等"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "monitor_type": {
                    "type": "string", 
                    "description": "监控类型：cpu, memory, disk, processes, all",
                    "default": "all"
                },
                "duration_seconds": {
                    "type": "integer",
                    "description": "监控持续时间（秒），仅用于持续监控",
                    "default": 10
                }
            },
            "required": []
        }
        
    async def execute(self, monitor_type: str = "all", duration_seconds: int = 10) -> str:
        import subprocess
        import time
        import psutil
        
        results = []
        
        if monitor_type in ["cpu", "all"]:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            
            cpu_info = f"""
CPU 信息:
- 核心数: {cpu_count}
- 当前使用率: {cpu_percent}%
- 频率: {cpu_freq.current if cpu_freq else 'N/A'} MHz
"""
            results.append(cpu_info)
        
        if monitor_type in ["memory", "all"]:
            # 内存使用情况
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            memory_info = f"""
内存信息:
- 总内存: {memory.total / (1024**3):.2f} GB
- 已使用: {memory.used / (1024**3):.2f} GB ({memory.percent}%)
- 可用: {memory.available / (1024**3):.2f} GB
- 交换空间: {swap.total / (1024**3):.2f} GB ({swap.percent}% 已使用)
"""
            results.append(memory_info)
        
        if monitor_type in ["disk", "all"]:
            # 磁盘使用情况
            disk_info = "磁盘信息:\n"
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_info += f"- {partition.device} ({partition.mountpoint}): {usage.percent}% 已使用, {usage.free / (1024**3):.2f} GB 可用\n"
                except:
                    continue
            results.append(disk_info)
        
        if monitor_type in ["processes", "all"]:
            # 进程信息
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    processes.append(proc.info)
                except:
                    continue
            
            # 按CPU使用率排序
            processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
            
            process_info = "Top 10 进程 (按CPU使用率):\n"
            for i, proc in enumerate(processes[:10]):
                process_info += f"{i+1}. PID: {proc['pid']}, 名称: {proc['name']}, CPU: {proc['cpu_percent']}%, 内存: {proc['memory_percent']:.1f}%\n"
            
            results.append(process_info)
        
        # 网络连接信息
        if monitor_type in ["all"]:
            net_info = "网络连接:\n"
            connections = psutil.net_connections()
            established = [c for c in connections if c.status == 'ESTABLISHED']
            listening = [c for c in connections if c.status == 'LISTEN']
            
            net_info += f"- 已建立连接: {len(established)}\n"
            net_info += f"- 监听端口: {len(listening)}\n"
            
            # 显示监听端口
            net_info += "监听端口:\n"
            for conn in listening[:5]:  # 只显示前5个
                if conn.laddr:
                    net_info += f"  - {conn.laddr.ip}:{conn.laddr.port} ({conn.type})\n"
            
            results.append(net_info)
        
        return "\n" + "="*50 + "\n".join(results) + "\n" + "="*50