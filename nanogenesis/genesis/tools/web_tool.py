"""
Web 搜索工具
"""

import sys
from pathlib import Path
from typing import Dict, Any
import json
import logging

sys.path.insert(0, str(Path(__file__).parent.parent))

from genesis.core.base import Tool


logger = logging.getLogger(__name__)


class WebSearchTool(Tool):
    """Web 搜索工具（简化版）"""
    
    @property
    def name(self) -> str:
        return "web_search"
    
    @property
    def description(self) -> str:
        return """【最高优先级的信息采集工具】用于在网络上快速检索未知的事实、新闻、文档和代码问题。
        
【核心规则】：
1. 当你需要“搜索”、“上网找找”、“查一下”任何信息时，**必须第一时间、首选使用本工具**！
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
        """执行 Web 搜索"""
        try:
            from genesis.core.config import config
            import urllib.request
            import json
            import ssl
            
            if not config.tavily_api_key:
                return "Error: TAVILY_API_KEY not configured. Please add it to .env or environment variables."
                
            # Tavily API Request
            url = "https://api.tavily.com/search"
            payload = {
                "api_key": config.tavily_api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": min(num_results, 10)
            }
            
            # 使用 curl 代替 urllib，因为 urllib 原生不支持 socks5 代理，在遇到 https_proxy=socks5:// 时会抛出 Remote end closed
            import subprocess
            
            json_payload = json.dumps(payload)
            curl_cmd = [
                "curl", "-s", "-X", "POST", url,
                "-H", "Content-Type: application/json",
                "-d", json_payload,
                "--max-time", "30"
            ]
            
            # 引入 socks5h 强制远端 DNS 解析，防止被墙
            import os
            proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
            if proxy and proxy.startswith("socks5"):
                proxy = proxy.replace("socks5://", "socks5h://")
                curl_cmd.extend(["-x", proxy])
                
            process = subprocess.run(curl_cmd, capture_output=True, text=True)
            
            if process.returncode != 0:
                return f"Error: 网络请求失败 - curl 退出码 {process.returncode}\n{process.stderr}"
                
            try:
                result_json = json.loads(process.stdout)
            except json.JSONDecodeError:
                return f"Error: Tavily API 返回了非法的 JSON - {process.stdout[:200]}"
                
            results = result_json.get('results', [])
            
            # 格式化输出
            output = [f"搜索: {query}", f"结果数: {len(results)}\n"]
            
            for i, result in enumerate(results, 1):
                title = result.get('title', 'No Title')
                url = result.get('url', '#')
                content = result.get('content', '')[:200] + "..." # 截断过长内容
                
                output.append(f"{i}. {title}")
                output.append(f"   {url}")
                output.append(f"   {content}\n")
            
            return "\n".join(output)
        
        except Exception as e:
            logger.error(f"搜索失败: {e}", exc_info=True)
            return f"Error: 搜索失败 - {str(e)}"


class FetchURLTool(Tool):
    """获取 URL 内容工具"""
    
    @property
    def name(self) -> str:
        return "fetch_url"
    
    @property
    def description(self) -> str:
        return "获取指定 URL 的内容（HTML 或文本）"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要获取的 URL"
                },
                "max_length": {
                    "type": "integer",
                    "description": "最大内容长度，默认 10000",
                    "default": 10000
                }
            },
            "required": ["url"]
        }
    
    async def execute(self, url: str, max_length: int = 10000) -> str:
        """获取 URL 内容"""
        try:
            # TODO: 实现真实的 URL 获取
            # 需要 aiohttp 或 httpx
            
            return f"""URL: {url}
状态: 200 OK
内容长度: 模拟数据

注意: 此功能需要安装 aiohttp 或 httpx 才能使用
"""
        
        except Exception as e:
            logger.error(f"获取 URL 失败: {e}", exc_info=True)
            return f"Error: 获取 URL 失败 - {str(e)}"
