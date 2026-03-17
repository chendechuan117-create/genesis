"""
深度网页阅读工具 — 将 URL 转换为可阅读的 Markdown 文本
使用 Jina Reader API (r.jina.ai) 作为主引擎，curl 降级兜底。
"""

import json
import logging
import os
import subprocess
from typing import Dict, Any

from genesis.core.base import Tool

logger = logging.getLogger(__name__)


class ReadUrlTool(Tool):
    """读取 URL 内容并转为结构化文本"""

    @property
    def name(self) -> str:
        return "read_url"

    @property
    def description(self) -> str:
        return (
            "读取指定 URL 的网页内容，返回 Markdown 格式的正文。"
            "适用于阅读文档、博客、技术文章、GitHub README 等。"
            "与 web_search 互补：web_search 负责'找到页面'，read_url 负责'读懂页面'。"
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要读取的网页 URL（必须以 http:// 或 https:// 开头）"
                },
                "max_length": {
                    "type": "integer",
                    "description": "返回正文的最大字符数，默认 8000",
                    "default": 8000
                }
            },
            "required": ["url"]
        }

    async def execute(self, url: str, max_length: int = 8000) -> str:
        """读取 URL 内容"""
        if not url or not url.startswith(("http://", "https://")):
            return "Error: URL 必须以 http:// 或 https:// 开头"

        # Strategy 1: Jina Reader API (免费，无需 key，返回 Markdown)
        content = self._fetch_via_jina(url)

        # Strategy 2: 直接 curl 抓取 + 简单 HTML 清洗
        if not content or content.startswith("Error"):
            logger.info("Jina Reader failed, falling back to direct curl fetch")
            content = self._fetch_direct(url)

        if not content or content.startswith("Error"):
            return f"Error: 无法读取 {url}"

        # 截断
        if len(content) > max_length:
            content = content[:max_length] + f"\n\n... [内容已截断，共 {len(content)} 字符，显示前 {max_length} 字符]"

        return content

    def _fetch_via_jina(self, url: str) -> str:
        """通过 Jina Reader API 获取 Markdown 格式的网页内容"""
        jina_url = f"https://r.jina.ai/{url}"
        cmd = [
            "curl", "-s", "-4",
            "--max-time", "30",
            "--connect-timeout", "10",
            "-H", "Accept: text/markdown",
            "-H", "X-Return-Format: markdown",
            jina_url
        ]

        proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
        if proxy and proxy.startswith("socks5"):
            proxy = proxy.replace("socks5://", "socks5h://")
            cmd.extend(["-x", proxy])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
            if result.returncode != 0:
                return f"Error: Jina Reader curl failed (code {result.returncode}): {result.stderr[:200]}"

            text = result.stdout.strip()
            if not text or len(text) < 50:
                return f"Error: Jina Reader returned empty or too short content"

            return text

        except subprocess.TimeoutExpired:
            return "Error: Jina Reader request timed out"
        except Exception as e:
            return f"Error: Jina Reader failed: {e}"

    def _fetch_direct(self, url: str) -> str:
        """直接 curl 获取页面，做简单的 HTML -> 文本清洗"""
        cmd = [
            "curl", "-s", "-4", "-L",
            "--max-time", "20",
            "--connect-timeout", "10",
            "-H", "User-Agent: Mozilla/5.0 (compatible; Genesis/1.0)",
            url
        ]

        proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
        if proxy and proxy.startswith("socks5"):
            proxy = proxy.replace("socks5://", "socks5h://")
            cmd.extend(["-x", proxy])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if result.returncode != 0:
                return f"Error: Direct fetch failed (code {result.returncode})"

            html = result.stdout
            if not html or len(html) < 100:
                return "Error: Direct fetch returned empty content"

            return self._html_to_text(html)

        except subprocess.TimeoutExpired:
            return "Error: Direct fetch timed out"
        except Exception as e:
            return f"Error: Direct fetch failed: {e}"

    @staticmethod
    def _html_to_text(html: str) -> str:
        """极简 HTML -> 纯文本转换（不依赖外部库）"""
        import re

        # 移除 script/style 块
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

        # 标题转 Markdown
        for level in range(1, 7):
            text = re.sub(
                rf"<h{level}[^>]*>(.*?)</h{level}>",
                lambda m, l=level: f"\n{'#' * l} {m.group(1).strip()}\n",
                text, flags=re.DOTALL | re.IGNORECASE
            )

        # 段落/换行
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<p[^>]*>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</p>", "", text, flags=re.IGNORECASE)

        # 列表项
        text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.IGNORECASE)

        # 链接
        text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", text, flags=re.DOTALL | re.IGNORECASE)

        # 粗体/斜体
        text = re.sub(r"<(?:b|strong)[^>]*>(.*?)</(?:b|strong)>", r"**\1**", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<(?:i|em)[^>]*>(.*?)</(?:i|em)>", r"*\1*", text, flags=re.DOTALL | re.IGNORECASE)

        # 代码块
        text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<pre[^>]*>(.*?)</pre>", r"\n```\n\1\n```\n", text, flags=re.DOTALL | re.IGNORECASE)

        # 清理剩余标签
        text = re.sub(r"<[^>]+>", "", text)

        # HTML 实体
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'")

        # 压缩空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)

        return text.strip()
