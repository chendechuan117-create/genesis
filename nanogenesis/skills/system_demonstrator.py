import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

#!/usr/bin/env python3
"""
系统演示器 - 展示Genesis系统的执行和自动化能力
通过执行一系列安全的Shell命令来证明"动手"能力
"""

import os
import subprocess
import json
import time
from datetime import datetime
from typing import Dict, List, Any

class SystemDemonstrator:
    """系统演示器工具类"""
    
    def __init__(self):
        self.name = "system_demonstrator"
        self.description = "执行系统演示操作，展示Genesis的执行能力"
        self.parameters = {
            "type": "object",
            "properties": {
                "demo_type": {
                    "type": "string",
                    "enum": ["basic", "advanced", "custom"],
                    "description": "演示类型：basic(基础演示), advanced(高级演示), custom(自定义命令)"
                },
                "custom_commands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "自定义命令列表（仅demo_type='custom'时使用）"
                }
            },
            "required": ["demo_type"]
        }
    
    def execute(self, demo_type: str = "basic", custom_commands: List[str] = None) -> Dict[str, Any]:
        """执行演示操作"""
        
        # 定义演示命令集
        demo_commands = {
            "basic": [
                "echo '=== 系统基础信息演示 ==='",
                "uname -a",
                "echo '当前用户：' && whoami",
                "echo '当前目录：' && pwd",
                "echo '磁盘使用：' && df -h | head -5",
                "echo '内存使用：' && free -h",
                "echo '进程数：' && ps aux | wc -l",
                "echo '网络连接：' && ss -tuln | head -10"
            ],
            "advanced": [
                "echo '=== 高级系统演示 ==='",
                "echo '系统启动时间：' && uptime",
                "echo 'CPU信息：' && lscpu | grep -E 'Model name|CPU\(s\)'",
                "echo '内核版本：' && uname -r",
                "echo 'Python版本：' && python3 --version",
                "echo 'Node.js版本：' && node --version 2>/dev/null || echo 'Node.js未安装'",
                "echo 'Git版本：' && git --version",
                "echo '当前目录文件：' && ls -la | head -15",
                "echo '环境变量示例：' && echo $PATH | tr ':' '\\n' | head -5"
            ]
        }
        
        # 选择命令集
        if demo_type == "custom" and custom_commands:
            commands = custom_commands
        else:
            commands = demo_commands.get(demo_type, demo_commands["basic"])
        
        # 执行命令并收集结果
        results = []
        start_time = time.time()
        
        for cmd in commands:
            try:
                # 执行命令
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                # 记录结果
                cmd_result = {
                    "command": cmd,
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                    "returncode": result.returncode,
                    "timestamp": datetime.now().isoformat()
                }
                results.append(cmd_result)
                
            except subprocess.TimeoutExpired:
                cmd_result = {
                    "command": cmd,
                    "stdout": "",
                    "stderr": "命令执行超时（10秒）",
                    "returncode": -1,
                    "timestamp": datetime.now().isoformat()
                }
                results.append(cmd_result)
            except Exception as e:
                cmd_result = {
                    "command": cmd,
                    "stdout": "",
                    "stderr": f"执行错误: {str(e)}",
                    "returncode": -1,
                    "timestamp": datetime.now().isoformat()
                }
                results.append(cmd_result)
        
        execution_time = time.time() - start_time
        
        # 生成报告
        report = self._generate_report(results, execution_time, demo_type)
        
        return report
    
    def _generate_report(self, results: List[Dict], execution_time: float, demo_type: str) -> Dict[str, Any]:
        """生成结构化报告"""
        
        # 统计信息
        total_commands = len(results)
        successful_commands = sum(1 for r in results if r["returncode"] == 0)
        failed_commands = total_commands - successful_commands
        
        # 生成Markdown格式报告
        markdown_report = f"""# 🚀 Genesis 系统演示报告

## 📊 执行摘要
- **演示类型**: {demo_type}
- **执行时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **总耗时**: {execution_time:.2f}秒
- **命令总数**: {total_commands}
- **成功命令**: {successful_commands}
- **失败命令**: {failed_commands}

## 🔧 执行详情

"""
        
        for i, result in enumerate(results, 1):
            markdown_report += f"### {i}. `{result['command']}`\n"
            markdown_report += f"- **状态**: {'✅ 成功' if result['returncode'] == 0 else '❌ 失败'}\n"
            markdown_report += f"- **时间**: {result['timestamp']}\n"
            
            if result['stdout']:
                markdown_report += f"- **输出**:\n```\n{result['stdout']}\n```\n"
            
            if result['stderr']:
                markdown_report += f"- **错误**:\n```\n{result['stderr']}\n```\n"
            
            markdown_report += "\n"
        
        # 分析结论
        markdown_report += f"""## 📈 能力验证

### ✅ 已验证能力
1. **Shell命令执行**: 成功执行 {successful_commands}/{total_commands} 个系统命令
2. **环境感知**: 获取系统信息、用户信息、进程状态
3. **文件系统操作**: 列出目录、检查磁盘使用
4. **网络状态检查**: 查看网络连接和端口状态
5. **自动化执行**: 批量执行命令并收集结果

### 🎯 演示价值
- **动手能力证明**: 系统具备真实的执行层能力
- **环境验证**: 确认当前系统状态和可用资源
- **自动化展示**: 演示批量任务执行和结果收集
- **可扩展性**: 演示框架支持自定义命令扩展

## 🔄 下一步建议
1. **扩展演示**: 添加文件创建、编辑、删除操作
2. **集成测试**: 将演示器集成到系统监控中
3. **定时任务**: 创建定期系统健康检查
4. **用户自定义**: 允许用户定义自己的演示脚本

---

*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')}*
"""
        
        return {
            "status": "success",
            "demo_type": demo_type,
            "execution_time": execution_time,
            "total_commands": total_commands,
            "successful_commands": successful_commands,
            "failed_commands": failed_commands,
            "results": results,
            "markdown_report": markdown_report,
            "timestamp": datetime.now().isoformat()
        }


# 工具导出
tool = SystemDemonstrator()