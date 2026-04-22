#!/usr/bin/env python3
"""V2 元信息系统观测脚本 — 每15分钟检查 GP 是否调了 record_point/record_line

用法:
  单次:   python3 scripts/v2_watch.py
  循环:   python3 scripts/v2_watch.py --loop 900   # 每900秒(15分钟)
  远程:   ssh yoga@100.74.123.18 "cd ~/Genesis && python3 scripts/v2_watch.py"
"""

import sqlite3
import sys
import time
import os
from datetime import datetime, timedelta

DB_PATH = os.path.expanduser("~/.genesis/workshop_v4.sqlite")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def v2_status():
    """核心观测：V2 工具使用情况"""
    conn = get_conn()
    now = datetime.utcnow()
    
    # ── 1. POINT 节点统计 ──
    total_points = conn.execute(
        "SELECT COUNT(*) FROM knowledge_nodes WHERE type = 'POINT'"
    ).fetchone()[0]
    
    recent_points = conn.execute(
        "SELECT COUNT(*) FROM knowledge_nodes WHERE type = 'POINT' AND created_at > ?",
        ((now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"),)
    ).fetchone()[0]
    
    # ── 2. 线统计（按 source 分） ──
    gp_lines = conn.execute(
        "SELECT COUNT(*) FROM reasoning_lines WHERE source = 'GP'"
    ).fetchone()[0]
    
    c_lines = conn.execute(
        "SELECT COUNT(*) FROM reasoning_lines WHERE source = 'C'"
    ).fetchone()[0]
    
    total_lines = conn.execute("SELECT COUNT(*) FROM reasoning_lines").fetchone()[0]
    untagged = total_lines - gp_lines - c_lines
    
    recent_gp_lines = conn.execute(
        "SELECT COUNT(*) FROM reasoning_lines WHERE source = 'GP' AND created_at > ?",
        ((now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),)
    ).fetchone()[0]
    
    # ── 3. INSIGHT_ 虚拟标记 ──
    insight_lines = conn.execute(
        "SELECT COUNT(*) FROM reasoning_lines WHERE new_point_id LIKE 'INSIGHT_%'"
    ).fetchone()[0]
    
    # ── 4. 最近5条 GP 线 ──
    recent_lines = conn.execute(
        "SELECT line_id, new_point_id, basis_point_id, reasoning, created_at "
        "FROM reasoning_lines WHERE source = 'GP' ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    
    # ── 5. 最近5个 POINT ──
    recent_pts = conn.execute(
        "SELECT node_id, title, created_at FROM knowledge_nodes "
        "WHERE type = 'POINT' ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    
    # ── 6. 入线数 TOP 5（价值信号） ──
    top_incoming = conn.execute(
        "SELECT basis_point_id, COUNT(*) as cnt FROM reasoning_lines "
        "GROUP BY basis_point_id ORDER BY cnt DESC LIMIT 5"
    ).fetchall()
    
    conn.close()
    
    # ── 输出 ──
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n{'='*60}")
    print(f"  V2 观测 @ {ts}")
    print(f"{'='*60}")
    
    # 核心指标
    print(f"\n📊 核心指标")
    print(f"  POINT 节点: {total_points} (近1h: +{recent_points})")
    print(f"  GP 线: {gp_lines} (近1h: +{recent_gp_lines})  |  C 线: {c_lines}  |  未标记: {untagged}")
    print(f"  INSIGHT_ 虚拟标记: {insight_lines}")
    
    # 判定
    if gp_lines > 0:
        print(f"\n✅ GP 已连线！record_line 被主动调用了 {gp_lines} 次")
    else:
        print(f"\n❌ GP 尚未连线 — record_line 还没被 GP 主动调用")
    
    if total_points > 0:
        print(f"✅ POINT 节点已存在 — record_point 被调用了 {total_points} 次")
    else:
        print(f"❌ 无 POINT 节点 — record_point 还没被调用")
    
    # 最近 GP 线
    if recent_lines:
        print(f"\n🔗 最近 GP 线:")
        for r in recent_lines:
            print(f"  {r['line_id']}: {r['new_point_id'][:20]} ← {r['basis_point_id'][:20]} | {r['reasoning'][:50]}")
    
    # 最近 POINT
    if recent_pts:
        print(f"\n📝 最近 POINT:")
        for r in recent_pts:
            print(f"  {r['node_id']}: {r['title'][:60]}")
    
    # 入线数 TOP
    if top_incoming:
        print(f"\n🏆 入线数 TOP5 (价值信号):")
        for r in top_incoming:
            print(f"  {r['basis_point_id']}: {r['cnt']} 入线")
    
    print(f"{'='*60}\n")
    
    return gp_lines > 0 or total_points > 0

if __name__ == "__main__":
    loop_interval = 0
    if len(sys.argv) > 1 and sys.argv[1] == "--loop":
        loop_interval = int(sys.argv[2]) if len(sys.argv) > 2 else 900
    
    if loop_interval > 0:
        print(f"循环观测模式: 每 {loop_interval}s 检查一次 (Ctrl+C 退出)")
        while True:
            v2_status()
            time.sleep(loop_interval)
    else:
        v2_status()
