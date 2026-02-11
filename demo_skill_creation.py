
import sys
import asyncio
import logging
from pathlib import Path

# 添加 nanabot 路径
# 添加路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nanogenesis.agent import NanoGenesis

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("demo_skill")

async def main():
    print("🧬 NanoGenesis 技能自适应生成演示")
    print("=" * 60)

    # 1. 初始化 Agent
    agent = NanoGenesis(enable_optimization=True)
    
    # 2. 模拟: Agent 遇到难题，决定编写一个新工具
    skill_name = "advanced_calculator"
    print(f"🔧 正在生成新技能: {skill_name}...")
    
    python_code = """
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
"""
    
    # 调用 SkillCreatorTool
    creator = agent.tools.get("skill_creator")
    result = await creator.execute(skill_name, python_code)
    print(result)
    print("-" * 60)
    
    # 3. 立即使用新技能
    print("🚀 尝试调用新技能...")
    
    # 验证工具是否已注册
    if "advanced_calculator" in agent.tools:
        print("✓ 工具已注册到 ToolRegistry")
        
        # 执行计算
        expression = "math.pow(2, 10)" # 2^10 = 1024
        print(f"执行: {expression}")
        
        calc_result = await agent.tools.execute("advanced_calculator", {"expression": expression})
        print(f"结果: {calc_result}")
        
        if str(float(1024)) in calc_result or "1024" in calc_result:
            print("\n✅ 验证成功: Agent 成功扩展了自己的能力！")
        else:
            print("\n❌ 验证失败: 结果不正确")
    else:
        print("\n❌ 验证失败: 工具未注册")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
