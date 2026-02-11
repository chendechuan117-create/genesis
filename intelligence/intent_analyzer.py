"""
意图分析模块 (Intent Analyzer)
独立于 Agent 主体，负责快速识别用户输入的意图类型。
"""

import re
import asyncio
from typing import Set, Optional
import logging

logger = logging.getLogger(__name__)

class IntentAnalyzer:
    """
    负责分析用户输入的意图，决定处理路径（Simple vs Complex/Polyhedron）。
    """
    
    def __init__(self, provider=None):
        self.provider = provider  # 本地 LLM Provider
        
        # 简单问候语 (无需动脑)
        self.greetings: Set[str] = {
            'hi', 'hello', 'hey', '你好', '您好', '在吗', 'test', 'ping', 
            '早', '早安', '晚安', 'good morning', 'good night'
        }
        
        # 简单确认/拒绝
        self.acknowledgments: Set[str] = {
            'ok', 'thanks', 'thank you', '好的', '谢谢', '收到', 'yes', 'no', 
            '对', '不对', '行', '不行'
        }
        
        # 复杂任务触发词 (必须动脑)
        self.complex_triggers: Set[str] = {
            'plan', 'analyze', 'debug', 'fix', 'create', 'write', 'how to', 
            '计划', '分析', '调试', '修复', '创建', '编写', '如何', '为什么', 
            '总结', '解释', '优化', '设计'
        }

    async def classify(self, user_input: str) -> str:
        """
        分类用户意图
        
        Returns:
            'simple': 简单意图，跳过元认知
            'complex': 复杂意图，强制元认知
            'general': 默认，由 Agent 自行决定
        """
        # 1. 优先尝试本地 LLM (如果可用)
        if self.provider and self.provider.available:
            try:
                return await self._classify_with_llm(user_input)
            except Exception as e:
                logger.warning(f"本地意图识别失败，降级到规则: {e}")
        
        # 2. 降级到规则匹配
        return self._classify_with_rules(user_input)

    def _classify_with_rules(self, user_input: str) -> str:
        text = user_input.lower().strip()
        
        # 1. 优先检查是否是简单交互
        if (any(g in text for g in self.greetings) and len(text) < 30) or \
           (len(text) < 10 and not any(c in text for c in './\\')):
            if not any(t in text for t in self.complex_triggers):
                return "simple"
            
        # 2. 检查简单回复
        if text in self.acknowledgments:
            return "simple"
            
        # 3. 检查复杂任务特征
        if any(trigger in text for trigger in self.complex_triggers):
            return "complex"
            
        # 4. 默认情况
        return "general"

    async def _classify_with_llm(self, user_input: str) -> str:
        """使用本地 LLM 进行分类"""
        prompt = f"""
        任务：分类用户意图。
        
        类别定义：
        - simple: 闲聊、问候、简单问答、不需要复杂思考或工具。
        - complex: 需要规划、多步推理、编写代码、分析问题。
        
        用户输入："{user_input}"
        
        只回答类别名称 (simple 或 complex)，不要其他废话。
        """
        
        messages = [{"role": "user", "content": prompt}]
        response = await self.provider.chat(messages)
        result = response.content.lower().strip()
        
        if "simple" in result:
            return "simple"
        elif "complex" in result:
            return "complex"
        else:
            return "general"
