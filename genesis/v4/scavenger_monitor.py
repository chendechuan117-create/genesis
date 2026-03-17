import sqlite3
import pandas as pd
from pathlib import Path
from genesis.core.config import ConfigManager

def get_stats():
    db_path = Path.home() / '.nanogenesis' / 'workshop_v4.sqlite'
    conn = sqlite3.connect(db_path)
    
    # 获取总战利品数
    total = conn.execute("SELECT COUNT(*) FROM knowledge_nodes WHERE title LIKE '[拾荒]%'").fetchone()[0]
    
    # 获取已经转正的战利品（分数>=0.8）
    promoted = conn.execute("SELECT COUNT(*) FROM knowledge_nodes WHERE verification_source LIKE 'scavenger%' AND confidence_score >= 0.8").fetchone()[0]
    
    # 获取最近5个
    df = pd.read_sql_query(
        "SELECT node_id, title, confidence_score "
        "FROM knowledge_nodes "
        "WHERE title LIKE '[拾荒]%' OR verification_source LIKE 'scavenger%' "
        "ORDER BY created_at DESC LIMIT 5", 
        conn
    )
    conn.close()
    
    config = ConfigManager().config
    
    print("\n" + "="*40)
    print("🎒 拾荒者 (Scavenger) 运行报告")
    print("="*40)
    print(f"📊 累计带回知识: {total} 条")
    print(f"🌟 已被你使用并转正: {promoted} 条")
    print(f"⛽ 当前主要耗材: DashScope (免费额度) / SiliconFlow (免费额度)")
    
    if config.dashscope_api_key:
        print(f"   [√] DashScope API 已配置")
    if config.siliconflow_api_key:
        print(f"   [√] SiliconFlow API 已配置")
        
    print("-" * 40)
    print("📋 最近 5 条收获:")
    if df.empty:
        print("暂无数据。")
    else:
        for _, row in df.iterrows():
            status = "🟩 已转正" if row['confidence_score'] >= 0.8 else "🟨 待检验"
            print(f"[{status}] {row['title']} (Score: {row['confidence_score']})")
    print("="*40 + "\n")

if __name__ == "__main__":
    get_stats()
