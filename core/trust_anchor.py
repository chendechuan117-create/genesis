"""
锚点信任模型 (Anchored Trust Model)

建立信息来源的信任层级，Genesis 知道该信谁。
"""

from enum import Enum
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class TrustLevel(Enum):
    """信任层级"""
    L0_LOCAL = 0      # 本地文件系统/进程状态 (绝对信任)
    L1_USER = 1       # 用户显式声明 (高信任)
    L2_INTERNAL = 2   # LLM 内部知识 (可信,但可能过时)
    L3_EXTERNAL = 3   # 外部网络搜索 (待验证)


class TrustAnchorManager:
    """信任锚点管理器"""
    
    # 工具 -> 信任层级映射
    TOOL_TRUST_MAP = {
        # L0: Local System
        "shell": TrustLevel.L0_LOCAL,
        "read_file": TrustLevel.L0_LOCAL,
        "list_directory": TrustLevel.L0_LOCAL,
        "write_file": TrustLevel.L0_LOCAL,
        "append_file": TrustLevel.L0_LOCAL,
        
        # L1: User Intent (via tools that record user input)
        "memory_store": TrustLevel.L1_USER,
        
        # L2: Internal Knowledge (LLM reasoning - no tool)
        # This is the default for non-tool responses
        
        # L3: External
        "web_search": TrustLevel.L3_EXTERNAL,
        "browser": TrustLevel.L3_EXTERNAL,
    }
    
    def __init__(self):
        pass
    
    def get_trust_level(self, source: str) -> TrustLevel:
        """获取信息来源的信任层级"""
        # Normalize tool name
        source_lower = source.lower().replace("tool", "").strip()
        
        return self.TOOL_TRUST_MAP.get(source_lower, TrustLevel.L2_INTERNAL)
    
    def get_disclaimer(self, trust_level: TrustLevel) -> Optional[str]:
        """获取信任层级对应的免责声明"""
        if trust_level == TrustLevel.L3_EXTERNAL:
            return "⚠️ 此信息来自外部网络，建议交叉验证。"
        elif trust_level == TrustLevel.L2_INTERNAL:
            return None  # No disclaimer for internal knowledge by default
        return None
    
    def should_verify(self, trust_level: TrustLevel) -> bool:
        """是否需要交叉验证"""
        return trust_level == TrustLevel.L3_EXTERNAL
    
    def tag_response(self, response: str, source: str) -> str:
        """为响应添加信任标签"""
        level = self.get_trust_level(source)
        disclaimer = self.get_disclaimer(level)
        
        if disclaimer:
            return f"{response}\n\n{disclaimer}"
        return response
