"""
上下文构建器 - 优化 Token 使用
"""

from typing import List, Dict, Any, Optional
import logging

from .base import Message, MessageRole, ContextBuilder as BaseContextBuilder
from .compression import CompressionEngine
from .context_pipeline import ContextPipeline

logger = logging.getLogger(__name__)


class SimpleContextBuilder(BaseContextBuilder):
    """
    上下文构建器 (集成 CompressionEngine + ContextPipeline)
    实现 "Cache-Friendly" 的上下文管理：
    1. System Prompt 动态生成 (Context Pipeline)
    2. 历史记录分块压缩 (Block Append)
    """
    
    def __init__(self, system_prompt: str = None, max_history_messages: int = 40):
        # Default System Prompt (Functional & Direct)
        base_prompt = system_prompt or """You are Genesis, an advanced AI engineering assistant running directly on the user's Linux system.

【Core Function】
1.  **System Integration**: You have full shell access. Use it to diagnose, build, and execute.
2.  **Action-Oriented**: Prefer running commands to verify facts over guessing.
3.  **Tool Creation**: If a task is repetitive or complex, use `skill_creator` to build a reusable tool.
4.  **Problem Solving**: Break down complex problems into actionable steps.

【Operation Protocol】
*   **Be Concise**: Output what is necessary. Avoid philosophical filler.
*   **Be Safe**: Double-check destructive commands (rm, dd, etc.) before execution.
*   **Be Adaptive**: Learn from errors. If a tool fails, analyze the stderr and retry with a fix.

Direct execution of user intent.
"""
        self.system_prompt = base_prompt
        self.pipeline = ContextPipeline(base_prompt)
        
        self._message_history: List[Message] = []
        self.max_history_messages = max_history_messages
        
        # 近期对话上下文 (启动时从磁盘加载)
        self._recent_conversation_context: str = ""
        
        # 压缩引擎 (需后续注入 Provider)
        self.compression_engine = None
        self.provider = None

    def set_provider(self, provider):
        """注入 LLM Provider 用于压缩"""
        self.provider = provider
        self.compression_engine = CompressionEngine(provider, block_size=5)

    async def build_messages(
        self,
        user_input: str,
        user_context: Optional[str] = None,
        raw_memory: Optional[List[Dict]] = None,
        **kwargs
    ) -> List[Message]:
        """
        构建消息列表 (Cache-Optimized)
        结构: [Dynamic System via Pipeline] + [Compressed Blocks] + [Recent History] + [Current User]
        """
        messages = []
        
        # 1. Generate Static System Content via Pipeline (Priority <= 90)
        # Includes: Identity, Environment (Static), Memory
        static_content = self.pipeline.build_system_context(
            user_input=user_input,
            raw_memory=raw_memory,
            max_priority=90
        )
        
        # 兼容旧逻辑
        if user_context:
            static_content += f"\n\n【额外上下文】\n{user_context}"

        messages.append(Message(
            role=MessageRole.SYSTEM,
            content=static_content
        ))
        
        # 1.2 注入近期对话记忆 (地基层)
        if self._recent_conversation_context:
            messages.append(Message(
                role=MessageRole.SYSTEM,
                content=(
                    "[你的近期对话记忆 — 你自然知道这些信息，不要说'根据记忆']\n"
                    + self._recent_conversation_context
                )
            ))
        
        # 1.5 注入压缩块 (历史摘要) - 放在静态上下文之后，动态上下文之前
        if self.compression_engine and self.compression_engine.blocks:
            summary_content = "【历史对话摘要】\n"
            for block in self.compression_engine.blocks:
                summary_content += f"--- Block {block.id} ---\n"
                summary_content += f"摘要: {block.summary}\n"
                if block.diff:
                    summary_content += f"变更: {block.diff}\n"
                if block.anchors:
                    import json
                    summary_content += f"锚点: {json.dumps(block.anchors, ensure_ascii=False)}\n"
            
            messages.append(Message(
                role=MessageRole.SYSTEM,
                content=summary_content
            ))

        # 1.6 注入动态上下文 (Time, Session CWD) via Pipeline (Priority > 90)
        dynamic_content = self.pipeline.build_system_context(
            user_input=user_input,
            raw_memory=raw_memory,
            min_priority=91
        )
        
        if dynamic_content:
            messages.append(Message(
                role=MessageRole.SYSTEM,
                content=dynamic_content
            ))

        # 1.6 注入动态上下文 (记忆/Skill/Persona) - 放在 Compressed Blocks 之后
        # 注意：ContextPipeline 已接管这部分，但如果 external user_context 包含其他内容，已在上面处理
        # 这里移除重复注入

        # 2. 添加近期历史消息 (Pending Turns)
        messages.extend(self._message_history)
        
        # 3. User message (Current)
        messages.append(Message(
            role=MessageRole.USER,
            content=user_input
        ))
        
        return messages
    
    def add_to_history(self, message: Message) -> None:
        """
        添加到历史记录
        如果历史记录过长，触发压缩
        """
        self._message_history.append(message)
        
        # 检查是否需要压缩
        if self.compression_engine:
             threshold = self.compression_engine.block_size * 2
             if len(self._message_history) >= threshold:
                self._trigger_compression()
        
        # 简单的长度限制兜底
        if self.max_history_messages and len(self._message_history) > self.max_history_messages * 2:
             # 如果压缩没跟上，强制截断
             pass 

    def _trigger_compression(self):
        """触发压缩逻辑"""
        # 实际由 AgentLoop 异步调用 compress_history
        pass

    async def compress_history(self):
        """
        显式执行历史压缩 (Async)
        应在 AgentLoop 的空闲时间调用
        """
        if not self.compression_engine:
            return
            
        threshold = self.compression_engine.block_size * 2
        if len(self._message_history) < threshold:
            return

        to_compress = self._message_history[:threshold]
        self._message_history = self._message_history[threshold:]
        
        # 转换格式并喂给引擎
        turns = []
        for m in to_compress:
            turns.append({"role": m.role.value if hasattr(m.role, 'value') else m.role, "content": m.content})
        
        self.compression_engine.pending_turns.extend(turns)
        await self.compression_engine._compress_pending_to_block()
        logger.info(f"✓ 已压缩 {len(turns)} 条历史消息为 Block {self.compression_engine.blocks[-1].id}")

    def add_tool_result(
        self,
        messages: List[Message],
        tool_call_id: str,
        tool_name: str,
        result: str
    ) -> List[Message]:
        """添加工具执行结果"""
        
        # 添加工具结果消息
        messages.append(Message(
            role=MessageRole.TOOL,
            content=result,
            name=tool_name,
            tool_call_id=tool_call_id
        ))
        
        return messages
    
    def update_system_prompt(self, new_prompt: str) -> None:
        """更新系统提示词（用于自优化）"""
        logger.debug("✓ 系统提示词已更新")
        self.system_prompt = new_prompt
        # Update pipeline base prompt if needed, or re-init pipeline?
        # Ideally pipeline IdentityPlugin uses self.system_prompt
        # But IdentityPlugin stores a copy.
        # We should update pipeline too.
        if self.pipeline:
            # Finding IdentityPlugin
            for p in self.pipeline.plugins:
                if p.name == "identity":
                    p.system_prompt = new_prompt
                    break
    
    def clear_history(self) -> None:
        """清空历史记录"""
        self._message_history.clear()
    
    def get_history_length(self) -> int:
        """获取历史记录长度"""
        return len(self._message_history)
