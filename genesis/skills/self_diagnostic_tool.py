import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class SelfDiagnosticTool(Tool):
    @property
    def name(self) -> str:
        return "self_diagnostic_tool"
        
    @property
    def description(self) -> str:
        return "自我诊断工具，用于检测系统状态、工具健康度和预防死循环等问题"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "check_type": {
                    "type": "string", 
                    "enum": ["full", "tools", "memory", "loops", "quick"],
                    "description": "检查类型：full(全面检查), tools(工具健康度), memory(内存状态), loops(死循环检测), quick(快速检查)",
                    "default": "quick"
                },
                "max_depth": {
                    "type": "integer",
                    "description": "递归深度检查限制",
                    "default": 10
                }
            },
            "required": []
        }
        
    async def execute(self, check_type: str = "quick", max_depth: int = 10) -> str:
        import subprocess
        import json
        import time
        import sys
        import os
        from datetime import datetime
        
        results = []
        
        def add_result(category, status, message, details=None):
            results.append({
                "category": category,
                "status": status,
                "message": message,
                "details": details,
                "timestamp": datetime.now().isoformat()
            })
        
        # 1. 系统资源检查
        if check_type in ["full", "quick", "memory"]:
            try:
                # 检查内存使用
                import psutil
                memory = psutil.virtual_memory()
                cpu_percent = psutil.cpu_percent(interval=0.1)
                
                add_result("system_resources", 
                          "healthy" if memory.percent < 90 and cpu_percent < 90 else "warning",
                          f"系统资源正常: CPU {cpu_percent}%, 内存 {memory.percent}%",
                          {"cpu_percent": cpu_percent, "memory_percent": memory.percent})
            except Exception as e:
                add_result("system_resources", "error", f"系统资源检查失败: {e}")
        
        # 2. 工具健康度检查
        if check_type in ["full", "tools", "quick"]:
            try:
                # 测试shell工具
                result = subprocess.run(["echo", "tool_test"], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    add_result("shell_tool", "healthy", "Shell工具工作正常")
                else:
                    add_result("shell_tool", "error", f"Shell工具异常: {result.stderr}")
            except Exception as e:
                add_result("shell_tool", "error", f"Shell工具检查失败: {e}")
            
            # 测试文件操作
            try:
                test_file = "/tmp/diagnostic_test.txt"
                with open(test_file, "w") as f:
                    f.write("test")
                with open(test_file, "r") as f:
                    content = f.read()
                os.remove(test_file)
                add_result("file_operations", "healthy", "文件操作正常")
            except Exception as e:
                add_result("file_operations", "error", f"文件操作异常: {e}")
        
        # 3. n8n服务检查
        if check_type in ["full", "quick"]:
            try:
                import requests
                response = requests.get("http://localhost:5678/healthz", timeout=5)
                if response.status_code == 200:
                    add_result("n8n_service", "healthy", f"n8n服务正常: {response.text}")
                else:
                    add_result("n8n_service", "warning", f"n8n服务异常: {response.status_code}")
            except Exception as e:
                add_result("n8n_service", "error", f"n8n服务检查失败: {e}")
        
        # 4. 死循环检测（模拟）
        if check_type in ["full", "loops"]:
            # 检查递归深度
            current_depth = sys.getrecursionlimit()
            add_result("recursion_depth", 
                      "healthy" if current_depth <= max_depth else "warning",
                      f"递归深度限制: {current_depth}",
                      {"current_depth": current_depth, "max_depth": max_depth})
        
        # 5. 工作坊状态检查
        if check_type in ["full", "quick"]:
            try:
                # 检查工作坊文件是否存在
                workshop_path = os.path.expanduser("~/.genesis/workshop.db")
                if os.path.exists(workshop_path):
                    file_size = os.path.getsize(workshop_path)
                    add_result("workshop", "healthy", 
                              f"工作坊文件存在，大小: {file_size} bytes",
                              {"path": workshop_path, "size": file_size})
                else:
                    add_result("workshop", "warning", "工作坊文件不存在")
            except Exception as e:
                add_result("workshop", "error", f"工作坊检查失败: {e}")
        
        # 生成报告
        total_checks = len(results)
        healthy_count = sum(1 for r in results if r["status"] == "healthy")
        warning_count = sum(1 for r in results if r["status"] == "warning")
        error_count = sum(1 for r in results if r["status"] == "error")
        
        report = f"""
🔍 自我诊断报告
========================================
检查类型: {check_type}
检查时间: {datetime.now().isoformat()}
检查项目: {total_checks} 项

📊 检查结果:
✅ 健康: {healthy_count} 项
⚠️  警告: {warning_count} 项
❌ 错误: {error_count} 项

📋 详细结果:
"""
        
        for result in results:
            status_icon = "✅" if result["status"] == "healthy" else "⚠️ " if result["status"] == "warning" else "❌"
            report += f"\n{status_icon} {result['category']}: {result['message']}"
            if result.get('details'):
                report += f"\n   详情: {json.dumps(result['details'], ensure_ascii=False)}"
        
        report += f"\n\n💡 建议:"
        if error_count > 0:
            report += "\n- 存在错误项，建议优先修复"
        if warning_count > 0:
            report += "\n- 存在警告项，建议关注并优化"
        if healthy_count == total_checks:
            report += "\n- 所有检查项正常，系统状态良好"
        
        report += "\n========================================"
        
        return report