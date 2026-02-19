
import sqlite3
from pathlib import Path

db_path = Path.home() / ".nanogenesis" / "brain.sqlite"

def check_schema():
    if not db_path.exists():
        print(f"❌ DB not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    
    print(f"📂 Default DB Path: {db_path}")
    print(f"📊 Tables found: {tables}")
    
    if "missions" in tables:
        print("✅ 'missions' table exists.")
        cursor.execute("PRAGMA table_info(missions);")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"   Columns: {columns}")
    else:
        print("❌ 'missions' table MISSING.")
        
    conn.close()

if __name__ == "__main__":
    check_schema()
