import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import ast
import os

class SimpleASTParser:
    def __init__(self):
        self.name = "simple_ast_parser"
        self.description = "简单的Python AST解析工具，提取类和方法名"
        self.parameters = {
            "file_path": {
                "type": "string",
                "description": "要分析的Python文件路径",
                "required": True
            }
        }
    
    def execute(self, file_path):
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "error": f"文件不存在: {file_path}"
                }
            
            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析AST
            tree = ast.parse(content, filename=file_path)
            
            # 提取类和方法信息
            classes = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_info = {
                        "class_name": node.name,
                        "line_number": node.lineno,
                        "methods": []
                    }
                    
                    # 提取类中的方法
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            class_info["methods"].append({
                                "name": item.name,
                                "line": item.lineno,
                                "type": "function"
                            })
                        elif isinstance(item, ast.AsyncFunctionDef):
                            class_info["methods"].append({
                                "name": item.name,
                                "line": item.lineno,
                                "type": "async_function"
                            })
                    
                    classes.append(class_info)
            
            # 创建格式化输出
            result = {
                "success": True,
                "file_path": file_path,
                "total_classes": len(classes),
                "classes": classes
            }
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

# 创建工具实例
tool = SimpleASTParser()