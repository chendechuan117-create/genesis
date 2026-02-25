import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class ASTParserTool(Tool):
    @property
    def name(self) -> str:
        return "ast_parser"
        
    @property
    def description(self) -> str:
        return "使用Python的ast库解析Python源文件，提取所有类名及其方法签名。"
        
    @property
    def parameters(self) -> dict:
        # 必须返回严格的 JSON Schema
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "要解析的Python源文件的路径"}
            },
            "required": ["file_path"]
        }
        
    async def execute(self, file_path: str) -> str:
        import ast
        import os
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return f"错误：文件 '{file_path}' 不存在。"
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return f"读取文件时出错：{e}"
        
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return f"Python语法错误，无法解析AST：{e}"
        
        result = []
        
        # 遍历AST树，查找类定义
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_name = node.name
                methods = []
                
                # 遍历类体，查找函数定义（方法）
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        method_name = item.name
                        # 构建方法签名：方法名(参数列表)
                        args = item.args
                        arg_names = []
                        # 位置参数
                        for arg in args.args:
                            arg_names.append(arg.arg)
                        # *args
                        if args.vararg:
                            arg_names.append(f"*{args.vararg.arg}")
                        # 仅限关键字参数（Python 3.8+ 使用 args.kwonlyargs）
                        for arg in args.kwonlyargs:
                            arg_names.append(arg.arg)
                        # **kwargs
                        if args.kwarg:
                            arg_names.append(f"**{args.kwarg.arg}")
                        
                        signature = f"{method_name}({', '.join(arg_names)})"
                        methods.append(signature)
                
                result.append({
                    "class": class_name,
                    "methods": methods
                })
        
        # 格式化输出
        if not result:
            return "该文件中未找到任何类定义。"
        
        output_lines = []
        for cls_info in result:
            output_lines.append(f"类: {cls_info['class']}")
            if cls_info['methods']:
                for method in cls_info['methods']:
                    output_lines.append(f"  - {method}")
            else:
                output_lines.append(f"  (无方法)")
            output_lines.append("")  # 空行分隔
        
        return "\n".join(output_lines).strip()