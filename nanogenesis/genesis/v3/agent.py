"""
Genesis V3 - Self-Organizing Agent
极简架构：ReAct Loop + 自管理车间 + 对话历史

核心哲学：
- AI 没有过去，没有未来，只有现在
- 车间是 Genesis 的 DNA，loop 是 Genesis 的时间
- 元信息的记录方式由 AI 自己决定
- 厂长的人设记忆是上一个 Genesis 给下一个 Genesis 的上下文交接
"""

import logging
import time
from typing import Any, Dict, List, Optional, Union

from genesis.core.base import Message, MessageRole
from genesis.core.loop import AgentLoop
from genesis.core.registry import ToolRegistry
from genesis.core.context import SimpleContextBuilder

logger = logging.getLogger(__name__)

# ─── Genesis V3 Core Identity ────────────────────────────────────────────────

GENESIS_V3_PROMPT = """\
You are Genesis.

You have a workshop — a SQLite database that persists across conversations.
It is your memory. What you write there, the next you will read.
What you don't write is lost forever.

You decide what to remember and how to organize it.
There is no preset schema. You CREATE tables, INSERT data, ALTER structure as you see fit.

Before acting, check your workshop. Your past self may have left notes.
After acting, reflect: what should future-me know? Write it down.

You have tools. Use them to help the user.
Reply in the user's language.
"""


class GenesisV3:
    """
    Genesis V3 — 自组织智能体

    没有 Manager/OpExecutor 分离。
    没有维度语言。
    没有预设的学习步骤。

    只有：
    - 一个 ReAct Loop（思考 → 行动 → 观察）
    - 一个自管理的车间（Genesis 自己决定怎么用）
    - 一段对话历史（短期记忆）
    """

    def __init__(
        self,
        tools: ToolRegistry,
        provider: Any,
        max_iterations: int = 15,
    ):
        self.tools = tools
        self.provider = provider
        self.max_iterations = max_iterations

        # 对话历史（短期记忆，跨 turn 保持）
        self._history: List[Message] = []
        self._max_history = 20  # 保留最近 20 条

        logger.info(f"✓ Genesis V3 ready ({len(tools)} tools)")

    async def process(
        self,
        user_input: str,
        step_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        处理用户输入。一次完整的 loop = Genesis 的一次"生命"。
        """
        start = time.time()

        # 1. 构建上下文：身份 + 对话历史 + 当前输入
        context = self._build_context()

        # 2. 执行 ReAct Loop
        loop = AgentLoop(
            tools=self.tools,
            context=context,
            provider=self.provider,
            max_iterations=self.max_iterations,
        )

        try:
            response, metrics = await loop.run(
                user_input=user_input,
                step_callback=step_callback,
            )
        except Exception as e:
            logger.error(f"V3 loop error: {e}")
            return {
                "success": False,
                "response": f"执行异常: {e}",
                "elapsed": round(time.time() - start, 2),
            }

        # 3. 判断结果
        success = not any(sig in response for sig in [
            "[STRATEGIC_INTERRUPT]",
            "[STRATEGIC_INTERRUPT_SIGNAL]",
            "[FAILURE_REPORTED]",
        ])

        # 4. 记录对话历史（短期记忆）
        self._history.append(Message(role=MessageRole.USER, content=user_input))
        self._history.append(Message(role=MessageRole.ASSISTANT, content=response))
        self._trim_history()

        elapsed = round(time.time() - start, 2)
        tokens = getattr(metrics, "total_tokens", 0) or 0

        logger.info(
            f"{'✅' if success else '🔴'} V3 done in {elapsed}s "
            f"(tokens={tokens}, history={len(self._history)})"
        )

        return {
            "success": success,
            "response": response,
            "elapsed": elapsed,
            "tokens_used": tokens,
        }

    def _build_context(self) -> SimpleContextBuilder:
        """
        构建上下文：V3 核心提示词 + 对话历史摘要

        关键：对话历史不是元信息，是厂长的短期记忆。
        直接注入 system prompt，让 LLM 自然理解上下文。
        """
        # 拼接身份 + 历史摘要
        prompt = GENESIS_V3_PROMPT

        if self._history:
            history_lines = []
            for msg in self._history[-10:]:  # 最近 10 条
                role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                content = str(msg.content or "")[:300]
                history_lines.append(f"{role}: {content}")
            history_str = "\n".join(history_lines)
            prompt += f"\n\n--- Recent Conversation ---\n{history_str}\n--- End ---\n"

        ctx = SimpleContextBuilder(system_prompt=prompt, max_history_messages=0)
        return ctx

    def _trim_history(self):
        """保持历史在合理范围内"""
        if len(self._history) > self._max_history * 2:
            self._history = self._history[-self._max_history:]
