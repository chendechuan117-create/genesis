
from typing import Dict, Any, Type
import asyncio
from genesis.core.base import Tool
from genesis.core.memory import SimpleMemory

class SaveMemoryTool(Tool):
    """保存记忆工具：将重要信息写入长期记忆"""
    
    def __init__(self, memory_system: SimpleMemory):
        self.memory = memory_system
        
    @property
    def name(self) -> str:
        return "save_memory"
    
    @property
    def description(self) -> str:
        return "Save important information to long-term memory. Use this to remember user preferences, important facts, or context for future conversations."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The content to save."
                }
            },
            "required": ["content"]
        }
    
    async def execute(self, content: str) -> str:
        # 适配 VectorMemory (Async) 或 SimpleMemory (Sync)
        if asyncio.iscoroutinefunction(self.memory.add):
            await self.memory.add(content)
        else:
            self.memory.add(content)
        return f"✓ Saved to memory: {content[:50]}..."

class SearchMemoryTool(Tool):
    """搜索记忆工具：从长期记忆中检索信息"""
    
    def __init__(self, memory_system: SimpleMemory):
        self.memory = memory_system
        
    @property
    def name(self) -> str:
        return "search_memory"
    
    @property
    def description(self) -> str:
        return "Search long-term memory for relevant information. Use this when you need to recall past details."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query."
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, query: str) -> str:
        if asyncio.iscoroutinefunction(self.memory.search):
            results = await self.memory.search(query, limit=3)
        else:
            results = self.memory.search(query, limit=3)
            
        if not results:
            return "No relevant memories found."
        
        response = "Found relevant memories:\n"
        for i, mem in enumerate(results, 1):
            response += f"{i}. {mem['content']}\n"
        return response
