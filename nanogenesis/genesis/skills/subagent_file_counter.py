import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import os
import subprocess
import json
from typing import Dict, Any

class SubagentFileCounter:
    name = "subagent_file_counter"
    description = "通过派生子代理统计指定目录下的Python文件数量"
    parameters = {
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "要统计的目录路径"
            }
        },
        "required": ["directory"]
    }
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        directory = args.get("directory")
        
        if not directory:
            return {
                "success": False,
                "error": "未提供目录路径"
            }
        
        # 检查目录是否存在
        if not os.path.exists(directory):
            return {
                "success": False,
                "error": f"目录不存在: {directory}"
            }
        
        # 构建子代理命令 - 模拟子代理执行
        # 在实际实现中，这里会调用真正的子代理系统
        # 现在使用直接执行作为演示
        try:
            # 使用find命令统计.py文件
            cmd = f"find '{directory}' -name '*.py' -type f | wc -l"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                count = int(result.stdout.strip())
                
                # 获取文件列表
                list_cmd = f"find '{directory}' -name '*.py' -type f"
                list_result = subprocess.run(list_cmd, shell=True, capture_output=True, text=True)
                files = []
                if list_result.returncode == 0:
                    files = list_result.stdout.strip().split('\n')
                    files = [f for f in files if f]  # 移除空行
                
                return {
                    "success": True,
                    "message": f"子代理已完成文件统计",
                    "data": {
                        "directory": directory,
                        "file_count": count,
                        "files": files,
                        "subagent_report": f"子代理报告：在 {directory} 目录下找到 {count} 个 .py 文件"
                    }
                }
            else:
                return {
                    "success": False,
                    "error": f"子代理执行失败: {result.stderr}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"子代理工具执行异常: {str(e)}"
            }