
import logging
import re
from typing import Dict, List, Optional, Any
from .context_pipeline import ContextPlugin

logger = logging.getLogger(__name__)

class SymbolicCompressor:
    """
    表示层压缩器 (Representational Compressor)
    将长文本块替换为短符号 (如 {l1}, {l2}) 以节省 Context Token。
    """
    
    def __init__(self, prefix: str = "l", min_len: int = 200):
        self.prefix = prefix
        self.min_len = min_len
        self.mapping: Dict[str, str] = {}
        self.counter = 0
        
    def compress(self, text: str, label: str = None) -> str:
        """
        如果文本足够长，将其替换为符号并存入映射表。
        """
        if len(text) < self.min_len:
            return text
            
        self.counter += 1
        symbol = f"{{{self.prefix}{self.counter}}}"
        if label:
            symbol_with_label = f"{{{self.prefix}:{label}}}"
            symbol = symbol_with_label
            
        self.mapping[symbol] = text
        logger.debug(f"已压缩文本块为符号: {symbol} (节省 {len(text) - len(symbol)} 字符)")
        return symbol

    def get_mapping_table(self) -> str:
        """
        生成传给 LLM 的映射指令。
        """
        if not self.mapping:
            return ""
            
        table = "\n[Representation Mapping Table]\n"
        table += "为了节省 Token，以下长文本块已映射为短符号。请在理解时自动替换回原内容：\n"
        for symbol, content in self.mapping.items():
            # 只展示开头一部分以节省空间，或者 LLM 实际上需要完整内容？
            # 这里的悖论是：如果我不把内容传给 LLM，它就不知道符号代表什么。
            # QMD 的做法通常是：在当前 Turn 中，符号代表的内容确实被省略了，
            # 但在 System Prompt 或之前的 Memory Pull 中已经加载并被“抽象”了。
            # 
            # 修正：在 Genesis 的 Triad 架构中：
            # Oracle 看到完整内容 -> 抽象为符号 -> Strategist 看到符号。
            # 所以映射表应该包含内容。
            table += f"- {symbol}: {content}\n"
        return table

    def clear(self):
        self.mapping = {}
        self.counter = 0

class ProtocolCompressionPlugin(ContextPlugin):
    """
    集成到 ContextPipeline 的压缩插件
    """
    name = "compression"
    priority = 100  # 最后运行
    
    def __init__(self, min_len: int = 300):
        self.compressor = SymbolicCompressor(min_len=min_len)
        
    def inject(self, ctx: Any) -> Optional[str]:
        # 清空上一次的映射
        self.compressor.clear()
        
        # 如果 ctx 有 raw_memory，尝试压缩它们
        if hasattr(ctx, 'raw_memory') and ctx.raw_memory:
            compressed_memories = []
            for hit in ctx.raw_memory:
                content = hit.get('content', '')
                path = hit.get('path', 'unknown')
                symbol = self.compressor.compress(content, label=path)
                compressed_memories.append(f"- {path}: {symbol}")
            
            if compressed_memories:
                mapping_table = self.compressor.get_mapping_table()
                return f"\n\n[Compressed Memory]\n" + "\n".join(compressed_memories) + "\n" + mapping_table
                
        return None
