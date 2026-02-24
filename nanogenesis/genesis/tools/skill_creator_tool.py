
from pathlib import Path
from typing import Dict, Any
from genesis.core.base import Tool
from genesis.core.registry import ToolRegistry

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
        当你遇到现有工具无法解决的问题时，使用此工具编写一个新的 Python 脚本作为工具。
        
        【极度严苛的代码要求】:
        1. 必须定义一个继承自 `Tool` 的类。
        2. 必须且只能包含以下 4 个方法/属性 (name, description, parameters, execute)。
        3. 🔴 **绝对禁止阻塞主线程**：`execute` 方法内部绝对不能出现无限 `while True:` 循环或长时间的同步 `sleep`。
           如果你的工具是一个持续监控的后台任务（如 activity_monitor），你必须在 `execute` 内使用 `subprocess.Popen` 或 `asyncio.create_task` 将死循环**抛到后台运行**，并且**立刻 `return` 一个状态字符串**给主循环！工具执行卡住会导致整个大模型死机！
        
        下面是你能且只能使用的绝对模板（请直接复制并修改其中的功能逻辑）：
        
        ```python
        class MyCustomTool(Tool):
            @property
            def name(self) -> str:
                return "my_custom_tool" # 必须是纯小写字母和下划线
                
            @property
            def description(self) -> str:
                return "这个工具的详细描述，告诉系统什么时候该用它。"
                
            @property
            def parameters(self) -> dict:
                # 必须返回严格的 JSON Schema
                return {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "描述1"}
                    },
                    "required": ["param1"]
                }
                
            async def execute(self, param1: str) -> str:
                # 你的核心逻辑写在这里。必须返回字符串。
                return "执行结果"
        ```
        
        注意：不需要包含 `from genesis.core.base import Tool`，底层会自动注入。
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
            header = "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parent.parent))\nfrom genesis.core.base import Tool\n\n"
            
            # 如果代码里已经有了 import Tool，就不要重复添加太乱的 header
            if "from genesis.core.base import Tool" in python_code:
                full_code = python_code
            else:
                full_code = header + python_code
                
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(full_code)
                
            # 3. 动态加载 & 验证
            success = self.registry.load_from_file(str(file_path))
            
            if success:
                # 3.1 验证 Schema (Fundamental Fix)
                # Just because it loaded doesn't mean it works. We must validate the constraints.
                tool_instance = self.registry.get(skill_name)
                if tool_instance:
                    try:
                        schema = tool_instance.to_schema()
                        params = schema['function']['parameters']
                        if not isinstance(params, dict) or params.get('type') != 'object':
                            # Rollback
                            self.registry.unregister(skill_name)
                            return f"⚠️ 技能创建失败: 工具 '{skill_name}' 的 parameters 属性无效。必须返回 JSON Schema 字典 ('type': 'object')。"
                    except Exception as e:
                        self.registry.unregister(skill_name)
                        return f"⚠️ 技能创建失败: 无法生成 Schema - {e}"

                return f"✓ 技能 '{skill_name}' 已创建并成功加载。现在可以直接调用它了。"
            else:
                return f"⚠️ 技能文件已创建 ({file_path})，但加载失败。请检查代码语法或类定义。"
                
        except Exception as e:
            return f"Error: 创建技能失败 - {str(e)}"
