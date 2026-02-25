import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool


class CustomWebSearchTool(Tool):
    @property
    def name(self):
        return "custom_web_search"
    
    @property
    def description(self):
        return "自定义网页搜索工具，使用浏览器作为备用方案"
    
    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询"},
                "use_browser": {"type": "boolean", "default": True, "description": "是否使用浏览器作为备用"}
            },
            "required": ["query"]
        }
    
    async def execute(self, query, use_browser=True):
        try:
            # 先尝试Tavily
            # 如果失败，使用浏览器作为备用
            if use_browser:
                return f"搜索查询: {query}\n由于Tavily问题，建议使用browser_tool手动搜索"
            else:
                return "搜索功能暂时不可用，正在修复中"
        except Exception as e:
            return f"搜索失败: {str(e)}"
