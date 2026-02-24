
import sqlite3
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import datetime
import hashlib
import asyncio
from .interface import MemoryStore

logger = logging.getLogger(__name__)

class SQLiteMemoryStore(MemoryStore):
    """
    Robust SQLite-based Memory Store.
    Migrates the best parts of QmdMemory:
    - FTS5 Keyword Search
    - Vector Search (via sqlite-vec or naive fallback)
    - Async IO
    """
    
    def __init__(self, db_path: str = None, embed_model: str = "all-MiniLM-L6-v2"):
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path.home() / ".nanogenesis" / "brain.sqlite"
            
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embed_model_name = embed_model
        self.encoder = None
        
        # Initialize DB in main thread
        self._init_db()
        
    def _get_conn(self):
        """Get a new connection (Thread-safe for async executor)"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        
        # Enable Extensions
        try:
            import sqlite_vec
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
        except:
            pass
            
        return conn

    def _init_db(self):
        """Initialize Schema"""
        conn = self._get_conn()
        try:
            # 1. Content Table (Deduplicated)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS content (
                    hash TEXT PRIMARY KEY,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            
            # 2. Memory Items Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_hash TEXT NOT NULL,
                    collection TEXT DEFAULT 'general',
                    metadata TEXT,
                    created_at TEXT,
                    FOREIGN KEY (content_hash) REFERENCES content(hash)
                )
            """)
            
            # 3. FTS5 Virtual Table
            try:
                conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(body, tokenize='unicode61')")
            except:
                conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(body)")
                
            # 4. Vector Table (sqlite-vec)
            # Check for vec0 support
            try:
                conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS vectors USING vec0(hash_seq TEXT PRIMARY KEY, embedding float[384])")
            except Exception as e:
                logger.warning(f"Vector search unavailable: {e}")
                
            # 5. Triggers for FTS
            conn.execute("DROP TRIGGER IF EXISTS trg_memories_insert")
            conn.execute("""
                CREATE TRIGGER trg_memories_insert AFTER INSERT ON memories
                BEGIN
                    INSERT INTO memories_fts(rowid, body)
                    SELECT new.id, c.body FROM content c WHERE c.hash = new.content_hash;
                END
            """)
            
            # 6. Compressed Blocks Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS compressed_blocks (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    start_index INTEGER,
                    end_index INTEGER,
                    summary TEXT,
                    diff TEXT,
                    anchors TEXT,
                    raw_hash TEXT,
                    created_at TEXT
                )
            """)
            
            conn.commit()
        finally:
            conn.close()

    def _get_encoder(self):
        """Lazy load encoder — 带超时保护，防止 torch 初始化卡死"""
        if getattr(self, '_encoder_failed', False):
            return None
            
        if not self.encoder:
            import concurrent.futures
            
            def _load():
                from sentence_transformers import SentenceTransformer
                return SentenceTransformer(self.embed_model_name)
            
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(_load)
                    self.encoder = future.result(timeout=5)  # 超过 5s 视为环境不支持
            except concurrent.futures.TimeoutError:
                logger.warning(
                    f"⏱ 向量编码器加载超时 (>5s)，环境可能不支持 PyTorch，"
                    f"将使用 FTS 关键词搜索作为回退。"
                )
                self._encoder_failed = True
                return None
            except ImportError:
                self._encoder_failed = True
                return None
            except Exception as e:
                logger.warning(f"向量编码器加载失败（{e}），回退到 FTS 模式")
                self._encoder_failed = True
                return None
        return self.encoder


    async def add(self, content: str, metadata: Dict[str, Any] = None) -> None:
        """Add memory item (Async)"""
        if not content: return
        metadata = metadata or {}
        
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        now = datetime.datetime.now().isoformat()
        meta_json = json.dumps(metadata or {})
        
        def _sync_write():
            conn = self._get_conn()
            try:
                with conn:
                    # Content
                    conn.execute(
                        "INSERT OR IGNORE INTO content (hash, body, created_at) VALUES (?, ?, ?)",
                        (content_hash, content, now)
                    )
                    
                    # Memory Item
                    conn.execute(
                        "INSERT INTO memories (content_hash, collection, metadata, created_at) VALUES (?, ?, ?, ?)",
                        (content_hash, metadata.get('collection', 'general'), meta_json, now)
                    )
                    
                    # Vector (Optional)
                    encoder = self._get_encoder()
                    if encoder:
                        embedding = encoder.encode(content)
                        import numpy as np
                        vec_params = (f"{content_hash}", np.array(embedding, dtype=np.float32).tobytes())
                        try:
                            conn.execute("INSERT OR REPLACE INTO vectors (hash_seq, embedding) VALUES (?, ?)", vec_params)
                        except:
                            pass
            finally:
                conn.close()
                
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_write)

    async def search(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Hybrid Search"""
        
        def _sync_read():
            conn = self._get_conn()
            results = {} # Map content -> score
            try:
                # 1. Keyword Search (FTS)
                # Wrap query in quotes to treat as string literal (avoids "no such column" for hyphens)
                safe_query = f'"{query}"'
                cursor = conn.execute("""
                    SELECT m.id, c.body, m.metadata, -10 as rank
                    FROM memories_fts f
                    JOIN memories m ON m.id = f.rowid
                    JOIN content c ON c.hash = m.content_hash
                    WHERE memories_fts MATCH ?
                    LIMIT ?
                """, (safe_query, limit * 2))
                
                for row in cursor:
                    body = row['body']
                    meta = json.loads(row['metadata'])
                    results[body] = {'content': body, 'metadata': meta, 'score': 0.5} # Base score
                    
                # 2. Vector Search (if available)
                encoder = self._get_encoder()
                if encoder:
                    q_vec = encoder.encode(query)
                    import numpy as np
                    q_bytes = np.array(q_vec, dtype=np.float32).tobytes()
                    try:
                        v_cursor = conn.execute("""
                            SELECT hash_seq, distance 
                            FROM vectors 
                            WHERE embedding MATCH ? AND k = ?
                        """, (q_bytes, limit))
                        
                        for v_row in v_cursor:
                            c_hash = v_row['hash_seq'] # We used content_hash as hash_seq
                            m_cursor = conn.execute("""
                                SELECT c.body, m.metadata 
                                FROM content c 
                                JOIN memories m ON m.content_hash = c.hash 
                                WHERE c.hash = ?
                            """, (c_hash,))
                            m_row = m_cursor.fetchone()
                            if m_row:
                                body = m_row['body']
                                meta = json.loads(m_row['metadata'])
                                score = 1.0 - v_row['distance']
                                if body in results:
                                    results[body]['score'] = max(results[body]['score'], score)
                                else:
                                    results[body] = {'content': body, 'metadata': meta, 'score': score}
                    except:
                        pass
                        
                # Sort
                final = sorted(results.values(), key=lambda x: x['score'], reverse=True)
                return final[:limit]
            finally:
                conn.close()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_read)

    async def save_block(self, block_data: Dict[str, Any]):
        """保存压缩块"""
        def _sync_save():
            conn = self._get_conn()
            try:
                with conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO compressed_blocks 
                        (id, session_id, start_index, end_index, summary, diff, anchors, raw_hash, created_at)
                        VALUES (:id, :session_id, :start_index, :end_index, :summary, :diff, :anchors, :raw_hash, :created_at)
                    """, block_data)
            finally:
                conn.close()
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_save)

    async def get_blocks(self, session_id: str) -> List[Dict[str, Any]]:
        """获取会话的所有压缩块"""
        def _sync_get():
            conn = self._get_conn()
            try:
                cursor = conn.execute("""
                    SELECT * FROM compressed_blocks 
                    WHERE session_id = ? 
                    ORDER BY start_index ASC
                """, (session_id,))
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_get)

    def close(self):
        # Already handled by _get_conn context managers usually, 
        # but if we hold any persistent connection (we don't), close it here.
        pass
