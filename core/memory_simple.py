
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import math
from collections import Counter

logger = logging.getLogger(__name__)

class SimpleMemory:
    """
    极简本地记忆系统 (无需向量库依赖)
    """
    def __init__(self, memory_path: str = None):
        if memory_path:
            self.memory_path = Path(memory_path)
        else:
            self.memory_path = Path.home() / ".nanogenesis" / "memory.json"
        self.memories: List[Dict[str, Any]] = []
        self._load_memory()
        
    def _load_memory(self):
        if self.memory_path.exists():
            try:
                with self.memory_path.open('r', encoding='utf-8') as f:
                    self.memories = json.load(f)
            except Exception as e:
                logger.error(f"加载记忆失败: {e}")
    
    def _save_memory(self):
        try:
            self.memory_path.parent.mkdir(parents=True, exist_ok=True)
            with self.memory_path.open('w', encoding='utf-8') as f:
                json.dump(self.memories, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存记忆失败: {e}")

    def add(self, content: str, metadata: Dict[str, Any] = None):
        if not content: return
        memory_item = {"content": content, "metadata": metadata or {}}
        if not any(m['content'] == content for m in self.memories):
            self.memories.append(memory_item)
            self._save_memory()

    def _tokenize(self, text: str) -> List[str]:
        text = text.lower()
        for char in ",.!?;:\"'()[]{}<>": text = text.replace(char, " ")
        return [w for w in text.split() if len(w) > 1]

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.memories: return []
        query_tokens = self._tokenize(query)
        if not query_tokens: return []
        doc_freqs = Counter()
        for mem in self.memories:
            tokens = set(self._tokenize(mem['content']))
            for token in tokens: doc_freqs[token] += 1
        total_docs = len(self.memories)
        scores = []
        for mem in self.memories:
            mem_tokens = self._tokenize(mem['content'])
            mem_token_counts = Counter(mem_tokens)
            score = 0.0
            for q_token in query_tokens:
                if q_token in mem_token_counts:
                    tf = mem_token_counts[q_token]
                    df = doc_freqs[q_token]
                    idf = math.log(1 + total_docs / (df + 1))
                    score += tf * idf
            if score > 0:
                score = score / (len(mem_tokens) + 1)
                scores.append((score, mem))
        scores.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scores[:limit]]
