
from pathlib import Path
from typing import Dict, Any
from core.base import Tool
from core.registry import ToolRegistry

class SkillCreatorTool(Tool):
    """技能生成工具：允许 Agent 编写新工具并动态加载"""
    
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self.skills_dir = Path(__file__).parent.parent / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        
    @property
    def name(self) -> str:
        return "skill_creator"
    
    @property
    def description(self) -> str:
        return """创建并加载新的 Python 工具技能。
        当你遇到现有工具无法解决的问题（如需要特定的数据解析、复杂的算法计算、或多模态文件处理）时，
        使用此工具编写一个新的 Python 脚本作为工具。
        
        代码要求：
        1. 必须定义一个继承自 Tool 的类
        2. 必须包含 name, description, parameters 属性和 execute 方法
        3. 不需要包含 'from core.base import Tool'，系统会自动处理或请使用相对导入
        """
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "技能名称 (纯小写字母和下划线，例如 'pdf_parser')"
                },
                "python_code": {
                    "type": "string",
                    "description": "完整的 Python 代码内容"
                }
            },
            "required": ["skill_name", "python_code"]
        }
    
    async def execute(self, skill_name: str, python_code: str) -> str:
        try:
            # 1. 验证文件名
            if not skill_name.isidentifier():
                return "Error: skill_name 必须是合法的 Python 标识符"
                
            file_path = self.skills_dir / f"{skill_name}.py"
            
            # 2. 写入文件
            # 自动添加必要的导入路径修正
            header = "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parent.parent))\nfrom core.base import Tool\n\n"
            
            # 如果代码里已经有了 import Tool，就不要重复添加太乱的 header
            if "from core.base import Tool" in python_code:
                full_code = python_code
            else:
                full_code = header + python_code
                
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(full_code)
                
            # 3. 动态加载
            success = self.registry.load_from_file(str(file_path))
            
            if success:
                return f"✓ 技能 '{skill_name}' 已创建并成功加载。现在可以直接调用它了。"
            else:
                return f"⚠️ 技能文件已创建 ({file_path})，但加载失败。请检查代码语法或类定义。"
                
        except Exception as e:
            return f"Error: 创建技能失败 - {str(e)}"
