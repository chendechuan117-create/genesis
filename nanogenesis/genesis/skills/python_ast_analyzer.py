import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import ast
import json
from typing import Dict, List, Any


class PythonASTAnalyzer:
    """Python AST代码分析器"""
    
    def __init__(self):
        self.name = "python_ast_analyzer"
        self.description = "使用Python AST库分析Python代码结构，提取类和方法信息"
        self.parameters = {
            "file_path": {
                "type": "string",
                "description": "要分析的Python文件路径",
                "required": True
            }
        }
    
    def execute(self, file_path: str) -> Dict[str, Any]:
        """执行分析"""
        try:
            return self._analyze_file(file_path)
        except Exception as e:
            return {"error": f"分析失败: {str(e)}"}
    
    def _analyze_file(self, file_path: str) -> Dict[str, Any]:
        """分析Python文件并提取类和方法信息"""
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        tree = ast.parse(source_code)
        
        result = {
            "file": file_path,
            "classes": [],
            "summary": {
                "total_classes": 0,
                "total_methods": 0
            }
        }
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_info = self._extract_class_info(node)
                result["classes"].append(class_info)
                result["summary"]["total_classes"] += 1
                result["summary"]["total_methods"] += len(class_info["methods"])
        
        return result
    
    def _extract_class_info(self, class_node: ast.ClassDef) -> Dict[str, Any]:
        """提取类信息"""
        class_info = {
            "name": class_node.name,
            "line": class_node.lineno,
            "bases": [],
            "decorators": [],
            "methods": []
        }
        
        # 提取基类
        for base in class_node.bases:
            if isinstance(base, ast.Name):
                class_info["bases"].append(base.id)
            elif isinstance(base, ast.Attribute):
                class_info["bases"].append(self._get_attribute_name(base))
        
        # 提取装饰器
        for decorator in class_node.decorator_list:
            if isinstance(decorator, ast.Name):
                class_info["decorators"].append(decorator.id)
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name):
                    class_info["decorators"].append(decorator.func.id)
        
        # 提取方法
        for node in class_node.body:
            if isinstance(node, ast.FunctionDef):
                method_info = self._extract_method_info(node)
                class_info["methods"].append(method_info)
            elif isinstance(node, ast.AsyncFunctionDef):
                method_info = self._extract_method_info(node)
                method_info["is_async"] = True
                class_info["methods"].append(method_info)
        
        return class_info
    
    def _extract_method_info(self, func_node: ast.FunctionDef) -> Dict[str, Any]:
        """提取方法信息"""
        method_info = {
            "name": func_node.name,
            "line": func_node.lineno,
            "is_async": False,
            "decorators": [],
            "args": []
        }
        
        # 提取装饰器
        for decorator in func_node.decorator_list:
            if isinstance(decorator, ast.Name):
                method_info["decorators"].append(decorator.id)
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name):
                    method_info["decorators"].append(decorator.func.id)
        
        # 提取参数
        args = func_node.args
        if args.posonlyargs:
            method_info["args"].extend([arg.arg for arg in args.posonlyargs])
        if args.args:
            method_info["args"].extend([arg.arg for arg in args.args])
        if args.vararg:
            method_info["args"].append(f"*{args.vararg.arg}")
        if args.kwonlyargs:
            method_info["args"].extend([arg.arg for arg in args.kwonlyargs])
        if args.kwarg:
            method_info["args"].append(f"**{args.kwarg.arg}")
        
        return method_info
    
    def _get_attribute_name(self, node: ast.Attribute) -> str:
        """获取属性名称"""
        if isinstance(node.value, ast.Name):
            return f"{node.value.id}.{node.attr}"
        elif isinstance(node.value, ast.Attribute):
            return f"{self._get_attribute_name(node.value)}.{node.attr}"
        return node.attr


# 创建Tool类供系统使用
class Tool:
    def __init__(self):
        self.name = "python_ast_analyzer"
        self.description = "使用Python AST库分析Python代码结构，提取类和方法信息"
        self.parameters = {
            "file_path": {
                "type": "string",
                "description": "要分析的Python文件路径",
                "required": True
            }
        }
    
    def execute(self, file_path: str) -> Dict[str, Any]:
        analyzer = PythonASTAnalyzer()
        return analyzer.execute(file_path)