import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

import os
import json
import datetime
from pathlib import Path

class ContextCapture:
    """捕获当前对话上下文并结构化为可查询的快照"""
    
    name = "context_capture"
    description = "捕获当前对话的上下文信息，包括工作目录、文件状态、时间等元数据"
    parameters = {
        "type": "object",
        "properties": {
            "save_to_memory": {
                "type": "boolean",
                "description": "是否将上下文保存到长期记忆",
                "default": True
            }
        }
    }
    
    def execute(self, save_to_memory=True):
        """执行上下文捕获"""
        try:
            # 获取当前时间
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 获取工作目录信息
            cwd = os.getcwd()
            cwd_path = Path(cwd)
            
            # 列出当前目录内容
            dir_contents = []
            try:
                for item in os.listdir(cwd):
                    item_path = cwd_path / item
                    stat = item_path.stat()
                    dir_contents.append({
                        "name": item,
                        "is_dir": item_path.is_dir(),
                        "size": stat.st_size,
                        "modified": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "extension": item_path.suffix if not item_path.is_dir() else ""
                    })
            except Exception as e:
                dir_contents = [{"error": str(e)}]
            
            # 获取最近修改的文件（前5个）
            recent_files = []
            try:
                all_files = []
                for root, dirs, files in os.walk(cwd, topdown=True):
                    for file in files:
                        file_path = Path(root) / file
                        try:
                            stat = file_path.stat()
                            all_files.append({
                                "path": str(file_path.relative_to(cwd)),
                                "modified": stat.st_mtime,
                                "size": stat.st_size
                            })
                        except:
                            continue
                
                # 按修改时间排序
                all_files.sort(key=lambda x: x["modified"], reverse=True)
                recent_files = all_files[:5]
                
                # 格式化时间
                for file_info in recent_files:
                    file_info["modified"] = datetime.datetime.fromtimestamp(file_info["modified"]).strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                recent_files = [{"error": str(e)}]
            
            # 构建上下文对象
            context = {
                "timestamp": current_time,
                "working_directory": cwd,
                "directory_contents": dir_contents,
                "recent_files": recent_files,
                "environment": {
                    "user": os.environ.get("USER", "unknown"),
                    "home": os.environ.get("HOME", ""),
                    "shell": os.environ.get("SHELL", "")
                },
                "system_info": {
                    "platform": os.uname().sysname if hasattr(os, 'uname') else "unknown",
                    "node": os.uname().nodename if hasattr(os, 'uname') else "unknown"
                }
            }
            
            result = {
                "success": True,
                "context": context,
                "summary": f"已捕获上下文：{cwd} 中的 {len(dir_contents)} 个项目，{len(recent_files)} 个最近文件"
            }
            
            # 如果需要保存到记忆
            if save_to_memory:
                try:
                    # 这里假设有 memory_tool 可用
                    # 在实际实现中，这里会调用 memory_tool.save
                    memory_content = json.dumps({
                        "type": "context_snapshot",
                        "timestamp": current_time,
                        "query": "ambiguous_query_context",
                        "data": context
                    }, ensure_ascii=False, indent=2)
                    
                    # 保存到文件作为临时方案
                    context_file = cwd_path / ".last_context.json"
                    with open(context_file, 'w', encoding='utf-8') as f:
                        f.write(memory_content)
                    
                    result["memory_saved"] = True
                    result["memory_file"] = str(context_file)
                except Exception as e:
                    result["memory_saved"] = False
                    result["memory_error"] = str(e)
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }