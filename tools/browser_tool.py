"""
浏览器控制工具 - NanoGenesis Browser Capability
提供标准化的网页访问接口。
在 Web 服务模式下使用 curl 抓取内容（而非 xdg-open），避免在无桌面环境中卡死。
"""

import os
import sys
import logging
import shlex
import subprocess
import urllib.parse
from typing import Dict, Any, Optional

from core.base import Tool

logger = logging.getLogger(__name__)

# 检测是否在 systemd 服务或无桌面环境中运行
def _is_headless():
    """判断当前是否为无头模式（systemd 服务、SSH 等）"""
    return not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY')


class BrowserTool(Tool):
    """
    浏览器/网页工具
    - 有桌面时：打开浏览器
    - 无桌面时（systemd 服务）：用 curl 抓取网页内容并返回摘要
    """
    name = "browser_tool"
    description = "用于打开网页或在浏览器中搜索。当用户要求访问某个网站或搜索信息时，优先使用此工具。"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["open", "search"],
                "description": "操作类型：open (打开特定URL) 或 search (搜索关键词)"
            },
            "url": {
                "type": "string",
                "description": "要打开的网址 (仅 action=open 时需要)"
            },
            "query": {
                "type": "string",
                "description": "搜索关键词 (仅 action=search 时需要)"
            }
        },
        "required": ["action"]
    }

    async def execute(self, action: str, url: str = None, query: str = None) -> str:
        """执行浏览器操作"""
        try:
            if action == "open":
                if not url:
                    return "Error: URL is required for 'open' action"
                
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url
                    
                logger.info(f"🌐 Fetching URL: {url}")
                
                if _is_headless():
                    # 无头模式：用 curl 抓取内容
                    return await self._fetch_with_curl(url)
                else:
                    # 有桌面：后台打开浏览器（不阻塞）
                    try:
                        subprocess.Popen(
                            ['xdg-open', url],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True
                        )
                        return f"已在默认浏览器中打开: {url}"
                    except Exception:
                        return await self._fetch_with_curl(url)
                
            elif action == "search":
                if not query:
                    return "Error: query is required for 'search' action"
                
                search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                logger.info(f"🔍 Searching: {query}")
                
                if _is_headless():
                    return await self._fetch_with_curl(search_url)
                else:
                    try:
                        subprocess.Popen(
                            ['xdg-open', search_url],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True
                        )
                        return f"已在浏览器中搜索: {query}"
                    except Exception:
                        return await self._fetch_with_curl(search_url)
            
            else:
                return f"Unknown action: {action}"
                
        except Exception as e:
            logger.error(f"浏览器操作失败: {e}")
            return f"Error: {str(e)}"

    async def _fetch_with_curl(self, url: str) -> str:
        """使用 curl 抓取网页内容（带超时保护）"""
        try:
            result = subprocess.run(
                ['curl', '-sL', '--max-time', '15', '-A',
                 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                 url],
                capture_output=True, text=True, timeout=20
            )
            
            if result.returncode != 0:
                return f"无法访问 {url}: curl 返回码 {result.returncode}"
            
            content = result.stdout
            
            # 简单提取文本（去除 HTML 标签）
            import re
            # 移除 script 和 style
            content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
            content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
            # 移除 HTML 标签
            content = re.sub(r'<[^>]+>', ' ', content)
            # 清理空白
            content = re.sub(r'\s+', ' ', content).strip()
            
            # 截断过长内容
            if len(content) > 3000:
                content = content[:3000] + "... [内容已截断]"
            
            if not content.strip():
                return f"已访问 {url}，但页面内容为空或全是动态加载内容。"
            
            return f"已抓取 {url} 的内容:\n\n{content}"
            
        except subprocess.TimeoutExpired:
            return f"访问 {url} 超时（15秒限制）"
        except Exception as e:
            return f"抓取失败: {str(e)}"
