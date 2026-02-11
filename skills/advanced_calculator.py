import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool


from typing import Dict, Any
import math

class AdvancedCalculator(Tool):
    @property
    def name(self) -> str:
        return "advanced_calculator"
        
    @property
    def description(self) -> str:
        return "执行高级数学计算 (支持 math 库函数)"
        
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式 (例如: math.sqrt(16) * 10)"
                }
            },
            "required": ["expression"]
        }
        
    async def execute(self, expression: str) -> str:
        try:
            # 安全警告: eval 是危险的，但在演示沙箱中可控
            # 在实际生产中应使用更安全的计算库
            allowed_names = {"math": math}
            result = eval(expression, {"__builtins__": None}, allowed_names)
            return str(result)
        except Exception as e:
            return f"Error: {str(e)}"
