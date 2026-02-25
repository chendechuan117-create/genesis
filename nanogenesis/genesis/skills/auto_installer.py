import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class AutoInstallerTool(Tool):
    @property
    def name(self) -> str:
        return "auto_installer"
        
    @property
    def description(self) -> str:
        return "自动化安装工具，支持pacman包管理器的批量安装、依赖检查和进度报告。适用于展示自动化能力。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "packages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要安装的软件包列表"
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "模拟运行，不实际安装",
                    "default": False
                },
                "skip_deps": {
                    "type": "boolean",
                    "description": "跳过依赖检查",
                    "default": False
                }
            },
            "required": ["packages"]
        }
        
    async def execute(self, packages: list, dry_run: bool = False, skip_deps: bool = False) -> str:
        import subprocess
        import json
        
        results = {
            "total": len(packages),
            "success": 0,
            "failed": 0,
            "details": []
        }
        
        for package in packages:
            try:
                # 检查包是否存在
                check_cmd = ["pacman", "-Si", package]
                check_result = subprocess.run(check_cmd, capture_output=True, text=True)
                
                if check_result.returncode != 0:
                    results["details"].append({
                        "package": package,
                        "status": "not_found",
                        "error": f"Package '{package}' not found in repositories"
                    })
                    results["failed"] += 1
                    continue
                
                if dry_run:
                    results["details"].append({
                        "package": package,
                        "status": "dry_run",
                        "message": f"Would install '{package}'"
                    })
                    results["success"] += 1
                    continue
                
                # 实际安装
                install_cmd = ["sudo", "pacman", "-S", "--noconfirm"]
                if skip_deps:
                    install_cmd.append("--nodeps")
                install_cmd.append(package)
                
                install_result = subprocess.run(
                    install_cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5分钟超时
                )
                
                if install_result.returncode == 0:
                    results["details"].append({
                        "package": package,
                        "status": "installed",
                        "output": install_result.stdout[:500]  # 截取前500字符
                    })
                    results["success"] += 1
                else:
                    results["details"].append({
                        "package": package,
                        "status": "failed",
                        "error": install_result.stderr[:500],
                        "returncode": install_result.returncode
                    })
                    results["failed"] += 1
                    
            except subprocess.TimeoutExpired:
                results["details"].append({
                    "package": package,
                    "status": "timeout",
                    "error": "Installation timed out after 5 minutes"
                })
                results["failed"] += 1
            except Exception as e:
                results["details"].append({
                    "package": package,
                    "status": "error",
                    "error": str(e)
                })
                results["failed"] += 1
        
        # 生成报告
        report = f"## 📦 自动化安装报告\n\n"
        report += f"**总计**: {results['total']} 个包\n"
        report += f"**成功**: {results['success']} 个\n"
        report += f"**失败**: {results['failed']} 个\n\n"
        
        if dry_run:
            report += "🔍 **模拟运行模式** (未实际安装)\n\n"
        
        for detail in results["details"]:
            status_emoji = {
                "installed": "✅",
                "dry_run": "🔍",
                "not_found": "❌",
                "failed": "❌",
                "timeout": "⏰",
                "error": "⚠️"
            }.get(detail["status"], "❓")
            
            report += f"{status_emoji} **{detail['package']}** - {detail['status']}\n"
            if "error" in detail:
                report += f"   错误: {detail['error']}\n"
            if "message" in detail:
                report += f"   信息: {detail['message']}\n"
            report += "\n"
        
        return report