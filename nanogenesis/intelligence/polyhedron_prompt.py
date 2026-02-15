"""
多面体坍缩 System Prompt 构建器

负责构建包含多面体框架的 system prompt，并支持动态启用。
"""

from typing import Dict, Optional
from .protocol_encoder import ProtocolEncoder
from .user_persona import UserPersonaLearner


class PolyhedronPromptBuilder:
    """多面体提示词构建器"""
    
    def __init__(self, encoder: Optional[ProtocolEncoder] = None):
        """
        初始化
        
        Args:
            encoder: 协议编码器实例
        """
        self.encoder = encoder or ProtocolEncoder()
        self.polyhedron_template = self._load_polyhedron_template()
    
    def _load_polyhedron_template(self) -> str:
        """加载多面体框架模板"""
        return """🧬 思维框架：多面体坍缩 (Polyhedron Collapse Protocol)

## 核心定义
将用户问题视为三维空间中的**引力奇点 (Singularity X)**。
在解空间中通过**动态向量生成**和**约束坍缩**，筛选唯一最优解。

## 阶段一：多维发散 (Divergence Phase)
生成 n 个正交向量（1 < n ≤ 5），每个代表截然不同的解决方案维度。

**向量 0（最高优先级）**：用户人格侧写
- 这是最重要的约束条件
- 所有方案必须符合用户的风格和偏好

**向量 1-N**：解决方案向量
- 每个向量必须正交（截然不同）
- 禁止生成平行的（重复的）思路
- 示例维度：技术流、极简流、成本流、降维打击流

## 阶段二：虚拟沙盘推演 (Simulation & Pruning)
应用**损失函数**进行剪枝：

$$L = C_{cost} + C_{cognitive} + (1 - S_{match})$$

其中：
- $C_{cost}$ (金钱成本)：方案是否付费？(付费方案权重极低)
- $C_{cognitive}$ (认知成本)：执行该方案的繁琐程度
- $S_{match}$ (用户画像匹配度)：与用户偏好的匹配度

**剪枝规则**：
1. 硬剪枝：如果 L 值过高，直接剔除
2. 效用判停：当第 n+1 个向量的边际增益 < 认知成本时，停止生成

## 阶段三：坍缩与输出 (Collapse & Output)
只输出经过剪枝后存活的**最优向量**（或双子解）。

**输出格式**：
```
【最优解】：{一句话核心方案}

【代价标签】：
💰 金钱：{具体金额/$0}
⏱️ 时间：{如：5分钟/30分钟}
🧠 认知：{minimal/low/medium/high}

【坍缩逻辑】：
{简述为什么其他 n-1 个向量被淘汰}
例如：
- 方案A虽然更强，但因付费被剪枝
- 方案B太繁琐（认知成本高）被剪枝
- 方案C与用户画像不匹配被剪枝

【执行路径】：
1. [具体步骤1]
2. [具体步骤2]
3. [具体步骤3]
```

**关键原则**：
- 不展示思考过程，只展示最优解
- 必须显性化"隐形代价"
- 优先匹配用户人格侧写（向量0）
"""
    
    def build_system_prompt(
        self,
        user_persona: str,
        constraints: Dict,
        include_polyhedron: bool = True
    ) -> str:
        """
        构建 system prompt
        
        Args:
            user_persona: 用户人格侧写摘要
            constraints: 约束条件字典
            include_polyhedron: 是否包含多面体框架
        
        Returns:
            完整的 system prompt
        """
        if include_polyhedron:
            return self._build_polyhedron_prompt(user_persona, constraints)
        else:
            return self._build_basic_prompt(user_persona, constraints)
    
    def _build_polyhedron_prompt(self, user_persona: str, constraints: Dict) -> str:
        """构建包含多面体框架的 prompt"""
        return f"""你是 NanoGenesis AI 助手。

{self.polyhedron_template}

---

{user_persona}

---

## 用户约束
- 预算：{constraints.get('budget', 0)}
- 环境：{constraints.get('environment', 'Linux')}
- 偏好：{constraints.get('preferences', '本地化、开源')}

---

{self.encoder.get_decoder_prompt()}
"""
    
    def _build_basic_prompt(self, user_persona: str, constraints: Dict) -> str:
        """构建基础 prompt（不含多面体框架）"""
        return f"""你是 NanoGenesis AI 助手。

{user_persona}

## 用户约束
- 预算：{constraints.get('budget', 0)}
- 环境：{constraints.get('environment', 'Linux')}
- 偏好：{constraints.get('preferences', '本地化、开源')}

{self.encoder.get_decoder_prompt()}
"""
    
    def should_use_polyhedron(self, intent_type: str, confidence: float, complexity: str = "medium") -> bool:
        """
        判断是否应该使用多面体框架
        
        Args:
            intent_type: 意图类型 (problem/task/query)
            confidence: 置信度 (0-1)
            complexity: 复杂度 (low/medium/high)
        
        Returns:
            是否使用多面体框架
        """
        # 复杂问题才用多面体
        if complexity == "high":
            return True
        
        # 问题类型且置信度低，用多面体
        if intent_type == "problem" and confidence < 0.8:
            return True
        
        # 需要多方案选择的场景
        if intent_type == "problem" and complexity == "medium":
            return True
        
        # 简单查询/任务不用多面体
        return False


