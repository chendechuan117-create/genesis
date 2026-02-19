
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

    logger.info(f"Migrating DB at {db_path} for Circuit Breaker...")
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        # Check if columns exist
        cursor.execute("PRAGMA table_info(missions);")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "error_count" not in columns:
            logger.info("Adding 'error_count' column...")
            conn.execute("ALTER TABLE missions ADD COLUMN error_count INTEGER DEFAULT 0")
        else:
            logger.info("'error_count' already exists.")
            
        if "last_error" not in columns:
            logger.info("Adding 'last_error' column...")
            conn.execute("ALTER TABLE missions ADD COLUMN last_error TEXT")
        else:
            logger.info("'last_error' already exists.")

        conn.commit()
        logger.info("✅ Migration successful: Circuit Breaker columns added.")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
