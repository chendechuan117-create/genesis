"""
NanoGenesis 压缩核心 (Compression Engine)
实现 "Cache-Friendly" 的上下文管理策略，最大化 DeepSeek 缓存命中率。

理论基础：
1. Immutable Prefix (不可变前缀): 锁定 System Prompt
2. Block Append (块状追加): 历史记录分块压缩，旧块保持不变
3. Semantic Anchor (语义锚点): 强制保留关键变量
"""

import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import time

@dataclass
class CompressedBlock:
    """压缩块"""
    id: str
    start_index: int
    end_index: int
    summary: str  # 逻辑摘要
    diff: str     # 关键 Diff (报错/代码变更)
    anchors: Dict[str, str] # 语义锚点 (关键变量状态)
    raw_hash: str # 原始数据的哈希 (用于校验)

class CompressionEngine:
    def __init__(self, provider, memory_store=None, session_id: str = "default", block_size: int = 5):
        self.provider = provider
        self.memory_store = memory_store
        self.session_id = session_id
        self.block_size = block_size
        self.blocks: List[CompressedBlock] = []
        self.pending_turns: List[Dict[str, str]] = []
        self.system_prompt_hash = "" 

    async def load_blocks(self):
        """从存储加载 Block"""
        if not self.memory_store:
            return
            
        try:
            stored_blocks = await self.memory_store.get_blocks(self.session_id)
            import json
            for b in stored_blocks:
                self.blocks.append(CompressedBlock(
                    id=b['id'],
                    start_index=b['start_index'],
                    end_index=b['end_index'],
                    summary=b['summary'],
                    diff=b['diff'],
                    anchors=json.loads(b['anchors']) if b['anchors'] else {},
                    raw_hash=b['raw_hash']
                ))
            print(f"📦 已加载 {len(self.blocks)} 个历史压缩块")
        except Exception as e:
            print(f"加载压缩块失败: {e}")

    async def _compress_pending_to_block(self):
        """执行压缩 (调用 LLM)"""
        # 取出要压缩的消息
        to_compress = self.pending_turns[:]
        self.pending_turns = [] # 清空缓冲
        
        # 构造压缩指令
        # ... (Prompt Omitted for brevity, logic remains same) ...
        prompt = f"""
        请对以下 {len(to_compress)//2} 轮对话进行【无损逻辑压缩】。
        
        要求：
        1. 摘要：用极简语言概括核心进展。
        2. Diff：提取代码修改的关键部分或报错信息。
        3. 锚点：提取当前的关键变量名、IP地址、文件路径。
        
        对话内容：
        {json.dumps(to_compress, ensure_ascii=False)}
        
        返回 JSON 格式：
        {{
            "summary": "...",
            "diff": "...",
            "anchors": {{ "ip": "...", "file": "..." }}
        }}
        """
        
        try:
            # 调用 LLM 进行压缩
            response = await self.provider.chat([{"role": "user", "content": prompt}])
            content = response.content
            
            # 解析 JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = {"summary": content, "diff": "", "anchors": {}}
             
            import time
            from datetime import datetime   
            block = CompressedBlock(
                id=f"blk_{int(time.time())}",
                start_index=0, 
                end_index=0,
                summary=data.get("summary", ""),
                diff=data.get("diff", ""),
                anchors=data.get("anchors", {}),
                raw_hash=str(hash(json.dumps(to_compress)))
            )
            
            self.blocks.append(block)
            
            # Persist if storage available
            if self.memory_store:
                await self.memory_store.save_block({
                    "id": block.id,
                    "session_id": self.session_id,
                    "start_index": block.start_index,
                    "end_index": block.end_index,
                    "summary": block.summary,
                    "diff": block.diff,
                    "anchors": json.dumps(block.anchors, ensure_ascii=False),
                    "raw_hash": block.raw_hash,
                    "created_at": datetime.now().isoformat()
                })
            
        except Exception as e:
            # 压缩失败，回滚
            print(f"压缩失败: {e}")
            self.pending_turns = to_compress + self.pending_turns

