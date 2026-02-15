
from typing import Dict, Any, Type
import asyncio
from core.base import Tool
from core.memory import SimpleMemory

class MemoryTool(Tool):
    """记忆工具：允许 Agent 主动保存和检索长期记忆"""
    
    def __init__(self, memory_system: SimpleMemory):
        self.memory = memory_system
        
    @property
    def name(self) -> str:
        return "memory_tool"
    
    @property
    def description(self) -> str:
        return """管理长期记忆。
        当用户要求记住某些信息，或者你需要检索之前的对话细节/知识时使用。
        支持功能：
        - save: 保存重要信息
        - search: 搜索相关记忆"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["save", "search"],
                    "description": "要执行的操作"
                },
                "content": {
                    "type": "string",
                    "description": "要保存的内容 或 要搜索的查询词"
                }
            },
            "required": ["action", "content"]
        }
    
    async def execute(self, action: str, content: str) -> str:
        if action == "save":
            # 适配 VectorMemory (Async) 或 SimpleMemory (Sync)
            if  asyncio.iscoroutinefunction(self.memory.add):
                await self.memory.add(content)
            else:
                self.memory.add(content)
            return f"✓ 已保存记忆: {content[:50]}..."
            
        elif action == "search":
            if asyncio.iscoroutinefunction(self.memory.search):
                results = await self.memory.search(content, limit=3)
            else:
                results = self.memory.search(content, limit=3)
                
            if not results:
                return "未找到相关记忆。"
            
            response = "找到以下相关记忆:\n"
            for i, mem in enumerate(results, 1):
                response += f"{i}. {mem['content']}\n"
            return response
            
        return f"未知操作: {action}"
