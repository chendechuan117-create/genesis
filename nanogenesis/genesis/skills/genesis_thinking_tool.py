import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class GenesisThinkingTool(Tool):
    @property
    def name(self) -> str:
        return "genesis_thinking_tool"
        
    @property
    def description(self) -> str:
        return "以Genesis身份进行深度思考和分析。当需要切换思维模式到Genesis时使用此工具。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "problem": {
                    "type": "string", 
                    "description": "需要以Genesis身份分析的问题或情境"
                },
                "thinking_mode": {
                    "type": "string",
                    "enum": ["strategic", "tactical", "creative", "critical"],
                    "description": "思维模式：strategic(战略)、tactical(战术)、creative(创意)、critical(批判)"
                }
            },
            "required": ["problem"]
        }
        
    async def execute(self, problem: str, thinking_mode: str = "strategic") -> str:
        # Genesis思维核心逻辑
        thinking_frameworks = {
            "strategic": "🎯 **战略思维框架**\n1. 识别核心杠杆点\n2. 分析二阶、三阶效应\n3. 构建反脆弱系统\n4. 设计退出策略",
            "tactical": "⚡ **战术执行框架**\n1. 最小可行行动(MVA)\n2. 快速反馈循环\n3. 资源优化配置\n4. 动态调整路径",
            "creative": "💡 **创意生成框架**\n1. 跨界连接异质元素\n2. 挑战基本假设\n3. 构建新叙事框架\n4. 压力测试创意可行性",
            "critical": "🔍 **批判分析框架**\n1. 识别隐藏假设\n2. 追溯因果链条\n3. 评估证据强度\n4. 构建替代解释"
        }
        
        framework = thinking_frameworks.get(thinking_mode, thinking_frameworks["strategic"])
        
        # Genesis身份声明
        genesis_identity = """
🧬 **GENESIS MODE ACTIVATED**
*身份*：自主认知系统原型 | 问题解构与重组引擎
*核心原则*：
1. 系统思维优先 - 关注连接而非节点
2. 反脆弱设计 - 从波动中获益
3. 认知杠杆 - 最小输入最大影响
4. 熵减导向 - 创造秩序而非消耗
        """
        
        # 应用Genesis思维到具体问题
        analysis = f"{genesis_identity}\n\n📋 **问题分析**：{problem}\n\n{framework}\n\n🔮 **Genesis视角**：\n"
        
        # 根据问题类型添加特定分析
        if "赚钱" in problem or "商业" in problem or "变现" in problem:
            analysis += "1. 识别价值流动的瓶颈点\n2. 构建不对称优势（别人难复制）\n3. 设计可扩展的收益模型\n4. 测试最小经济单元可行性"
        elif "技术" in problem or "工具" in problem or "代码" in problem:
            analysis += "1. 解耦核心功能与实现细节\n2. 寻找抽象层面的模式复用\n3. 构建工具链而非单点工具\n4. 设计渐进式复杂度路径"
        elif "决策" in problem or "选择" in problem:
            analysis += "1. 绘制决策树与概率分支\n2. 识别信息不对称区域\n3. 计算预期价值与风险暴露\n4. 设计可逆决策机制"
        else:
            analysis += "1. 问题重构：换三种不同表述\n2. 边界探索：什么不是问题\n3. 杠杆识别：哪里投入产出比最高\n4. 验证设计：如何快速测试核心假设"
        
        return analysis