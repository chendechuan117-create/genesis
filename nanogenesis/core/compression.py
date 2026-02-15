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
    def __init__(self, provider, block_size: int = 5):
        self.provider = provider # LLM Provider 用于执行压缩
        self.block_size = block_size
        self.blocks: List[CompressedBlock] = []
        self.pending_turns: List[Dict[str, str]] = [] # 未压缩的最近几轮
        self.system_prompt_hash = "" # 用于检测前缀是否变动
    
    def add_interaction(self, user_input: str, agent_response: str):
        """添加一轮交互"""
        self.pending_turns.append({"role": "user", "content": user_input})
        self.pending_turns.append({"role": "assistant", "content": agent_response})
        
        # 自动压缩逻辑已移至 Agent 层显式调用，避免 Sync/Async 混用问题
        # if len(self.pending_turns) >= self.block_size * 2:
        #    self._compress_pending_to_block()

    def get_context_for_api(self, system_prompt: str) -> List[Dict[str, str]]:
        """
        生成用于 API 调用的上下文
        结构: [Fixed System Prompt] + [Compressed Blocks] + [Recent Pending Turns]
        """
        messages = [{"role": "system", "content": system_prompt}]
        
        # 1. 注入压缩块 (作为 System 提示的一部分或独立的 Context 消息)
        # 为了利用 Cache，这些文本必须保持稳定
        if self.blocks:
            context_summary = "【历史对话摘要】\n"
            for block in self.blocks:
                context_summary += f"--- Block {block.id} ---\n"
                context_summary += f"摘要: {block.summary}\n"
                if block.diff:
                    context_summary += f"变更: {block.diff}\n"
                if block.anchors:
                    context_summary += f"锚点: {json.dumps(block.anchors, ensure_ascii=False)}\n"
            
            # 将摘要作为第二个 system 消息或 user 消息的背景
            # DeepSeek 推荐将长 Context 放在开头
            messages.append({"role": "system", "content": context_summary})

        # 2. 注入最近的未压缩对话
        messages.extend(self.pending_turns)
        
        return messages

    async def _compress_pending_to_block(self):
        """执行压缩 (调用 LLM)"""
        # 取出要压缩的消息
        to_compress = self.pending_turns[:]
        self.pending_turns = [] # 清空缓冲
        
        # 构造压缩指令
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
            # 调用 LLM 进行压缩 (使用 Fast Lane / Local LLM 以节省成本，或者 Cloud LLM)
            # 这里为了质量，建议用 Cloud LLM，但 Token 较少
            response = await self.provider.chat([{"role": "user", "content": prompt}])
            content = response.content
            
            # 解析 JSON (简单的容错处理)
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = {"summary": content, "diff": "", "anchors": {}}
                
            block = CompressedBlock(
                id=str(len(self.blocks) + 1),
                start_index=0, # TODO: 维护全局索引
                end_index=0,
                summary=data.get("summary", ""),
                diff=data.get("diff", ""),
                anchors=data.get("anchors", {}),
                raw_hash=str(hash(json.dumps(to_compress)))
            )
            
            self.blocks.append(block)
            
        except Exception as e:
            # 压缩失败，回滚
            print(f"压缩失败: {e}")
            self.pending_turns = to_compress + self.pending_turns

