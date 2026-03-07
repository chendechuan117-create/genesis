import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class DeploymentMonitor(Tool):
    @property
    def name(self) -> str:
        return "deployment_monitor"
        
    @property
    def description(self) -> str:
        return "监控部署状态，包括服务健康检查、端口监听、进程状态和资源使用情况"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "services": {
                    "type": "array", 
                    "description": "要监控的服务列表，格式：[{'name': 'n8n', 'port': 5678, 'health_endpoint': '/healthz'}, ...]",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "port": {"type": "integer"},
                            "health_endpoint": {"type": "string"}
                        }
                    },
                    "default": [
                        {"name": "n8n", "port": 5678, "health_endpoint": "/healthz"},
                        {"name": "web_ui", "port": 5000, "health_endpoint": "/"}
                    ]
                },
                "check_resources": {
                    "type": "boolean",
                    "description": "是否检查系统资源",
                    "default": True
                }
            },
            "required": []
        }
        
    async def execute(self, services: list = None, check_resources: bool = True) -> str:
        import socket
        import requests
        import psutil
        import time
        from datetime import datetime
        
        if services is None:
            services = [
                {"name": "n8n", "port": 5678, "health_endpoint": "/healthz"},
                {"name": "web_ui", "port": 5000, "health_endpoint": "/"}
            ]
        
        results = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "services": [],
            "resources": {},
            "overall_status": "HEALTHY"
        }
        
        # 检查服务状态
        for service in services:
            service_name = service.get("name", "unknown")
            port = service.get("port", 0)
            health_endpoint = service.get("health_endpoint", "")
            
            service_status = {
                "name": service_name,
                "port": port,
                "status": "UNKNOWN",
                "details": ""
            }
            
            # 检查端口是否监听
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex(('127.0.0.1', port))
                sock.close()
                
                if result == 0:
                    service_status["status"] = "PORT_OPEN"
                    
                    # 尝试HTTP健康检查
                    if health_endpoint:
                        try:
                            url = f"http://127.0.0.1:{port}{health_endpoint}"
                            response = requests.get(url, timeout=3)
                            if response.status_code == 200:
                                service_status["status"] = "HEALTHY"
                                service_status["details"] = f"HTTP {response.status_code}"
                            else:
                                service_status["status"] = "UNHEALTHY"
                                service_status["details"] = f"HTTP {response.status_code}"
                        except Exception as e:
                            service_status["status"] = "PORT_OPEN_NO_HTTP"
                            service_status["details"] = str(e)
                else:
                    service_status["status"] = "PORT_CLOSED"
                    service_status["details"] = f"Port {port} not listening"
                    
            except Exception as e:
                service_status["status"] = "ERROR"
                service_status["details"] = str(e)
            
            # 检查是否有相关进程
            try:
                found_processes = []
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        if service_name.lower() in proc.info['name'].lower() or \
                           (proc.info['cmdline'] and any(service_name.lower() in cmd.lower() for cmd in proc.info['cmdline'] if cmd)):
                            found_processes.append({
                                "pid": proc.info['pid'],
                                "name": proc.info['name'],
                                "cpu": proc.cpu_percent(),
                                "memory": proc.memory_percent()
                            })
                    except:
                        continue
                
                if found_processes:
                    service_status["processes"] = found_processes
            except:
                pass
            
            results["services"].append(service_status)
            
            # 更新整体状态
            if service_status["status"] not in ["HEALTHY", "PORT_OPEN"]:
                results["overall_status"] = "DEGRADED"
        
        # 检查系统资源
        if check_resources:
            try:
                # CPU
                cpu_percent = psutil.cpu_percent(interval=1)
                
                # 内存
                memory = psutil.virtual_memory()
                
                # 磁盘
                disk_usage = psutil.disk_usage('/')
                
                # 网络连接
                connections = len(psutil.net_connections())
                
                results["resources"] = {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_available_gb": memory.available / (1024**3),
                    "disk_percent": disk_usage.percent,
                    "disk_free_gb": disk_usage.free / (1024**3),
                    "network_connections": connections
                }
                
                # 检查资源阈值
                if cpu_percent > 80:
                    results["overall_status"] = "DEGRADED"
                if memory.percent > 85:
                    results["overall_status"] = "DEGRADED"
                if disk_usage.percent > 90:
                    results["overall_status"] = "DEGRADED"
                    
            except Exception as e:
                results["resources_error"] = str(e)
        
        # 生成报告
        report = []
        report.append("=" * 60)
        report.append(f"部署监控报告 - {results['timestamp']}")
        report.append(f"整体状态: {results['overall_status']}")
        report.append("=" * 60)
        
        report.append("\n📊 服务状态:")
        for service in results["services"]:
            status_icon = "✅" if service["status"] in ["HEALTHY", "PORT_OPEN"] else "⚠️" if service["status"] == "DEGRADED" else "❌"
            report.append(f"  {status_icon} {service['name']} (端口:{service['port']}): {service['status']}")
            if service.get("details"):
                report.append(f"    详情: {service['details']}")
            if service.get("processes"):
                for proc in service["processes"]:
                    report.append(f"    进程: PID {proc['pid']} ({proc['name']}) - CPU: {proc['cpu']:.1f}%, 内存: {proc['memory']:.1f}%")
        
        if results.get("resources"):
            report.append("\n💾 系统资源:")
            resources = results["resources"]
            report.append(f"  CPU使用率: {resources['cpu_percent']:.1f}%")
            report.append(f"  内存使用率: {resources['memory_percent']:.1f}% (可用: {resources['memory_available_gb']:.1f} GB)")
            report.append(f"  磁盘使用率: {resources['disk_percent']:.1f}% (可用: {resources['disk_free_gb']:.1f} GB)")
            report.append(f"  网络连接数: {resources['network_connections']}")
        
        if results.get("resources_error"):
            report.append(f"\n⚠️ 资源监控错误: {results['resources_error']}")
        
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)