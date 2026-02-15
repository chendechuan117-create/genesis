"""
向量记忆系统 (Vector Memory)
轻量级纯 Python 实现，无需 Numpy/ChromaDB 依赖。
"""

import json
import math
import logging
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

class VectorMemory:
    """
    轻量级向量记忆库 (Zero-Dependency)
    """
    
    def __init__(self, provider=None, db_path: str = None):
        """
        初始化
        
        Args:
            provider: LLM Provider (必须支持 embed 方法)
            db_path: 数据库路径
        """
        self.provider = provider
        
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path.home() / ".nanogenesis" / "memories_vector.json"
            
        self.memories: List[Dict[str, Any]] = []
        self._load()
    
    def set_provider(self, provider):
        self.provider = provider

    def _load(self):
        """加载记忆库"""
        if not self.db_path.exists():
            return
            
        try:
            with self.db_path.open('r', encoding='utf-8') as f:
                self.memories = json.load(f)
            logger.info(f"✓ 已加载 {len(self.memories)} 条向量记忆")
        except Exception as e:
            logger.warning(f"加载记忆库失败: {e}")
            self.memories = []

    def _save(self):
        """保存记忆库"""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self.db_path.open('w', encoding='utf-8') as f:
                json.dump(self.memories, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存记忆库失败: {e}")

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        """纯 Python 余弦相似度计算"""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
            
        dot_product = sum(a * b for a, b in zip(v1, v2))
        magnitude1 = math.sqrt(sum(a * a for a in v1))
        magnitude2 = math.sqrt(sum(a * a for a in v2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
            
        return dot_product / (magnitude1 * magnitude2)

    async def add(self, content: str, metadata: Dict[str, Any] = None):
        """添加记忆"""
        if not self.provider:
            logger.warning("未配置 Provider，无法生成向量")
            return
            
        # 生成向量
        embedding = await self.provider.embed(content)
        
        memory_item = {
            "id": f"mem_{datetime.now().timestamp()}",
            "content": content,
            "embedding": embedding,
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat()
        }
        
        self.memories.append(memory_item)
        self._save()
        logger.info(f"✓ 已存储记忆 (向量维度: {len(embedding)})")

    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """语义搜索"""
        if not self.provider:
            return []
            
        # 生成查询向量
        query_embedding = await self.provider.embed(query)
        
        # 计算相似度
        scored_memories = []
        for mem in self.memories:
            # 兼容旧数据 (无 embedding)
            if "embedding" not in mem or not mem["embedding"]:
                continue
                
            score = self._cosine_similarity(query_embedding, mem["embedding"])
            scored_memories.append((score, mem))
            
        # 排序
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        
        # 返回 Top N
        results = []
        for score, mem in scored_memories[:limit]:
            # 返回副本，去掉 embedding 以减少传输量
            mem_copy = mem.copy()
            del mem_copy["embedding"]
            mem_copy["score"] = score
            results.append(mem_copy)
            
        return results

    async def delete(self, memory_id: str):
        """删除记忆"""
        self.memories = [m for m in self.memories if m["id"] != memory_id]
        self._save()
