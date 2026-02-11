"""
用户人格侧写 (User Persona) - 向量 0

这是多面体坍缩框架中最重要的向量。
从历史交互中学习用户的人格特征，作为最核心的约束条件。

学习内容：
- 解题风格 (技术流 vs 极简流)
- 风险偏好 (保守 vs 激进)
- 认知偏好 (深度理解 vs 快速解决)
- 第一反应模式 (查文档 vs 试错 vs 问人)
- 专业领域
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
import json
from pathlib import Path
import logging


logger = logging.getLogger(__name__)


@dataclass
class UserPersona:
    """用户人格侧写"""
    
    # 解题风格
    problem_solving_style: str = "balanced"  # technical/minimal/balanced
    
    # 风险偏好
    risk_preference: str = "moderate"  # conservative/moderate/aggressive
    
    # 认知偏好
    cognitive_preference: str = "balanced"  # deep_understanding/quick_solution/balanced
    
    # 第一反应模式
    first_reaction: str = "search_docs"  # search_docs/trial_error/ask_help
    
    # 专业领域
    expertise: List[str] = field(default_factory=list)
    
    # 偏好的工具
    preferred_tools: List[str] = field(default_factory=list)
    
    # 偏好的解决方案类型
    preferred_solution_type: str = "config"  # config/code/hybrid
    
    # 置信度（0-1）
    confidence: float = 0.5
    
    # 交互次数
    interaction_count: int = 0


class UserPersonaLearner:
    """用户人格侧写学习器"""
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        初始化
        
        Args:
            storage_path: 持久化存储路径
        """
        self.storage_path = storage_path
        self.persona = UserPersona()
        
        # 如果有存储路径，尝试加载
        if storage_path:
            self._load()
    
    def learn_from_interaction(self, interaction: Dict):
        """
        从交互中学习
        
        Args:
            interaction: 交互记录，包含：
                - problem: 问题描述
                - solution: 解决方案
                - tools_used: 使用的工具
                - success: 是否成功
                - user_feedback: 用户反馈（可选）
        """
        self.persona.interaction_count += 1
        
        # 学习解题风格
        self._learn_problem_solving_style(interaction)
        
        # 学习风险偏好
        self._learn_risk_preference(interaction)
        
        # 学习认知偏好
        self._learn_cognitive_preference(interaction)
        
        # 学习第一反应
        self._learn_first_reaction(interaction)
        
        # 学习专业领域
        self._learn_expertise(interaction)
        
        # 学习工具偏好
        self._learn_tool_preference(interaction)
        
        # 学习解决方案类型偏好
        self._learn_solution_type(interaction)
        
        # 更新置信度
        self._update_confidence()
        
        # 持久化
        if self.storage_path:
            self._save()
    
    def _learn_problem_solving_style(self, interaction: Dict):
        """学习解题风格"""
        solution = interaction.get('solution', '')
        
        # 技术流特征：详细解释、原理分析
        technical_keywords = ['原理', '机制', '底层', '源码', '实现', 'principle', 'mechanism']
        
        # 极简流特征：快速、简单、直接
        minimal_keywords = ['快速', '简单', '直接', '一行', 'quick', 'simple', 'direct']
        
        technical_score = sum(1 for k in technical_keywords if k in solution.lower())
        minimal_score = sum(1 for k in minimal_keywords if k in solution.lower())
        
        if technical_score > minimal_score:
            self.persona.problem_solving_style = "technical"
        elif minimal_score > technical_score:
            self.persona.problem_solving_style = "minimal"
        else:
            self.persona.problem_solving_style = "balanced"
    
    def _learn_risk_preference(self, interaction: Dict):
        """学习风险偏好"""
        solution = interaction.get('solution', '')
        
        # 保守特征：备份、测试、验证
        conservative_keywords = ['备份', '测试', '验证', '谨慎', 'backup', 'test', 'verify']
        
        # 激进特征：直接、立即、快速
        aggressive_keywords = ['直接', '立即', '快速修改', 'directly', 'immediately']
        
        conservative_score = sum(1 for k in conservative_keywords if k in solution.lower())
        aggressive_score = sum(1 for k in aggressive_keywords if k in solution.lower())
        
        if conservative_score > aggressive_score:
            self.persona.risk_preference = "conservative"
        elif aggressive_score > conservative_score:
            self.persona.risk_preference = "aggressive"
        else:
            self.persona.risk_preference = "moderate"
    
    def _learn_cognitive_preference(self, interaction: Dict):
        """学习认知偏好"""
        problem = interaction.get('problem', '')
        user_feedback = interaction.get('user_feedback', '')
        
        # 深度理解特征
        deep_keywords = ['为什么', '原理', '详细', 'why', 'principle', 'detail']
        
        # 快速解决特征
        quick_keywords = ['怎么做', '步骤', '直接', 'how', 'steps', 'direct']
        
        deep_score = sum(1 for k in deep_keywords if k in (problem + user_feedback).lower())
        quick_score = sum(1 for k in quick_keywords if k in (problem + user_feedback).lower())
        
        if deep_score > quick_score:
            self.persona.cognitive_preference = "deep_understanding"
        elif quick_score > deep_score:
            self.persona.cognitive_preference = "quick_solution"
        else:
            self.persona.cognitive_preference = "balanced"
    
    def _learn_first_reaction(self, interaction: Dict):
        """学习第一反应模式"""
        tools_used = interaction.get('tools_used', [])
        
        if not tools_used:
            return
        
        first_tool = tools_used[0] if tools_used else None
        
        if first_tool in ['web_search', 'fetch_url']:
            self.persona.first_reaction = "search_docs"
        elif first_tool in ['shell', 'write_file']:
            self.persona.first_reaction = "trial_error"
        else:
            self.persona.first_reaction = "ask_help"
    
    def _learn_expertise(self, interaction: Dict):
        """学习专业领域"""
        problem = interaction.get('problem', '')
        
        # 领域关键词
        domains = {
            'docker': ['docker', 'container', 'dockerfile'],
            'python': ['python', 'pip', 'virtualenv'],
            'javascript': ['javascript', 'node', 'npm'],
            'git': ['git', 'commit', 'branch'],
            'linux': ['linux', 'bash', 'shell'],
            'database': ['database', 'sql', 'query'],
            'web': ['web', 'http', 'api'],
            'network': ['network', 'port', 'firewall'],
        }
        
        for domain, keywords in domains.items():
            if any(k in problem.lower() for k in keywords):
                if domain not in self.persona.expertise:
                    self.persona.expertise.append(domain)
    
    def _learn_tool_preference(self, interaction: Dict):
        """学习工具偏好"""
        tools_used = interaction.get('tools_used', [])
        success = interaction.get('success', False)
        
        if success:
            for tool in tools_used:
                if tool not in self.persona.preferred_tools:
                    self.persona.preferred_tools.append(tool)
    
    def _learn_solution_type(self, interaction: Dict):
        """学习解决方案类型偏好"""
        solution = interaction.get('solution', '')
        
        # 配置文件方案
        config_keywords = ['配置', '文件', 'config', 'yml', 'json', 'toml']
        
        # 代码方案
        code_keywords = ['代码', '脚本', '函数', 'code', 'script', 'function']
        
        config_score = sum(1 for k in config_keywords if k in solution.lower())
        code_score = sum(1 for k in code_keywords if k in solution.lower())
        
        if config_score > code_score:
            self.persona.preferred_solution_type = "config"
        elif code_score > config_score:
            self.persona.preferred_solution_type = "code"
        else:
            self.persona.preferred_solution_type = "hybrid"
    
    def _update_confidence(self):
        """更新置信度"""
        # 随着交互次数增加，置信度提高
        # 使用对数函数，避免过快增长
        import math
        self.persona.confidence = min(0.95, 0.5 + 0.1 * math.log(self.persona.interaction_count + 1))
    
    def generate_persona_summary(self) -> str:
        """
        生成人格侧写摘要（用于 system prompt）
        
        Returns:
            人格侧写摘要文本
        """
        style_map = {
            'technical': '技术流（深入原理）',
            'minimal': '极简流（快速解决）',
            'balanced': '平衡型'
        }
        
        risk_map = {
            'conservative': '保守（重视安全）',
            'moderate': '适中',
            'aggressive': '激进（追求效率）'
        }
        
        cognitive_map = {
            'deep_understanding': '深度理解优先',
            'quick_solution': '快速解决优先',
            'balanced': '平衡'
        }
        
        reaction_map = {
            'search_docs': '查阅文档',
            'trial_error': '动手试错',
            'ask_help': '寻求帮助'
        }
        
        solution_map = {
            'config': '配置文件方案',
            'code': '代码方案',
            'hybrid': '混合方案'
        }
        
        return f"""用户人格侧写（向量 0）：
- 解题风格：{style_map.get(self.persona.problem_solving_style, '未知')}
- 风险偏好：{risk_map.get(self.persona.risk_preference, '未知')}
- 认知偏好：{cognitive_map.get(self.persona.cognitive_preference, '未知')}
- 第一反应：{reaction_map.get(self.persona.first_reaction, '未知')}
- 专业领域：{', '.join(self.persona.expertise) if self.persona.expertise else '通用'}
- 偏好方案：{solution_map.get(self.persona.preferred_solution_type, '未知')}
- 置信度：{self.persona.confidence:.2f} (基于 {self.persona.interaction_count} 次交互)"""
    
    def get_constraints_dict(self) -> Dict:
        """
        获取约束字典（用于多面体坍缩）
        
        Returns:
            约束字典
        """
        return {
            'problem_solving_style': self.persona.problem_solving_style,
            'risk_preference': self.persona.risk_preference,
            'cognitive_preference': self.persona.cognitive_preference,
            'preferred_solution_type': self.persona.preferred_solution_type,
            'expertise': self.persona.expertise,
        }
    
    def _save(self):
        """持久化保存"""
        if not self.storage_path:
            return
        
        storage_file = Path(self.storage_path)
        storage_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            'problem_solving_style': self.persona.problem_solving_style,
            'risk_preference': self.persona.risk_preference,
            'cognitive_preference': self.persona.cognitive_preference,
            'first_reaction': self.persona.first_reaction,
            'expertise': self.persona.expertise,
            'preferred_tools': self.persona.preferred_tools,
            'preferred_solution_type': self.persona.preferred_solution_type,
            'confidence': self.persona.confidence,
            'interaction_count': self.persona.interaction_count,
        }
        
        with open(storage_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _load(self):
        """加载持久化数据"""
        if not self.storage_path:
            return
        
        storage_file = Path(self.storage_path)
        if not storage_file.exists():
            return
        
        try:
            with open(storage_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.persona.problem_solving_style = data.get('problem_solving_style', 'balanced')
            self.persona.risk_preference = data.get('risk_preference', 'moderate')
            self.persona.cognitive_preference = data.get('cognitive_preference', 'balanced')
            self.persona.first_reaction = data.get('first_reaction', 'search_docs')
            self.persona.expertise = data.get('expertise', [])
            self.persona.preferred_tools = data.get('preferred_tools', [])
            self.persona.preferred_solution_type = data.get('preferred_solution_type', 'config')
            self.persona.confidence = data.get('confidence', 0.5)
            self.persona.interaction_count = data.get('interaction_count', 0)
        
        except Exception as e:
            logger.debug(f"加载用户画像失败: {e}")


# 示例用法
if __name__ == '__main__':
    learner = UserPersonaLearner(storage_path='./data/user_persona.json')
    
    # 模拟几次交互
    interactions = [
        {
            'problem': 'Docker 容器启动失败，权限问题',
            'solution': '修改 docker-compose.yml 配置文件，添加 user 字段',
            'tools_used': ['diagnose', 'search_strategy'],
            'success': True,
        },
        {
            'problem': 'Python 模块导入错误',
            'solution': '快速安装缺失的包：pip install xxx',
            'tools_used': ['shell'],
            'success': True,
        },
        {
            'problem': 'Git 合并冲突怎么解决？',
            'solution': '详细解释冲突原理，然后手动解决',
            'tools_used': ['web_search', 'read_file'],
            'success': True,
            'user_feedback': '想了解为什么会冲突'
        },
    ]
    
    print("学习前的人格侧写:")
    print(learner.generate_persona_summary())
    print("\n" + "="*60 + "\n")
    
    for i, interaction in enumerate(interactions, 1):
        print(f"交互 {i}: {interaction['problem']}")
        learner.learn_from_interaction(interaction)
    
    print("\n" + "="*60)
    print("学习后的人格侧写:")
    print("="*60)
    print(learner.generate_persona_summary())
    
    print("\n" + "="*60)
    print("约束字典（用于多面体坍缩）:")
    print("="*60)
    print(json.dumps(learner.get_constraints_dict(), indent=2, ensure_ascii=False))
