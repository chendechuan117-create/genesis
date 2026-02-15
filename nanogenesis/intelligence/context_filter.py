"""
上下文筛选器 (Context Filter)
使用本地 LLM 智能筛选记忆，防止上下文爆炸。
"""

import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ContextFilter:
    """
    上下文筛选器
    """
    
    def __init__(self, provider):
        self.provider = provider
        
    async def filter(self, query: str, memories: List[Dict[str, Any]], max_keep: int = 5) -> List[Dict[str, Any]]:
        """
        筛选相关记忆
        
        Args:
            query: 用户问题
            memories: 候选记忆列表
            max_keep: 最大保留数量
            
        Returns:
            筛选后的记忆列表
        """
        if not memories:
            return []
            
        if not self.provider or not self.provider.available:
            # 降级：直接返回前 N 个
            return memories[:max_keep]
            
        try:
            # 构建 Prompt
            memory_list_str = ""
            for i, m in enumerate(memories):
                preview = m['content'][:200].replace('\n', ' ')
                memory_list_str += f"{i}. {preview}\n"
                
            prompt = f"""
            任务：【去粗求精】筛选与用户问题在**语义和领域**上高度相关的记忆。
            
            用户问题："{query}"
            
            筛选标准：
            1. **领域一致性**：严禁跨领域匹配。例如，如果问题是关于编程的，必须剔除关于生活、苹果、做饭的记忆。
            2. **必要性**：只保留对解决当前问题**不可或缺**的信息。
            3. **宁缺毋滥**：如果没有相关的，返回空，不要凑数。
            
            候选记忆：
            {memory_list_str}
            
            请从上述列表中选出最核心的记忆 ID（数字）。
            只返回数字列表，用逗号分隔（例如：0, 2）。
            严禁返回无关 ID。
            """
            
            messages = [{"role": "user", "content": prompt}]
            response = await self.provider.chat(messages)
            content = response.content.strip()
            
            # 解析结果
            selected_indices = []
            for part in content.split(','):
                try:
                    idx = int(part.strip())
                    if 0 <= idx < len(memories):
                        selected_indices.append(idx)
                except ValueError:
                    continue
            
            # 过滤
            filtered = [memories[i] for i in selected_indices]
            
            logger.info(f"🧠 本地筛选：从 {len(memories)} 条中保留了 {len(filtered)} 条")
            return filtered
            
        except Exception as e:
            logger.warning(f"本地筛选失败，降级处理: {e}")
            return memories[:max_keep]
