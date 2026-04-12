import json
import logging
import numpy as np
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)

class VectorEngine:
    _instance = None
    _model = None
    _reranker = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VectorEngine, cls).__new__(cls)
            cls._instance.is_ready = False
            cls._instance.reranker_ready = False
            cls._instance.matrix = None  # np.ndarray shape (N, dim)
            cls._instance.node_ids = []  # List[str] corresponding to matrix rows
        return cls._instance

    def initialize(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        """Load the model and set readiness."""
        if self.is_ready:
            return
        
        try:
            # Only import sentence_transformers if actually used, to avoid hard crash if not installed
            from sentence_transformers import SentenceTransformer
            logger.info(f"VectorEngine: Loading embedding model {model_name}...")
            self._model = SentenceTransformer(model_name)
            self.is_ready = True
            logger.info("VectorEngine: Model loaded successfully.")
            
            # 加载 Cross-Encoder Reranker (精排模型，异步延迟加载避免阻塞启动)
            import threading
            def _load_reranker():
                try:
                    from sentence_transformers import CrossEncoder
                    reranker_name = "BAAI/bge-reranker-base"
                    logger.info(f"VectorEngine: Loading reranker model {reranker_name}...")
                    self._reranker = CrossEncoder(reranker_name)
                    self.reranker_ready = True
                    logger.info("VectorEngine: Reranker loaded successfully.")
                except Exception as e:
                    logger.warning(f"VectorEngine: Reranker not available: {e}")
                    self.reranker_ready = False
            threading.Thread(target=_load_reranker, daemon=True).start()
                
        except ImportError as e:
            logger.warning(f"VectorEngine: ImportError during model load: {e}. Vector search disabled.")
            self.is_ready = False
        except Exception as e:
            logger.error(f"VectorEngine: Failed to load model: {e}")
            self.is_ready = False

    def load_matrix(self, rows: List[Dict]):
        """
        Load existing embeddings from database rows into the numpy matrix.
        Rows should be dict-like with 'node_id' and 'embedding' (JSON string).
        """
        if not self.is_ready:
            return
        
        valid_ids = []
        valid_vecs = []
        
        for r in rows:
            if r.get('embedding'):
                try:
                    vec = json.loads(r['embedding'])
                    valid_ids.append(r['node_id'])
                    valid_vecs.append(vec)
                except Exception as e:
                    logger.warning(f"VectorEngine: Failed to parse embedding for {r['node_id']}: {e}")
        
        if valid_vecs:
            self.node_ids = valid_ids
            self.matrix = np.array(valid_vecs, dtype=np.float32)
            # Normalize the matrix for faster cosine similarity via dot product
            norms = np.linalg.norm(self.matrix, axis=1, keepdims=True)
            self.matrix = self.matrix / np.where(norms == 0, 1e-10, norms)
            logger.info(f"VectorEngine: In-memory matrix loaded with {len(valid_ids)} nodes.")
        else:
            self.matrix = None
            self.node_ids = []

    def encode(self, text: str) -> Optional[List[float]]:
        """Encode a single text string to a float list."""
        if not self.is_ready or not self._model:
            return None
        try:
            vec = self._model.encode(text, normalize_embeddings=True)
            return vec.tolist()
        except Exception as e:
            logger.error(f"VectorEngine: Encoding failed: {e}")
            return None

    def search(self, query: str, top_k: int = 5, threshold: float = 0.5) -> List[Tuple[str, float]]:
        """
        Search the in-memory matrix for the most similar nodes.
        Returns a list of (node_id, similarity_score).
        """
        if not self.is_ready or self.matrix is None or len(self.node_ids) == 0:
            return []
        
        try:
            # Query vector is already normalized by encode(normalize_embeddings=True)
            q_vec = self._model.encode(query, normalize_embeddings=True)
            # Cosine similarity via dot product (since both are normalized)
            similarities = np.dot(self.matrix, q_vec)
            
            # Get top_k indices
            if len(similarities) < top_k:
                top_k = len(similarities)
                
            # argpartition is faster than sort
            top_indices = np.argpartition(similarities, -top_k)[-top_k:]
            # sorted in descending order
            top_indices = top_indices[np.argsort(-similarities[top_indices])]
            
            results = []
            for idx in top_indices:
                score = float(similarities[idx])
                if score >= threshold:
                    results.append((self.node_ids[idx], score))
                    
            return results
        except Exception as e:
            logger.error(f"VectorEngine: Search failed: {e}")
            return []

    def rerank(self, query: str, candidates: List[Dict]) -> List[Dict]:
        """
        用 Cross-Encoder 对候选节点精排。
        candidates: [{node_id, title, tags, resolves, ...}, ...]
        返回按相关度降序排列的候选列表，附带 rerank_score。
        """
        if not self.reranker_ready or not self._reranker or not candidates:
            return candidates  # 降级：原样返回
        
        try:
            # 构建 (query, document) 对
            pairs = []
            for c in candidates:
                doc_text = f"{c.get('title', '')} {c.get('tags', '')} {c.get('resolves', '')}".strip()
                pairs.append((query, doc_text))
            
            scores = self._reranker.predict(pairs)
            
            # 附加分数并排序
            for i, c in enumerate(candidates):
                c['rerank_score'] = float(scores[i])
            
            candidates.sort(key=lambda x: x.get('rerank_score', 0), reverse=True)
            return candidates
        except Exception as e:
            logger.error(f"VectorEngine: Rerank failed: {e}")
            return candidates

    def add_to_matrix(self, node_id: str, vec: List[float]):
        """Dynamically add or update a node in the in-memory matrix."""
        if not self.is_ready:
            return
            
        vec_np = np.array(vec, dtype=np.float32)
        norm = np.linalg.norm(vec_np)
        vec_np = vec_np / (norm if norm > 0 else 1e-10)
        
        if node_id in self.node_ids:
            idx = self.node_ids.index(node_id)
            self.matrix[idx] = vec_np
        else:
            self.node_ids.append(node_id)
            if self.matrix is None:
                self.matrix = vec_np.reshape(1, -1)
            else:
                self.matrix = np.vstack([self.matrix, vec_np])

    def add_to_matrix_batch(self, items: List[Tuple[str, List[float]]]):
        """批量添加向量，一次 vstack 代替逐条 O(N²) 拷贝。"""
        if not self.is_ready or not items:
            return
        new_ids = []
        new_vecs = []
        for node_id, vec in items:
            vec_np = np.array(vec, dtype=np.float32)
            norm = np.linalg.norm(vec_np)
            vec_np = vec_np / (norm if norm > 0 else 1e-10)
            if node_id in self.node_ids:
                idx = self.node_ids.index(node_id)
                self.matrix[idx] = vec_np
            else:
                new_ids.append(node_id)
                new_vecs.append(vec_np)
        if new_vecs:
            new_matrix = np.array(new_vecs, dtype=np.float32)
            self.node_ids.extend(new_ids)
            if self.matrix is None:
                self.matrix = new_matrix
            else:
                self.matrix = np.vstack([self.matrix, new_matrix])
