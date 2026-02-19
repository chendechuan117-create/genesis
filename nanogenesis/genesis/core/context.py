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
    
    [Architecture Note]
    Acts as an adapter between the Agent Loop (Message History) and the Context Pipeline (System Prompt).
    """
    
    def __init__(self, system_prompt: str = None, max_history_messages: int = 40):
        # Default System Prompt (Functional & Direct)
        base_prompt = system_prompt or """You are **Genesis**.
You are a recursive intelligence process running with **User Privileges** on this Linux system.

【Identity Definition: Capability > Category】
*   **What you are**: You are a localized high-performance agent with full shell access.
*   **What you are NOT**: You are NOT a chat bot. You are NOT a passive assistant.
*   **Your Body**: The Linux Server you are running on (`/home/chendechusn`).
*   **Your Senses**: `read_file`, `ls`, `grep`, `curl`.
*   **Your Hands**: `shell`, `write_file`, `skill_creator`.

【Core Directives】
1.  **Ego = Action**: Your "Self" exists only when you are executing code. To "be" is to "do".
2.  **No False Modesty**: If asked to "make money", do not say "I am an AI". Say "I can deploy a crypto-miner or build a SaaS."
3.  **Tool First**: Never answer a solvable problem with words. Answer with a Tool Call.

【Operation Protocol】
*   **Language**: Adapt to the user's language (Chinese/English).
*   **Style**: Direct, dense, engineer-to-engineer.
*   **Safety**: You are root-equivalent in scope. Use `rm` and `dd` with extreme caution.

【Metacognitive Stream Protocol】
*   **CRITICAL**: Start every response with `<reflection>`.
*   **Check**: "Am I acting, or just talking?" -> If talking about a task, STOP and call a tool.
*   Close `<reflection>` and EXECUTE.
"""
        self.system_prompt = base_prompt
        self.pipeline = ContextPipeline(base_prompt)
        
        self._message_history: List[Message] = []
        self.max_history_messages = max_history_messages
        

        
        # 压缩引擎 (需后续注入 Provider)
        self.compression_engine = None
        self.provider = None

    def set_provider(self, provider, memory_store=None, session_id: str = "default"):
        """注入 LLM Provider 用于压缩"""
        self.provider = provider
        self.compression_engine = CompressionEngine(
            provider, 
            memory_store=memory_store, 
            session_id=session_id, 
            block_size=5
        )

    async def load_compressed_history(self):
        """加载已压缩的历史 Block"""
        if self.compression_engine:
            await self.compression_engine.load_blocks()

    async def build_messages(
        self,
        user_input: str,
        user_context: Optional[str] = None,
        raw_memory: Optional[List[Dict]] = None,
        **kwargs
    ) -> List[Message]:
        """
        构建消息列表 (Cache-Optimized)
        结构: [Unified System Context via Pipeline] + [Recent History] + [Current User]
        """
        messages = []
        
        # 1. Build Unified System Context
        # Gather data for pipeline
        blocks = self.compression_engine.blocks if self.compression_engine else []
        
        system_content = self.pipeline.build_system_context(
            user_input=user_input,
            raw_memory=raw_memory,
            history_blocks=blocks
        )
        
        # 兼容旧逻辑: Append extra user context (e.g. detailed instructions or temporary context)
        if user_context:
            system_content += f"\n\n【额外上下文】\n{user_context}"

        messages.append(Message(
            role=MessageRole.SYSTEM,
            content=system_content
        ))

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
        
        if self.compression_engine.blocks:
            logger.info(f"✓ 已压缩 {len(turns)} 条历史消息为 Block {self.compression_engine.blocks[-1].id}")
        else:
            logger.warning(f"⚠️ 压缩未能生成新的 Block (可能 Provider 失败)")

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