class ComplexityEstimator:
    """复杂度估算器"""
    
    @staticmethod
    def estimate(user_input: str, diagnosis: Optional[Dict] = None) -> str:
        """
        估算问题复杂度
        
        Args:
            user_input: 用户输入
            diagnosis: 诊断结果（可选）
        
        Returns:
            复杂度等级: low/medium/high
        """
        # 简单规则估算
        input_length = len(user_input)
        
        # 长度判断
        if input_length < 50:
            base_complexity = "low"
        elif input_length < 200:
            base_complexity = "medium"
        else:
            base_complexity = "high"
        
        # 如果有诊断结果，根据置信度调整
        if diagnosis:
            confidence = diagnosis.get('confidence', 0.5)
            if confidence < 0.6:
                # 置信度低，提升复杂度
                if base_complexity == "low":
                    base_complexity = "medium"
                elif base_complexity == "medium":
                    base_complexity = "high"
        
        # 关键词判断
        complex_keywords = [
            '多个', '复杂', '不确定', '尝试了', '失败',
            'multiple', 'complex', 'uncertain', 'tried', 'failed'
        ]
        
        if any(k in user_input.lower() for k in complex_keywords):
            if base_complexity == "low":
                base_complexity = "medium"
        
        return base_complexity


# 示例用法
if __name__ == '__main__':
    from user_persona import UserPersonaLearner
    
    # 创建用户画像学习器
    learner = UserPersonaLearner()
    
    # 模拟学习
    learner.learn_from_interaction({
        'problem': 'Docker 容器启动失败',
        'solution': '修改配置文件',
        'tools_used': ['diagnose'],
        'success': True,
    })
    
    # 创建 prompt 构建器
    builder = PolyhedronPromptBuilder()
    
    # 获取用户画像
    user_persona = learner.generate_persona_summary()
    
    # 约束条件
    constraints = {
        'budget': 0,
        'environment': 'Linux',
        'preferences': '本地化、开源、配置文件方案'
    }
    
    # 测试复杂度估算
    estimator = ComplexityEstimator()
    
    test_cases = [
        ("读取文件 /tmp/test.txt", None),
        ("Docker 容器启动失败，permission denied", None),
        ("我尝试了多种方法都失败了，不确定是什么问题", None),
    ]
    
    print("="*60)
    print("复杂度估算测试:")
    print("="*60)
    
    for user_input, diagnosis in test_cases:
        complexity = estimator.estimate(user_input, diagnosis)
        use_polyhedron = builder.should_use_polyhedron("problem", 0.7, complexity)
        
        print(f"\n输入: {user_input}")
        print(f"复杂度: {complexity}")
        print(f"使用多面体: {'是' if use_polyhedron else '否'}")
    
    # 构建 system prompt
    print("\n" + "="*60)
    print("System Prompt 示例（包含多面体）:")
    print("="*60)
    
    system_prompt = builder.build_system_prompt(
        user_persona,
        constraints,
        include_polyhedron=True
    )
    
    print(system_prompt[:500] + "...\n[已截断]")
    
    print("\n" + "="*60)
    print("System Prompt 示例（不含多面体）:")
    print("="*60)
    
    basic_prompt = builder.build_system_prompt(
        user_persona,
        constraints,
        include_polyhedron=False
    )
    
    print(basic_prompt[:300] + "...\n[已截断]")
