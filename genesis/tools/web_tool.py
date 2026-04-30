"""
Web 搜索工具
双引擎：SearXNG（自建，无限免费）→ Tavily（付费 fallback）
"""

from typing import Dict, Any
import json
import logging
import os
import subprocess

from genesis.core.base import Tool


logger = logging.getLogger(__name__)

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8080")


class WebSearchTool(Tool):
    """Web 搜索工具（SearXNG + Tavily 双引擎）"""
    
    def is_concurrency_safe(self, arguments: Dict[str, Any]) -> bool:
        return True  # 只读搜索，可并行
    
    @property
    def name(self) -> str:
        return "web_search"
    
    @property
    def description(self) -> str:
        return """【最高优先级的信息采集工具】用于在网络上快速检索未知的事实、新闻、文档和代码问题。
        
【核心规则】：
1. 当你需要"搜索"、"上网找找"、"查一下"任何信息时，**必须第一时间、首选使用本工具**！
2. 绝对不要使用 browser_tool 进行普通的网页搜索，browser_tool 只用于需要物理桌面浏览器交互的特殊场景。
3. 本工具使用高并发无头 API 后台搜索，速度极快且不会卡死。"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询"
                },
                "num_results": {
                    "type": "integer",
                    "description": "返回结果数量，默认 5",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, query: str, num_results: int = 5) -> str:
        """执行 Web 搜索：SearXNG 优先，Tavily 兜底"""
        # Strategy 1: SearXNG（自建，无限免费，多引擎聚合）
        result = self._search_searxng(query, num_results)
        if result and not result.startswith("Error"):
            return result

        # Strategy 2: Tavily（付费，稳定）
        logger.info(f"SearXNG failed, falling back to Tavily for: {query[:40]}")
        result = self._search_tavily(query, num_results)
        if result and not result.startswith("Error"):
            return result

        return f"Error: 搜索失败（SearXNG + Tavily 均不可用）"

    def _search_searxng(self, query: str, num_results: int) -> str:
        """通过本地 SearXNG 实例搜索"""
        try:
            import urllib.parse
            url = f"{SEARXNG_URL}/search"
            encoded_q = urllib.parse.quote(query)
            cmd = [
                "curl", "-s",
                "--max-time", "15",
                "--connect-timeout", "5",
                f"{url}?q={encoded_q}&format=json&pageno=1"
            ]
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if process.returncode != 0:
                return f"Error: SearXNG curl failed (code {process.returncode})"
            
            data = json.loads(process.stdout)
            results = data.get("results", [])
            if not results:
                unresponsive = data.get("unresponsive_engines", [])
                if unresponsive:
                    return f"Error: SearXNG engines unresponsive: {unresponsive}"
                return "Error: SearXNG returned 0 results"
            
            results = results[:min(num_results, 10)]
            return self._format_results(query, results, source="SearXNG")
        
        except subprocess.TimeoutExpired:
            return "Error: SearXNG request timed out"
        except json.JSONDecodeError:
            return "Error: SearXNG returned invalid JSON"
        except Exception as e:
            return f"Error: SearXNG failed: {e}"

    def _search_tavily(self, query: str, num_results: int) -> str:
        """通过 Tavily API 搜索（付费兜底）"""
        try:
            from genesis.core.config import config
            
            if not config.tavily_api_key:
                return "Error: TAVILY_API_KEY not configured"
                
            url = "https://api.tavily.com/search"
            payload = {
                "api_key": config.tavily_api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": min(num_results, 10)
            }
            
            json_payload = json.dumps(payload)
            curl_cmd = [
                "curl", "-s", "-X", "POST", url,
                "-H", "Content-Type: application/json",
                "-d", json_payload,
                "--max-time", "30"
            ]
            
            proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
            if proxy and proxy.startswith("socks5"):
                proxy = proxy.replace("socks5://", "socks5h://")
                curl_cmd.extend(["-x", proxy])
                
            process = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=35)
            
            if process.returncode != 0:
                return f"Error: Tavily curl failed (code {process.returncode})"
                
            data = json.loads(process.stdout)
            results = data.get("results", [])
            if not results:
                return "Error: Tavily returned 0 results"
            
            return self._format_results(query, results, source="Tavily")
        
        except subprocess.TimeoutExpired:
            return "Error: Tavily request timed out"
        except json.JSONDecodeError:
            return "Error: Tavily returned invalid JSON"
        except Exception as e:
            logger.error(f"Tavily 搜索失败: {e}", exc_info=True)
            return f"Error: Tavily failed: {e}"

    @staticmethod
    def _format_results(query: str, results: list, source: str = "") -> str:
        """统一格式化搜索结果"""
        output = [f"搜索: {query}", f"结果数: {len(results)}（{source}）\n"]
        
        for i, result in enumerate(results, 1):
            title = result.get("title", "No Title")
            url = result.get("url", "#")
            content = result.get("content", "")[:200]
            if content:
                content += "..."
            
            output.append(f"{i}. {title}")
            output.append(f"   {url}")
            if content:
                output.append(f"   {content}\n")
            else:
                output.append("")
        
        return "\n".join(output)
