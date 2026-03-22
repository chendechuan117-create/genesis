"""
browser-use 浏览器自动化工具
LLM 驱动的智能浏览器操作，适用于需要登录、填表、多步交互的场景。
使用 Groq（免费）作为驱动 LLM，节省主模型 token。
"""

import asyncio
import logging
import os
from typing import Dict, Any, Optional

from genesis.core.base import Tool

logger = logging.getLogger(__name__)

# 进程级 Browser 实例复用
_browser = None
_browser_lock = asyncio.Lock() if hasattr(asyncio, 'Lock') else None


class BrowserUseTool(Tool):
    """LLM 驱动的浏览器自动化工具（基于 browser-use）"""

    @property
    def name(self) -> str:
        return "browser_agent"

    @property
    def description(self) -> str:
        return (
            "LLM 驱动的智能浏览器自动化工具。适用于需要与网页进行复杂交互的场景：\n"
            "- 登录网站、填写表单\n"
            "- 多步骤网页操作（如：在 GitHub 上搜索项目并查看 README）\n"
            "- 抓取需要 JavaScript 渲染的动态页面内容\n"
            "- 操作需要身份验证的页面\n\n"
            "【注意】此工具比 web_search 和 read_url 慢且开销大，仅在普通搜索/阅读无法完成时使用。"
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "要执行的浏览器任务描述（自然语言），例如：'打开 GitHub 搜索 browser-use 项目，获取 README 内容'"
                },
                "start_url": {
                    "type": "string",
                    "description": "起始 URL（可选，省略则由 Agent 自行决定）",
                    "default": ""
                },
                "max_steps": {
                    "type": "integer",
                    "description": "最大操作步数，默认 10，防止无限循环",
                    "default": 10
                }
            },
            "required": ["task"]
        }

    async def execute(self, task: str, start_url: str = "", max_steps: int = 10) -> str:
        """执行浏览器自动化任务"""
        try:
            from browser_use import Agent, Browser, BrowserConfig
            from langchain_openai import ChatOpenAI
        except ImportError as e:
            return f"Error: 依赖缺失 — {e}。需要: pip install browser-use langchain-openai"

        # 用 Groq 免费 LLM 驱动浏览器（节省 DeepSeek token）
        llm = self._get_llm()
        if not llm:
            return "Error: 无法初始化 LLM（需要 GROQ_API_KEY 或 DEEPSEEK_API_KEY）"

        try:
            # 配置浏览器
            proxy_url = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
            browser_config = BrowserConfig(
                headless=True,
                disable_security=True,
            )
            if proxy_url:
                browser_config.proxy = {"server": proxy_url}

            browser = Browser(config=browser_config)

            # 构建完整任务描述
            full_task = task
            if start_url:
                full_task = f"首先打开 {start_url}，然后 {task}"

            agent = Agent(
                task=full_task,
                llm=llm,
                browser=browser,
                max_actions_per_step=3,
                use_vision=False,
            )

            result = await asyncio.wait_for(
                agent.run(max_steps=max_steps),
                timeout=max_steps * 30  # 每步最多 30s
            )

            await browser.close()

            # 提取结果
            if result and hasattr(result, 'final_result') and result.final_result:
                return f"[browser-use 完成]\n{result.final_result()}"
            elif result:
                return f"[browser-use 完成]\n任务已执行，共 {len(result.history) if hasattr(result, 'history') else '?'} 步"
            else:
                return "Error: browser-use 返回空结果"

        except asyncio.TimeoutError:
            return f"Error: 浏览器任务超时（{max_steps * 30}s）"
        except Exception as e:
            logger.error(f"browser-use failed: {e}", exc_info=True)
            return f"Error: browser-use 执行失败 — {str(e)[:200]}"

    @staticmethod
    def _get_llm() -> Optional[Any]:
        """获取用于驱动浏览器的 LLM（优先 Groq 免费，次选 DeepSeek）"""
        try:
            from langchain_openai import ChatOpenAI

            # 优先 Groq（免费）
            groq_key = os.environ.get("GROQ_API_KEY")
            if groq_key:
                return ChatOpenAI(
                    model="llama-3.3-70b-versatile",
                    api_key=groq_key,
                    base_url="https://api.groq.com/openai/v1",
                    temperature=0.0,
                )

            # 次选 DeepSeek
            ds_key = os.environ.get("DEEPSEEK_API_KEY")
            if ds_key:
                return ChatOpenAI(
                    model="deepseek-chat",
                    api_key=ds_key,
                    base_url="https://api.deepseek.com",
                    temperature=0.0,
                )

            return None
        except Exception as e:
            logger.error(f"Failed to init LLM for browser-use: {e}")
            return None
