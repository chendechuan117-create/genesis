"""
上下文感知管道 - NanoGenesis Context Pipeline
实现模块化、插件化的上下文构建，替代硬编码的字符串拼接。
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime
import os
import platform
from pathlib import Path
from dataclasses import dataclass
from .base import Message, MessageRole

@dataclass
class ContextContext:
    """传递给插件的上下文环境"""
    user_input: str
    raw_memory: Optional[List[Dict]] = None
    agent_state: Optional[Dict] = None
    history_blocks: Optional[List[Any]] = None

class ContextPlugin(ABC):
    """上下文插件基类"""
    name: str = "base_plugin"
    priority: int = 10  # 越小越靠前
    
    @abstractmethod
    def inject(self, ctx: ContextContext) -> Optional[str]:
        """返回要注入的上下文片段，None 表示不注入"""
        pass

class IdentityPlugin(ContextPlugin):
    """身份定义插件 (最核心)"""
    name = "identity"
    priority = 0
    
    def __init__(self, system_prompt: str):
        self.system_prompt = system_prompt
        
    def inject(self, ctx: ContextContext) -> str:
        return self.system_prompt

class TimeAwarenessPlugin(ContextPlugin):
    """时间感知插件 (动态 - 放在最后以利用缓存)"""
    name = "time_awareness"
    priority = 100  # 极低优先级，放在 Prompt 末尾
    
    def inject(self, ctx: ContextContext) -> str:
        now = datetime.now()
        return f"\n[System Time: {now.strftime('%Y-%m-%d %H:%M:%S')} {now.astimezone().tzname() or ''}]"

class EnvironmentPlugin(ContextPlugin):
    """环境感知插件 (静态部分 - System Profile)"""
    name = "environment_static"
    priority = 2
    
    def inject(self, ctx: ContextContext) -> str:
        # 仅加载静态系统画像
        profile_content = ""
        possible_paths = [
            Path(os.getcwd()) / "system_profile.md",
            Path(__file__).parent.parent / "system_profile.md"
        ]
        
        for path in possible_paths:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        profile_content = f"\n\n[System Hardware & Scope]\n{f.read().strip()}"
                    break
                except Exception:
                    pass
        
        # 如果没有 Profile，返回基础静态 OS 信息
        if not profile_content:
             return f"\n[Host OS: {platform.system()} {platform.release()}]"
             
        return profile_content

class SessionStatePlugin(ContextPlugin):
    """会话状态插件 (动态 - CWD/User)"""
    name = "session_state"
    priority = 99 # 放在时间之前，历史之后
    
    def inject(self, ctx: ContextContext) -> str:
        return f"\n[Session State]\nCWD: {os.getcwd()}\nUser: {os.getlogin()}"

class MemoryPlugin(ContextPlugin):
    """记忆注入插件"""
    name = "memory"
    priority = 5
    
    def inject(self, ctx: ContextContext) -> Optional[str]:
        if not ctx.raw_memory:
            return None
            
        content = "\n\n[Relevant Memories]\n"
        for i, m in enumerate(ctx.raw_memory, 1):
            content += f"{i}. {m.get('content', '')}\n"
        return content

class HistorySummariesPlugin(ContextPlugin):
    """历史摘要插件 (Compressed Blocks)"""
    name = "history_summaries"
    priority = 20  # 放在身份之后，记忆之后
    
    def inject(self, ctx: ContextContext) -> Optional[str]:
        if not ctx.history_blocks:
            return None
            
        summary_content = "【历史对话摘要】\n"
        for block in ctx.history_blocks:
            summary_content += f"--- Block {block.id} ---\n"
            summary_content += f"摘要: {block.summary}\n"
            if block.diff:
                summary_content += f"变更: {block.diff}\n"
            if block.anchors:
                import json
                summary_content += f"锚点: {json.dumps(block.anchors, ensure_ascii=False)}\n"
        
        return summary_content

class ContextPipeline:
    """上下文管道管理器"""
    
    def __init__(self, base_system_prompt: str):
        self.plugins: List[ContextPlugin] = []
        # 默认注册核心插件
        self.register(IdentityPlugin(base_system_prompt))
        self.register(TimeAwarenessPlugin())
        # EnvironmentPlugin moved below
        self.register(EnvironmentPlugin())
        self.register(MemoryPlugin())
        self.register(HistorySummariesPlugin())
        
        # 延迟导入以避免循环依赖
        try:
            from .representation import ProtocolCompressionPlugin
            self.register(ProtocolCompressionPlugin())
        except ImportError:
            pass
        
    def register(self, plugin: ContextPlugin):
        self.plugins.append(plugin)
        self.plugins.sort(key=lambda x: x.priority)
        
    def build_system_context(self, user_input: str, min_priority: int = -999, max_priority: int = 9999, **kwargs) -> str:
        """构建完整的 System Context"""
        ctx = ContextContext(user_input=user_input, **kwargs)
        
        parts = []
        for plugin in self.plugins:
            # Filter by priority
            if not (min_priority <= plugin.priority <= max_priority):
                continue

            try:
                content = plugin.inject(ctx)
                if content:
                    parts.append(content)
            except Exception as e:
                # 插件故障不应导致崩盘
                print(f"Plugin {plugin.name} failed: {e}")
                
        return "\n".join(parts)
