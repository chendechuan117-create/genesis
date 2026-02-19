
import sqlite3
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")

db_path = Path.home() / ".nanogenesis" / "brain.sqlite"

def migrate():
    if not db_path.exists():
        logger.error(f"DB not found at {db_path}")
        return

    logger.info(f"Migrating DB at {db_path}...")
    conn = sqlite3.connect(db_path)
    try:
        # Check if table exists
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='missions';")
        if cursor.fetchone():
            logger.info("Table 'missions' already exists.")
            return

        logger.info("Creating 'missions' table...")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS missions (
                id TEXT PRIMARY KEY,
                objective TEXT NOT NULL,
                status TEXT DEFAULT 'active', -- active, paused, completed, failed
                context_snapshot TEXT, -- JSON
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
        logger.info("✅ Migration successful: 'missions' table created.")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
