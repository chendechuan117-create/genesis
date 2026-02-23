import ast
import json
from typing import Dict, List, Any
from genesis.core.base import Tool


class ASTCodeParser(Tool):
    """Python AST代码解析器 - 提取类和方法信息"""
    
    @property
    def name(self) -> str:
        return "ast_code_parser"
    
    @property
    def description(self) -> str:
        return "使用Python AST库分析Python代码结构，提取所有类及其方法名"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要分析的Python文件路径"
                }
            },
            "required": ["file_path"]
        }
    
    async def execute(self, file_path: str) -> str:
        """执行AST分析"""
        try:
            result = self._analyze_file(file_path)
            return json.dumps(result, indent=2, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
    
    def _analyze_file(self, file_path: str) -> Dict[str, Any]:
        """分析Python文件并提取类和方法信息"""
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        tree = ast.parse(source_code)
        
        classes = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_info = self._extract_class_info(node)
                classes.append(class_info)
        
        # 创建简洁的报告
        report = {
            "file": file_path,
            "summary": {
                "total_classes": len(classes),
                "total_methods": sum(len(c["methods"]) for c in classes)
            },
            "classes": []
        }
        
        for class_info in classes:
            class_summary = {
                "class_name": class_info["name"],
                "line": class_info["line"],
                "bases": class_info["bases"],
                "methods": []
            }
            
            for method in class_info["methods"]:
                method_summary = {
                    "method_name": method["name"],
                    "line": method["line"],
                    "is_async": method.get("is_async", False)
                }
                class_summary["methods"].append(method_summary)
            
            report["classes"].append(class_summary)
        
        return report
    
    def _extract_class_info(self, class_node: ast.ClassDef) -> Dict[str, Any]:
        """提取类信息"""
        class_info = {
            "name": class_node.name,
            "line": class_node.lineno,
            "bases": [],
            "methods": []
        }
        
        # 提取基类
        for base in class_node.bases:
            if isinstance(base, ast.Name):
                class_info["bases"].append(base.id)
            elif isinstance(base, ast.Attribute):
                class_info["bases"].append(self._get_attribute_name(base))
        
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
            "is_async": False
        }
        
        return method_info
    
    def _get_attribute_name(self, node: ast.Attribute) -> str:
        """获取属性名称"""
        if isinstance(node.value, ast.Name):
            return f"{node.value.id}.{node.attr}"
        elif isinstance(node.value, ast.Attribute):
            return f"{self._get_attribute_name(node.value)}.{node.attr}"
        return node.attr