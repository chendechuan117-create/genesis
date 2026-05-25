import ast
from pathlib import Path
from typing import Dict, Any, List
from genesis.core.base import Tool
from genesis.core.registry import ToolRegistry


def _skill_ast_base_name(base) -> str:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return ""


def _skill_ast_property_string(cls: ast.ClassDef, property_name: str) -> str:
    for item in cls.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) or item.name != property_name:
            continue
        for stmt in item.body:
            if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                return stmt.value.value
    return ""


def _skill_ast_has_member(cls: ast.ClassDef, member_name: str) -> bool:
    return any(isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == member_name for item in cls.body)


def _skill_imports(tree: ast.AST) -> List[str]:
    imports: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return sorted(set(imports))


def _scan_skill_file(path: Path, registry: ToolRegistry = None) -> Dict[str, Any]:
    item = {
        "file": path.name,
        "path": str(path),
        "status": "unknown",
        "tool_classes": [],
        "tool_names": [],
        "registered": False,
        "imports": [],
        "reason": "",
    }
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception as exc:
        item["status"] = "parse_error"
        item["reason"] = str(exc)[:160]
        return item

    item["imports"] = _skill_imports(tree)
    tool_classes = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(_skill_ast_base_name(base) in {"Tool", "MetaTool"} for base in node.bases)
    ]
    if not tool_classes:
        item["status"] = "missing_tool_subclass"
        item["reason"] = "no Tool/MetaTool subclass"
        return item

    registered_names = set(registry.list_tools()) if registry else set()
    schema_incomplete = False
    for cls in tool_classes:
        tool_name = _skill_ast_property_string(cls, "name") or path.stem
        item["tool_classes"].append(cls.name)
        item["tool_names"].append(tool_name)
        if tool_name in registered_names:
            item["registered"] = True
        if not _skill_ast_has_member(cls, "parameters") or not _skill_ast_has_member(cls, "execute"):
            schema_incomplete = True

    reject_reason = None
    if registry and hasattr(registry, "_audit_source_safety"):
        reject_reason = registry._audit_source_safety(source, path.stem)
    if reject_reason:
        item["status"] = "safety_rejected"
        item["reason"] = reject_reason
    elif schema_incomplete:
        item["status"] = "schema_incomplete"
        item["reason"] = "missing parameters or execute member"
    elif item["registered"]:
        item["status"] = "registered"
    else:
        item["status"] = "orphan_candidate"
    return item


class SkillInventoryTool(Tool):
    def __init__(self, registry: ToolRegistry = None, skills_dir: Path = None):
        self.registry = registry
        self.skills_dir = Path(skills_dir) if skills_dir else Path(__file__).parent.parent / "skills"

    @property
    def name(self) -> str:
        return "skill_inventory"

    @property
    def description(self) -> str:
        return "只读扫描本地 genesis/skills 技能资产，报告已注册、孤儿候选、安全拒绝和结构不完整的技能文件；不导入、不执行、不安装依赖。"

    @property
    def cost_estimate(self) -> str:
        return "cheap"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "include_non_tools": {"type": "boolean", "description": "是否包含没有 Tool 子类的普通 Python 文件，默认 false"},
                "limit": {"type": "integer", "description": "最多显示多少条文件记录，默认 40"},
            },
            "required": []
        }

    def is_concurrency_safe(self, arguments: Dict[str, Any]) -> bool:
        return True

    def build_inventory(self, include_non_tools: bool = False, limit: int = 40) -> Dict[str, Any]:
        if not self.skills_dir.exists():
            return {
                "skills_dir": str(self.skills_dir),
                "exists": False,
                "files_total": 0,
                "status_counts": {},
                "items": [],
            }
        skill_paths = [path for path in sorted(self.skills_dir.glob("*.py")) if path.name != "__init__.py"]
        items = []
        for path in skill_paths:
            item = _scan_skill_file(path, self.registry)
            if include_non_tools or item["status"] != "missing_tool_subclass":
                items.append(item)
        status_counts: Dict[str, int] = {}
        for item in items:
            status = item["status"]
            status_counts[status] = status_counts.get(status, 0) + 1
        try:
            limit_value = max(1, int(limit))
        except Exception:
            limit_value = 40
        return {
            "skills_dir": str(self.skills_dir),
            "exists": True,
            "files_total": len(skill_paths),
            "reported_total": len(items),
            "status_counts": status_counts,
            "items": items[:limit_value],
            "omitted": max(0, len(items) - limit_value),
        }

    async def execute(self, include_non_tools: bool = False, limit: int = 40) -> str:
        report = self.build_inventory(include_non_tools=include_non_tools, limit=limit)
        if not report["exists"]:
            return f"⚠️ [技能资产清单] skills_dir 不存在: {report['skills_dir']}"
        lines = [
            "🧭 [技能资产清单] 只读扫描完成（未导入/未执行/未注册）",
            f"dir={report['skills_dir']}",
            f"files={report['files_total']} reported={report['reported_total']} omitted={report.get('omitted', 0)}",
            "status=" + ", ".join(f"{key}:{value}" for key, value in sorted(report["status_counts"].items())),
        ]
        for item in report["items"]:
            names = ",".join(item["tool_names"]) if item["tool_names"] else "-"
            reason = f" reason={item['reason']}" if item.get("reason") else ""
            lines.append(f"- {item['file']} status={item['status']} tools={names}{reason}")
        return "\n".join(lines)

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
