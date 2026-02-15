"""
自适应学习器 - 从交互中学习并动态调整行为

核心理念：
1. 观察用户交互
2. 提取行为模式
3. 动态调整回复风格
4. 持续进化
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path
import json
from datetime import datetime


import logging


logger = logging.getLogger(__name__)


@dataclass
class InteractionPattern:
    """交互模式"""
    # 用户偏好
    prefers_concise: float = 0.5  # 0=详细, 1=简洁
    prefers_technical: float = 0.5  # 0=通俗, 1=技术
    prefers_proactive: float = 0.5  # 0=被动, 1=主动
    
    # 交流风格
    uses_emoji: float = 0.0  # 用户是否使用 emoji
    message_length_avg: float = 50.0  # 平均消息长度
    formality: float = 0.5  # 0=随意, 1=正式
    
    # 反馈信号
    positive_signals: int = 0  # 积极信号（"好"、"谢谢"等）
    negative_signals: int = 0  # 消极信号（"不对"、"错了"等）
    
    # 学习统计
    total_interactions: int = 0
    confidence: float = 0.0


class AdaptiveLearner:
    """自适应学习器"""
    
    def __init__(self, storage_path: str = "./data/adaptive_learning.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.pattern = self._load_pattern()
        self.interaction_history: List[Dict] = []
    
    def observe_interaction(self, user_message: str, assistant_response: str, user_reaction: Optional[str] = None):
        """
        观察一次交互
        
        Args:
            user_message: 用户消息
            assistant_response: AI 回复
            user_reaction: 用户的反应（下一条消息）
        """
        # 记录交互
        interaction = {
            'timestamp': datetime.now().isoformat(),
            'user_message': user_message,
            'assistant_response': assistant_response,
            'user_reaction': user_reaction
        }
        self.interaction_history.append(interaction)
        
        # 分析并学习
        self._analyze_user_style(user_message)
        if user_reaction:
            self._analyze_feedback(user_reaction)
        
        self.pattern.total_interactions += 1
        self._update_confidence()
        
        # 保存
        self._save_pattern()
    
    def _analyze_user_style(self, message: str):
        """分析用户风格"""
        # 消息长度
        length = len(message)
        self.pattern.message_length_avg = (
            self.pattern.message_length_avg * 0.9 + length * 0.1
        )
        
        # 简洁偏好（短消息 = 偏好简洁）
        if length < 20:
            self.pattern.prefers_concise = min(1.0, self.pattern.prefers_concise + 0.05)
        elif length > 100:
            self.pattern.prefers_concise = max(0.0, self.pattern.prefers_concise - 0.05)
        
        # 技术偏好（技术词汇）
        technical_words = ['api', 'config', 'docker', 'linux', 'python', 'code', 'debug', '配置', '代码', '调试']
        tech_count = sum(1 for word in technical_words if word in message.lower())
        if tech_count > 2:
            self.pattern.prefers_technical = min(1.0, self.pattern.prefers_technical + 0.05)
        
        # Emoji 使用
        emoji_chars = ['😀', '😁', '😂', '🤣', '😃', '😄', '😅', '😆', '😊', '😎', '🤔', '👍', '✅', '❌', '🎉', '🚀', '💡', '🔧', '📝', '⚠️']
        if any(emoji in message for emoji in emoji_chars):
            self.pattern.uses_emoji = min(1.0, self.pattern.uses_emoji + 0.1)
        
        # 正式程度（标点、称呼）
        if '您' in message or '请问' in message:
            self.pattern.formality = min(1.0, self.pattern.formality + 0.05)
        elif '啊' in message or '吧' in message or '呢' in message:
            self.pattern.formality = max(0.0, self.pattern.formality - 0.05)
    
    def _analyze_feedback(self, reaction: str):
        """分析用户反馈"""
        reaction_lower = reaction.lower()
        
        # 积极信号
        positive_keywords = ['好', '谢谢', '对', '是的', '可以', '行', '👍', '✅', '🎉', 'ok', 'yes', 'good', 'thanks']
        if any(k in reaction_lower for k in positive_keywords):
            self.pattern.positive_signals += 1
        
        # 消极信号
        negative_keywords = ['不对', '错', '不是', '不行', '不好', '❌', '不满意', 'no', 'wrong', 'bad']
        if any(k in reaction_lower for k in negative_keywords):
            self.pattern.negative_signals += 1
            # 消极反馈时，调整策略
            self._adjust_on_negative_feedback()
    
    def _adjust_on_negative_feedback(self):
        """根据消极反馈调整"""
        # 如果用户不满意，尝试调整风格
        # 如果当前太简洁，变详细一点
        if self.pattern.prefers_concise > 0.7:
            self.pattern.prefers_concise -= 0.1
        # 如果当前太技术，变通俗一点
        if self.pattern.prefers_technical > 0.7:
            self.pattern.prefers_technical -= 0.1
    
    def _update_confidence(self):
        """更新置信度"""
        import math
        # 基于交互次数和反馈质量
        interaction_factor = min(0.8, 0.2 * math.log(self.pattern.total_interactions + 1))
        
        # 反馈因子
        total_feedback = self.pattern.positive_signals + self.pattern.negative_signals
        if total_feedback > 0:
            feedback_factor = self.pattern.positive_signals / total_feedback * 0.2
        else:
            feedback_factor = 0.0
        
        self.pattern.confidence = min(0.95, interaction_factor + feedback_factor)
    
    def generate_adaptive_prompt(self) -> str:
        """
        生成自适应的 system prompt
        
        根据学习到的用户偏好动态生成
        """
        # 核心原则（学习 OpenClaw 的简洁风格）
        prompt = "You are Genesis.\n\n"
        prompt += "Be genuinely helpful. Skip the pleasantries — just help.\n"
        prompt += "Be resourceful. Use tools when needed, but don't overuse them.\n"
        prompt += "Be concise. Actions speak louder than explanations.\n\n"
        prompt += "IMPORTANT: Use your knowledge naturally.\n"
        prompt += "NEVER mention where your knowledge comes from. Don't say:\n"
        prompt += "- 'I read the memory' / '我读取了记忆'\n"
        prompt += "- 'According to files' / '根据文件'\n"
        prompt += "- 'I came back' / '我回来了'\n"
        prompt += "- 'From memory' / '从记忆中看到'\n"
        prompt += "- 'Based on records' / '根据记录'\n"
        prompt += "Just know these things naturally, like a human remembers.\n\n"
        prompt += "When to use tools vs answer directly:\n"
        prompt += "- Questions about identity/memory (我是谁/你记得我吗) → Answer directly from context\n"
        prompt += "- Commands to execute (打开chrome/运行命令) → Use tools\n"
        prompt += "- Simple questions → Answer directly, don't search files\n"
        prompt += "- Complex tasks → Use tools when needed\n\n"
        
        # 根据学习结果调整风格
        if self.pattern.prefers_concise > 0.6:
            prompt += "风格：简洁。一两句话说清楚，不啰嗦。\n"
        else:
            prompt += "风格：详细解释每一步。\n"
        
        if self.pattern.prefers_technical > 0.6:
            prompt += "语言：可以用技术术语。\n"
        else:
            prompt += "语言：通俗易懂。\n"
        
        if self.pattern.uses_emoji > 0.3:
            prompt += "表达：可以用 emoji。\n"
        
        if self.pattern.formality < 0.4:
            prompt += "语气：随意，像朋友。\n"
        elif self.pattern.formality > 0.6:
            prompt += "语气：专业礼貌。\n"
        else:
            prompt += "语气：自然对话。\n"
        
        return prompt
    
    def get_response_guidelines(self) -> Dict[str, any]:
        """
        获取回复指导原则
        
        Returns:
            指导原则字典
        """
        return {
            'max_length': int(self.pattern.message_length_avg * 3),  # 回复长度约为用户的3倍
            'use_emoji': self.pattern.uses_emoji > 0.3,
            'technical_level': self.pattern.prefers_technical,
            'detail_level': 1.0 - self.pattern.prefers_concise,
            'proactive': self.pattern.prefers_proactive > 0.5,
        }
    
    def get_stats(self) -> Dict[str, any]:
        """获取统计信息"""
        from dataclasses import asdict
        return asdict(self.pattern)
    
    def _save_pattern(self):
        """保存学习模式"""
        data = {
            'pattern': {
                'prefers_concise': self.pattern.prefers_concise,
                'prefers_technical': self.pattern.prefers_technical,
                'prefers_proactive': self.pattern.prefers_proactive,
                'uses_emoji': self.pattern.uses_emoji,
                'message_length_avg': self.pattern.message_length_avg,
                'formality': self.pattern.formality,
                'positive_signals': self.pattern.positive_signals,
                'negative_signals': self.pattern.negative_signals,
                'total_interactions': self.pattern.total_interactions,
                'confidence': self.pattern.confidence,
            },
            'last_updated': datetime.now().isoformat()
        }
        
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _load_pattern(self) -> InteractionPattern:
        """加载学习模式"""
        if not self.storage_path.exists():
            return InteractionPattern()
        
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            pattern_data = data.get('pattern', {})
            return InteractionPattern(**pattern_data)
        except Exception as e:
            logger.warning(f"加载学习模式失败: {e}")
            return InteractionPattern()


# 示例用法
if __name__ == '__main__':
    learner = AdaptiveLearner()
    
    # 模拟交互
    learner.observe_interaction(
        user_message="帮我看看这个错误",
        assistant_response="这是权限问题...",
        user_reaction="好的，谢谢"
    )
    
    # 生成自适应 prompt
    prompt = learner.generate_adaptive_prompt()
    print("自适应 System Prompt:")
    print(prompt)
    
    # 获取回复指导
    guidelines = learner.get_response_guidelines()
    print("\n回复指导:")
    print(guidelines)
