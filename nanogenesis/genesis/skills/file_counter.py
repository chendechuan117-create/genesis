import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import os

class FileCounter:
    name = "file_counter"
    description = "统计目录中的Python文件数量"
    
    def execute(self, args):
        # 模拟子代理行为
        print("子代理启动：开始统计文件...")
        
        directory = args.get("directory", "genesis/tools/")
        
        try:
            # 使用os.walk统计.py文件
            py_files = []
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.endswith('.py'):
                        py_files.append(os.path.join(root, file))
            
            count = len(py_files)
            
            # 生成子代理报告
            report = f"""
            🚀 子代理统计报告 🚀
            
            任务目标：统计 {directory} 目录下的 .py 文件
            执行代理：子代理 #001
            执行时间：现在
            
            📊 统计结果：
            - 目录：{directory}
            - .py 文件总数：{count} 个
            
            📁 文件列表（前10个）：
            """
            
            for i, file in enumerate(py_files[:10]):
                report += f"  {i+1}. {os.path.basename(file)}\n"
            
            if len(py_files) > 10:
                report += f"  ... 还有 {len(py_files)-10} 个文件\n"
            
            report += "\n✅ 子代理任务完成！"
            
            return {
                "success": True,
                "message": "子代理统计完成",
                "report": report,
                "data": {
                    "directory": directory,
                    "file_count": count,
                    "files": py_files
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"子代理执行失败: {str(e)}"
            }