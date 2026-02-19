#!/usr/bin/env python3
"""
Genesis Memory Migration Script
Migrates data from legacy `qmd_memory.sqlite` to `brain.sqlite`.
"""

import sqlite3
import json
import logging
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from genesis.memory import SQLiteMemoryStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Migration")

def migrate():
    home = Path.home() / ".nanogenesis"
    old_db_path = home / "qmd_memory.sqlite"
    new_db_path = home / "brain.sqlite"
    
    if not old_db_path.exists():
        logger.error(f"❌ Legacy database found at {old_db_path}")
        return

    logger.info(f"🔄 Migrating from {old_db_path} to {new_db_path}...")
    
    # Connect to Old DB
    old_conn = sqlite3.connect(old_db_path)
    old_conn.row_factory = sqlite3.Row
    
    # Initialize New Store (creates updated schema)
    store = SQLiteMemoryStore(str(new_db_path))
    new_conn = store._get_conn()
    
    try:
        # 1. Migrate Content (Deduplicated Body)
        logger.info("📦 Migrating Content...")
        cursor = old_conn.execute("SELECT hash, body, created_at FROM content")
        count = 0
        with new_conn:
            for row in cursor:
                new_conn.execute(
                    "INSERT OR IGNORE INTO content (hash, body, created_at) VALUES (?, ?, ?)",
                    (row['hash'], row['body'], row['created_at'])
                )
                count += 1
        logger.info(f"✓ Migrated {count} content blocks.")

        # 2. Migrate Documents -> Memories
        logger.info("🧠 Migrating Memories...")
        cursor = old_conn.execute("SELECT hash, metadata FROM documents") # 'path' and 'title' are in metadata now? check schema
        # Legacy schema had 'path', 'title', 'collection' separate. We should merge them into metadata.
        
        # Re-query with full fields
        cursor = old_conn.execute("SELECT hash, collection, path, title, metadata, active FROM documents")
        
        mem_count = 0
        with new_conn:
            for row in cursor:
                # Merge legacy fields into metadata
                try:
                    meta = json.loads(row['metadata']) if row['metadata'] else {}
                except:
                    meta = {}
                
                meta['source_path'] = row['path']
                meta['title'] = row['title']
                meta['legacy_collection'] = row['collection']
                
                # Insert into new memories table
                # content_hash, collection, metadata, created_at
                new_conn.execute(
                    """
                    INSERT INTO memories (content_hash, collection, metadata, created_at)
                    VALUES (?, ?, ?, datetime('now'))
                    """,
                    (row['hash'], row['collection'], json.dumps(meta))
                )
                mem_count += 1
        logger.info(f"✓ Migrated {mem_count} memory items.")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        old_conn.close()
        new_conn.close()
        
    logger.info("✨ Migration Complete.")

if __name__ == "__main__":
    migrate()
