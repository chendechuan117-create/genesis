import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import os
import subprocess

class SimpleSubagentCounter:
    name = "simple_subagent_counter"
    description = "简单的子代理文件计数器"
    
    def execute(self, args):
        directory = args.get("directory", "genesis/tools/")
        
        # 模拟子代理执行
        print(f"子代理开始工作：正在统计 {directory} 目录下的 .py 文件...")
        
        try:
            # 统计文件数量
            count_cmd = f"find '{directory}' -name '*.py' -type f | wc -l"
            count_result = subprocess.run(count_cmd, shell=True, capture_output=True, text=True)
            
            if count_result.returncode != 0:
                return {
                    "success": False,
                    "error": f"统计失败: {count_result.stderr}"
                }
            
            count = int(count_result.stdout.strip())
            
            # 获取文件列表
            list_cmd = f"find '{directory}' -name '*.py' -type f"
            list_result = subprocess.run(list_cmd, shell=True, capture_output=True, text=True)
            
            files = []
            if list_result.returncode == 0:
                files = [f for f in list_result.stdout.strip().split('\n') if f]
            
            # 子代理报告
            report = f"""
            ===== 子代理统计报告 =====
            任务：统计 {directory} 目录下的 .py 文件
            执行时间：{subprocess.getoutput('date')}
            
            统计结果：
            - 总文件数：{count} 个 .py 文件
            
            文件列表：
            {chr(10).join([f'  {i+1}. {os.path.basename(f)}' for i, f in enumerate(files[:10]])}
            {f'  ... 还有 {len(files)-10} 个文件' if len(files) > 10 else ''}
            
            子代理任务完成！
            =========================
            """
            
            return {
                "success": True,
                "message": "子代理统计完成",
                "report": report,
                "data": {
                    "directory": directory,
                    "file_count": count,
                    "files": files,
                    "files_count": len(files)
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"子代理执行异常: {str(e)}"
            }