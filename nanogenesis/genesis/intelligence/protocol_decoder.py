"""
协议解码器 (Protocol Decoder)
===========================
将大模型的原始文本输出 (Raw Text Protocol) 解析为结构化意图 (Structured Intents)。
这是为了保护核心引擎（如 agent.py）不受硬编码字符串解析的污染，彻底斩断“硬编码癌”。
"""

import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

class ProtocolDecoder:
    """
    负责将带有 [TAG] 的混合文本解构为机器可识别的强类型行为指令。
    """
    
    # 核心控制标记
    TAG_CLARIFICATION = "[CLARIFICATION_REQUIRED]"
    TAG_FORGE = "[CAPABILITY_FORGE]"
    TAG_INTERRUPT = "[STRATEGIC_INTERRUPT_SIGNAL]"
    
    @classmethod
    def decode_strategy(cls, raw_text: str) -> Tuple[str, str, str]:
        """
        解析策略蓝图阶段 (Strategy Phase) 的输出
        
        Returns:
            Tuple[intent_type, intent_content, original_text]:
            - intent_type: 'clarification', 'forge', 'normal'
            - intent_content: 提取出的核心指令/需求
            - original_text: 原始文本
        """
        if cls.TAG_CLARIFICATION in raw_text:
            return "clarification", raw_text, raw_text
            
        if cls.TAG_FORGE in raw_text:
            parts = raw_text.split(cls.TAG_FORGE)
            if len(parts) > 1:
                forge_intent = parts[1].strip()
                return "forge", forge_intent, raw_text
                
        return "normal", raw_text, raw_text

    @classmethod
    def decode_execution(cls, raw_text: str) -> Tuple[str, str, str]:
        """
        解析执行阶段 (Execution Phase) 或 Loop 返回的输出
        
        Returns:
            Tuple[intent_type, intent_content, original_text]:
            - intent_type: 'interrupt', 'normal'
            - intent_content: 清洗后的内容
            - original_text: 原始文本
        """
        if cls.TAG_INTERRUPT in raw_text:
            clean_msg = raw_text.replace(cls.TAG_INTERRUPT, "").strip()
            return "interrupt", clean_msg, raw_text
            
        return "normal", raw_text, raw_text
