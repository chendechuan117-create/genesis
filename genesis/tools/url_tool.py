"""
深度网页阅读工具 — 将 URL 转换为可阅读的 Markdown 文本
四层降级：trafilatura（快速内容提取）→ Playwright（JS 渲染）→ Jina Reader → curl 兜底
"""

import atexit
import asyncio
import logging
import os
import subprocess
from typing import Dict, Any

from genesis.core.base import Tool

logger = logging.getLogger(__name__)

# Playwright 浏览器实例复用（进程级单例，避免每次调用启动新浏览器）
_pw_browser = None
_pw_lock = asyncio.Lock() if hasattr(asyncio, 'Lock') else None


def _cleanup_playwright():
    """进程退出时关闭 Playwright 浏览器，防止 Chromium 子进程残留"""
    global _pw_browser
    if _pw_browser and _pw_browser.is_connected():
        try:
            import asyncio as _aio
            loop = _aio.get_event_loop()
            if loop.is_running():
                loop.create_task(_pw_browser.close())
            else:
                loop.run_until_complete(_pw_browser.close())
        except Exception:
            pass
        _pw_browser = None

atexit.register(_cleanup_playwright)


async def _get_playwright_browser():
    """懒初始化 Playwright 浏览器（Chromium headless），进程内复用。"""
    global _pw_browser, _pw_lock
    if _pw_lock is None:
        _pw_lock = asyncio.Lock()
    async with _pw_lock:
        if _pw_browser and _pw_browser.is_connected():
            return _pw_browser
        try:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            proxy_url = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
            launch_args = {"headless": True, "args": ["--no-sandbox", "--disable-gpu"]}
            if proxy_url:
                launch_args["proxy"] = {"server": proxy_url}
            _pw_browser = await pw.chromium.launch(**launch_args)
            logger.info("Playwright browser launched (headless Chromium)")
            return _pw_browser
        except Exception as e:
            logger.warning(f"Playwright launch failed: {e}")
            return None


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
        """读取 URL 内容，四层降级"""
        if not url or not url.startswith(("http://", "https://")):
            return "Error: URL 必须以 http:// 或 https:// 开头"

        strategy_used = ""

        # Strategy 1: trafilatura 直接抓取+提取（快速，无需浏览器，质量高）
        content = await asyncio.to_thread(self._fetch_via_trafilatura, url)
        if content and not content.startswith("Error"):
            strategy_used = "trafilatura"
        
        # Strategy 2: Playwright JS 渲染 + trafilatura 提取（JS-heavy 页面）
        if not content or content.startswith("Error"):
            logger.info(f"trafilatura failed for {url[:60]}, trying Playwright...")
            content = await self._fetch_via_playwright(url)
            if content and not content.startswith("Error"):
                strategy_used = "playwright"

        # Strategy 3: Jina Reader API (免费，无需 key)
        if not content or content.startswith("Error"):
            logger.info(f"Playwright failed for {url[:60]}, trying Jina Reader...")
            content = await asyncio.to_thread(self._fetch_via_jina, url)
            if content and not content.startswith("Error"):
                strategy_used = "jina"

        # Strategy 4: curl 直接抓取 + 极简清洗（最后兜底）
        if not content or content.startswith("Error"):
            logger.info(f"Jina failed for {url[:60]}, falling back to curl...")
            content = await asyncio.to_thread(self._fetch_direct, url)
            if content and not content.startswith("Error"):
                strategy_used = "curl"

        if not content or content.startswith("Error"):
            return f"Error: 无法读取 {url}（四层策略均失败）"

        logger.info(f"URL fetched via {strategy_used}: {url[:60]}... ({len(content)} chars)")

        # 截断
        if len(content) > max_length:
            content = content[:max_length] + f"\n\n... [内容已截断，共 {len(content)} 字符，显示前 {max_length} 字符]"

        return content

    # ── Strategy 1: trafilatura ──────────────────────────────
    @staticmethod
    def _fetch_via_trafilatura(url: str) -> str:
        """trafilatura: 自带 HTTP 抓取 + 学术级内容提取，输出 Markdown。"""
        try:
            import trafilatura
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return "Error: trafilatura fetch returned empty"
            text = trafilatura.extract(
                downloaded,
                output_format="markdown",
                include_links=True,
                include_tables=True,
                include_images=False,
                favor_recall=True,
            )
            if not text or len(text) < 50:
                return "Error: trafilatura extracted too little content"
            return text
        except Exception as e:
            return f"Error: trafilatura failed: {e}"

    # ── Strategy 2: Playwright + trafilatura ─────────────────
    @staticmethod
    async def _fetch_via_playwright(url: str) -> str:
        """Playwright 渲染 JS → trafilatura 提取正文。处理 SPA/JS-heavy 页面。"""
        browser = await _get_playwright_browser()
        if not browser:
            return "Error: Playwright not available"
        page = None
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # 等待额外 2s 让 JS 渲染完成
            await asyncio.sleep(2)
            html = await page.content()
            if not html or len(html) < 200:
                return "Error: Playwright got empty page"
            
            import trafilatura
            text = trafilatura.extract(
                html,
                output_format="markdown",
                include_links=True,
                include_tables=True,
                include_images=False,
                favor_recall=True,
            )
            if not text or len(text) < 50:
                return "Error: Playwright+trafilatura extracted too little"
            return text
        except Exception as e:
            return f"Error: Playwright failed: {e}"
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

    # ── Strategy 3: Jina Reader ──────────────────────────────
    @staticmethod
    def _fetch_via_jina(url: str) -> str:
        """Jina Reader API: 免费，无需 key，返回 Markdown。"""
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
                return f"Error: Jina Reader curl failed (code {result.returncode})"
            text = result.stdout.strip()
            if not text or len(text) < 50:
                return "Error: Jina Reader returned empty or too short content"
            return text
        except subprocess.TimeoutExpired:
            return "Error: Jina Reader request timed out"
        except Exception as e:
            return f"Error: Jina Reader failed: {e}"

    # ── Strategy 4: curl + regex 兜底 ────────────────────────
    @staticmethod
    def _fetch_direct(url: str) -> str:
        """直接 curl 获取页面，用 trafilatura 提取（比 regex 好），最后退化到 regex。"""
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
            # 优先用 trafilatura 提取
            try:
                import trafilatura
                text = trafilatura.extract(
                    html, output_format="markdown",
                    include_links=True, include_tables=True, favor_recall=True,
                )
                if text and len(text) >= 50:
                    return text
            except Exception:
                pass
            # 最后退化到 regex
            return ReadUrlTool._html_to_text(html)
        except subprocess.TimeoutExpired:
            return "Error: Direct fetch timed out"
        except Exception as e:
            return f"Error: Direct fetch failed: {e}"

    @staticmethod
    def _html_to_text(html: str) -> str:
        """极简 HTML -> 纯文本转换（最后兜底，不依赖外部库）"""
        import re
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        for level in range(1, 7):
            text = re.sub(
                rf"<h{level}[^>]*>(.*?)</h{level}>",
                lambda m, l=level: f"\n{'#' * l} {m.group(1).strip()}\n",
                text, flags=re.DOTALL | re.IGNORECASE
            )
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<p[^>]*>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</p>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.IGNORECASE)
        text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<(?:b|strong)[^>]*>(.*?)</(?:b|strong)>", r"**\1**", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<(?:i|em)[^>]*>(.*?)</(?:i|em)>", r"*\1*", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<pre[^>]*>(.*?)</pre>", r"\n```\n\1\n```\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'")
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()
