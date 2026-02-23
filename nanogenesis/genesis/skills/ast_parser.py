import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import ast
import os
from typing import Dict, List, Any

class ASTParser:
    def __init__(self):
        self.name = "ast_parser"
        self.description = "使用Python的ast库解析Python文件，提取类和方法信息"
        self.parameters = {
            "file_path": {
                "type": "string",
                "description": "要分析的Python文件路径",
                "required": True
            }
        }
    
    def execute(self, file_path: str) -> Dict[str, Any]:
        """
        解析Python文件并提取类和方法信息
        """
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
                            method_info = {
                                "method_name": item.name,
                                "line_number": item.lineno,
                                "is_async": False
                            }
                            class_info["methods"].append(method_info)
                        elif isinstance(item, ast.AsyncFunctionDef):
                            method_info = {
                                "method_name": item.name,
                                "line_number": item.lineno,
                                "is_async": True
                            }
                            class_info["methods"].append(method_info)
                    
                    classes.append(class_info)
            
            # 统计信息
            total_classes = len(classes)
            total_methods = sum(len(cls["methods"]) for cls in classes)
            
            return {
                "success": True,
                "file_path": file_path,
                "file_size": len(content),
                "total_classes": total_classes,
                "total_methods": total_methods,
                "classes": classes,
                "summary": f"找到 {total_classes} 个类，共 {total_methods} 个方法"
            }
            
        except SyntaxError as e:
            return {
                "success": False,
                "error": f"语法错误: {str(e)}",
                "line": e.lineno,
                "offset": e.offset
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"解析错误: {str(e)}"
            }

# 创建工具实例
tool = ASTParser()