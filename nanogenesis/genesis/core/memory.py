
import sqlite3
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import datetime
import hashlib
import os

logger = logging.getLogger(__name__)

class QmdMemory:
    """
    QMD-style Memory (Quick Memory Discovery)
    
    Features:
    1. SQLite-based storage
    2. FTS5 for keyword search
    3. sqlite-vec for vector search (semantic)
    4. Content-addressable storage (hash-based)
    """
    
    def __init__(self, db_path: str = None, embed_model_name: str = "all-MiniLM-L6-v2"):
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path.home() / ".nanogenesis" / "qmd_memory.sqlite"
            
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embed_model_name = embed_model_name
        self.encoder = None  # Lazy load sentence-transformers
        
        # The user's provided "Code Edit" snippet implies moving the connection logic here.
        # I will follow the structure implied by the snippet, which moves the connection
        # and row_factory setup from _init_db to __init__, and adds check_same_thread=False.
        # The mkdir for parent is already done above, so the `if not self.db_path.exists()` block
        # from the snippet is redundant and will not be included.
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        self._init_db()
        
    def _init_db(self):
        """初始化数据库架构"""
        # The connection and row_factory setup has been moved to __init__ based on the user's snippet.
        
        # 加载 sqlite-vec 扩展
        try:
            import sqlite_vec
            self.conn.enable_load_extension(True)
            sqlite_vec.load(self.conn)
            logger.info("sqlite-vec 扩展加载成功")
        except Exception as e:
            logger.warning(f"无法加载 sqlite-vec 扩展: {e}. 将回退到仅 FTS5 搜索。")
            
        # 基础表：存储原始内容
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS content (
                hash TEXT PRIMARY KEY,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        # 索引表：文件/片段元数据
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection TEXT NOT NULL,
                path TEXT NOT NULL,
                title TEXT,
                hash TEXT NOT NULL,
                metadata TEXT,
                active INTEGER DEFAULT 1,
                FOREIGN KEY (hash) REFERENCES content(hash),
                UNIQUE(collection, path)
            )
        """)
        
        # FTS5 全文检索
        try:
            self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                    path, title, body,
                    tokenize='porter unicode61'
                )
            """)
        except sqlite3.OperationalError:
            # 有些 SQLite 不支持 porter
            self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                    path, title, body,
                    tokenize='unicode61'
                )
            """)
            
        # 向量表 (sqlite-vec)
        # 默认 all-MiniLM-L6-v2 是 384 维
        # 注意：这里我们使用 vec0
        try:
            # 检查表是否存在
            cursor = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vectors_vec'")
            if not cursor.fetchone():
                self.conn.execute("CREATE VIRTUAL TABLE vectors_vec USING vec0(hash_seq TEXT PRIMARY KEY, embedding float[384] distance_metric=cosine)")
        except Exception as e:
            logger.warning(f"创建向量表失败: {e}")
            
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS compressed_blocks (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                start_index INTEGER,
                end_index INTEGER,
                summary TEXT,
                diff TEXT,
                anchors TEXT,
                raw_hash TEXT,
                created_at TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # 触发器：自动同步 FTS
        self.conn.execute("DROP TRIGGER IF EXISTS trg_docs_insert")
        self.conn.execute("""
            CREATE TRIGGER trg_docs_insert AFTER INSERT ON documents
            BEGIN
                INSERT INTO documents_fts(rowid, path, title, body)
                SELECT new.id, new.path, new.title, c.body 
                FROM content c WHERE c.hash = new.hash;
            END
        """)
        
        self.conn.commit()

    def _get_encoder(self):
        """延迟加载 Embedding 模型"""
        if self.encoder is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"正在加载 Embedding 模型: {self.embed_model_name}...")
                self.encoder = SentenceTransformer(self.embed_model_name)
            except Exception as e:
                logger.error(f"加载 Embedding 模型失败: {e}")
                # Don't re-raise, just return None so we can degrade gracefully
                return None
        return self.encoder

    async def add(self, content: str, path: str = "general", collection: str = "default", title: str = None, metadata: Dict = None):
        """添加或更新记忆"""
        if not content:
            return
            
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        now = datetime.datetime.now().isoformat()
        meta_json = json.dumps(metadata or {})
        
        # 封装同步操作
        def _sync_add():
            with self.conn:
                # 1. 存入 content
                self.conn.execute(
                    "INSERT OR IGNORE INTO content (hash, body, created_at) VALUES (?, ?, ?)",
                    (content_hash, content, now)
                )
                
                # 2. 存入 documents
                self.conn.execute("""
                    INSERT OR REPLACE INTO documents (collection, path, title, hash, metadata, active)
                    VALUES (?, ?, ?, ?, ?, 1)
                """, (collection, path, title or path, content_hash, meta_json))
                
                # 3. 生成向量并存入向量表 (如果支持)
                try:
                    encoder = self._get_encoder()
                    if encoder:
                        embedding = encoder.encode(content)
                        import numpy as np
                        vec_data = np.array(embedding, dtype=np.float32).tobytes()
                        hash_seq = f"{content_hash}_0" 
                        self.conn.execute(
                            "INSERT OR REPLACE INTO vectors_vec (hash_seq, embedding) VALUES (?, ?)",
                            (hash_seq, vec_data)
                        )
                except Exception as e:
                    logger.debug(f"跳过向量生成: {e}")

        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_add)

    async def add_decision(self, situation: str, action: str, outcome: str, insight: str = "", cost: Dict = None):
        """
        添加决策事件 (S, A, R)
        """
        combined_content = f"S: {situation}\nA: {action}\nR: {outcome}\nInsight: {insight}"
        metadata = {
            "type": "decision",
            "situation": situation,
            "action": action,
            "outcome": outcome,
            "insight": insight,
            "cost": cost or {}
        }
        path = f"decision_{hashlib.md5(situation.encode()).hexdigest()[:8]}"
        await self.add(combined_content, path=path, collection="_decisions", metadata=metadata)
        logger.info(f"🧠 决策事件已缓存 ({outcome}): {situation[:30]}...")

    async def search(self, query: str, limit: int = 5, mode: str = "hybrid", collection: str = None) -> List[Dict[str, Any]]:
        """
        混合搜索: Keyword (FTS5) + Semantic (Vector)
        """
        def _sync_search():
            results = {}
            # ... (同步搜索逻辑保持不变)
            # 为了避免重写太多，我这里直接包装
            return self._sync_search_impl(query, limit, mode, collection)

        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_search)

    def _sync_search_impl(self, query: str, limit: int = 5, mode: str = "hybrid", collection: str = None) -> List[Dict[str, Any]]:
        results = {}
        # 1. Keyword Search
        try:
            coll_filter = f"AND d.collection = '{collection}'" if collection else ""
            cursor = self.conn.execute(f"""
                SELECT d.id, d.path, d.title, d.collection, c.body, 'keyword' as source, f.rank
                FROM documents_fts f
                JOIN documents d ON d.id = f.rowid
                JOIN content c ON c.hash = d.hash
                WHERE documents_fts MATCH ? {coll_filter}
                ORDER BY rank
                LIMIT ?
            """, (query, limit))
            for row in cursor:
                res = dict(row)
                res['score'] = 1.0 / (abs(res['rank']) + 1.1)
                res['content'] = res.get('body', '')
                results[res['path']] = res
        except Exception as e:
            logger.debug(f"FTS 搜索失败: {e}")

        # 2. Vector Search
        if mode in ["hybrid", "vector"]:
            try:
                encoder = self._get_encoder()
                if not encoder: return list(results.values())[:limit]
                query_vec = encoder.encode(query)
                import numpy as np
                query_bytes = np.array(query_vec, dtype=np.float32).tobytes()
                
                cursor = self.conn.execute("""
                    SELECT hash_seq, distance 
                    FROM vectors_vec 
                    WHERE embedding MATCH ? 
                    AND k = ?
                """, (query_bytes, limit * 2))
                
                for row in cursor:
                    hash_val = row['hash_seq'].split('_')[0]
                    coll_filter = f"AND d.collection = '{collection}'" if collection else ""
                    doc_cursor = self.conn.execute(f"""
                        SELECT d.path, d.title, d.collection, c.body, 'vector' as source, d.metadata
                        FROM documents d
                        JOIN content c ON c.hash = d.hash
                        WHERE d.hash = ? AND d.active = 1 {coll_filter}
                    """, (hash_val,))
                    doc_row = doc_cursor.fetchone()
                    if doc_row:
                        res = dict(doc_row)
                        res['score'] = 1.0 - row['distance']
                        res['content'] = res.get('body', '')
                        path = res['path']
                        if path not in results or res['score'] > results[path]['score']:
                            results[path] = res
            except Exception as e:
                logger.debug(f"Vector 搜索失败: {e}")

        sorted_results = sorted(results.values(), key=lambda x: x['score'], reverse=True)
        return sorted_results[:limit]

    async def save_block(self, block_data: Dict[str, Any]):
        """保存压缩块"""
        def _sync_save():
            with self.conn:
                self.conn.execute("""
                    INSERT OR REPLACE INTO compressed_blocks 
                    (id, session_id, start_index, end_index, summary, diff, anchors, raw_hash, created_at)
                    VALUES (:id, :session_id, :start_index, :end_index, :summary, :diff, :anchors, :raw_hash, :created_at)
                """, block_data)
        
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_save)

    async def get_blocks(self, session_id: str) -> List[Dict[str, Any]]:
        """获取会话的所有压缩块"""
        def _sync_get():
            cursor = self.conn.execute("""
                SELECT * FROM compressed_blocks 
                WHERE session_id = ? 
                ORDER BY start_index ASC
            """, (session_id,))
            return [dict(row) for row in cursor.fetchall()]

        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_get)

    def close(self):
        self.conn.close()

class SimpleMemory:
    """保留旧的 SimpleMemory 以向下兼容"""
    def __init__(self, memory_path: str = None):
        from .memory_simple import SimpleMemory as OriginalSimpleMemory
        self._impl = OriginalSimpleMemory(memory_path)
    def add(self, content, metadata=None): self._impl.add(content, metadata)
    def search(self, query, limit=5): return self._impl.search(query, limit)
