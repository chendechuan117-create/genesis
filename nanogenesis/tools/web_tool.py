"""
Web 搜索工具
"""

import sys
from pathlib import Path
from typing import Dict, Any
import json
import logging

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.base import Tool


logger = logging.getLogger(__name__)


class WebSearchTool(Tool):
    """Web 搜索工具（简化版）"""
    
    @property
    def name(self) -> str:
        return "web_search"
    
    @property
    def description(self) -> str:
        return """在网络上搜索信息。
        
注意：
- 返回搜索结果摘要
- 包含标题、链接、描述
- 最多返回指定数量的结果"""
    
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
            from core.config import config
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
            
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            
            # 使用不验证 SSL 的 context (防止本地证书问题)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
                result_json = json.loads(response.read().decode('utf-8'))
                
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
