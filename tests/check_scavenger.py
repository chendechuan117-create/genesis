import sqlite3
import pandas as pd
from pathlib import Path

db_path = Path.home() / '.nanogenesis' / 'workshop_v4.sqlite'
try:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT node_id, title, created_at, confidence_score "
        "FROM knowledge_nodes "
        "WHERE title LIKE '[拾荒]%' "
        "ORDER BY created_at DESC LIMIT 10", 
        conn
    )
    print("\n=== 最近拾荒成果 ===")
    if df.empty:
        print("暂无拾荒数据，或者刚清理过。")
    else:
        print(df.to_string(index=False))
    conn.close()
except Exception as e:
    print(f"检查失败: {e}")
