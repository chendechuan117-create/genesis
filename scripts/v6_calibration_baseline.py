"""
V6 Shadow Calibration — 基线建立脚本

在 V6 模型就绪前，先建立评估框架和简单基线。
当前阶段: shadow_only, no routing, no filtering, no prompt injection.

基线类型:
- frequency_baseline: 最常见工具路径的预测准确率
- recent_success_baseline: 最近成功路径的召回率
- pls_only_baseline: 仅靠 PLS terrain 的决策质量

输出: 打印基线指标，供未来 V6 模型对比。
"""

import sqlite3
import json
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

TRACES_DB = Path(__file__).resolve().parent.parent.parent / "runtime" / "traces.db"
ENTITY_DB = Path(__file__).resolve().parent.parent.parent / "runtime" / "trace_entities.db"


def _connect(db_path: Path) -> sqlite3.Connection | None:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path), timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def compute_frequency_baseline(conn: sqlite3.Connection, top_n: int = 10) -> dict:
    """最常见工具序列的频次基线。"""
    rows = conn.execute("""
        SELECT s.trace_id, s.tool_name, s.started_at
        FROM spans s
        WHERE s.span_type = 'tool_call'
        ORDER BY s.trace_id, s.started_at
    """).fetchall()

    # Group tool sequences by trace
    traces: dict[str, list[str]] = {}
    for r in rows:
        traces.setdefault(r["trace_id"], []).append(r["tool_name"])

    # Count tool bigrams (tool_i -> tool_{i+1})
    bigram_counter: Counter = Counter()
    tool_counter: Counter = Counter()
    for seq in traces.values():
        for i, tool in enumerate(seq):
            tool_counter[tool] += 1
            if i + 1 < len(seq):
                bigram_counter[(tool, seq[i + 1])] += 1

    top_tools = tool_counter.most_common(top_n)
    top_bigrams = bigram_counter.most_common(top_n)

    return {
        "total_traces": len(traces),
        "total_tool_calls": sum(tool_counter.values()),
        "unique_tools": len(tool_counter),
        "top_tools": [(t, c) for t, c in top_tools],
        "top_bigrams": [(f"{a}->{b}", c) for (a, b), c in top_bigrams],
    }


def compute_recent_success_baseline(conn: sqlite3.Connection, window_days: int = 7) -> dict:
    """最近 N 天的成功工具调用模式。"""
    rows = conn.execute("""
        SELECT s.tool_name, s.status, s.started_at
        FROM spans s
        WHERE s.span_type = 'tool_call'
          AND s.started_at > ?
        ORDER BY s.started_at DESC
    """, (datetime.now(timezone.utc).timestamp() - window_days * 86400,)).fetchall()

    if not rows:
        return {"note": "no recent data", "window_days": window_days}

    success_count: Counter = Counter()
    fail_count: Counter = Counter()
    for r in rows:
        status = (r["status"] or "").lower()
        if status in ("ok", "success"):
            success_count[r["tool_name"]] += 1
        else:
            fail_count[r["tool_name"]] += 1

    tool_rates = {}
    for tool in set(list(success_count.keys()) + list(fail_count.keys())):
        s = success_count.get(tool, 0)
        f = fail_count.get(tool, 0)
        total = s + f
        tool_rates[tool] = {
            "success": s, "fail": f, "total": total,
            "rate": round(s / total, 3) if total > 0 else 0,
        }

    return {
        "window_days": window_days,
        "total_calls": len(rows),
        "tool_success_rates": dict(sorted(tool_rates.items(), key=lambda x: -x[1]["total"])[:10]),
    }


def compute_entity_density(conn: sqlite3.Connection) -> dict:
    """Trace entity 密度（知识结晶化程度）。"""
    if not conn:
        return {"note": "trace_entities.db not found"}
    canonical = conn.execute("SELECT COUNT(*) as cnt FROM canonical_entities").fetchone()
    occurrences = conn.execute("SELECT COUNT(*) as cnt FROM entity_occurrences").fetchone()
    communities = conn.execute("SELECT COUNT(*) as cnt FROM communities").fetchone()
    return {
        "canonical_entities": canonical["cnt"] if canonical else 0,
        "total_occurrences": occurrences["cnt"] if occurrences else 0,
        "communities": communities["cnt"] if communities else 0,
    }


def main():
    print("=" * 50)
    print("V6 Shadow Calibration Baseline")
    print(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 50)

    traces_conn = _connect(TRACES_DB)
    entity_conn = _connect(ENTITY_DB)

    if traces_conn:
        print("\n--- Frequency Baseline ---")
        freq = compute_frequency_baseline(traces_conn)
        print(json.dumps(freq, indent=2, ensure_ascii=False))

        print("\n--- Recent Success Baseline ---")
        recent = compute_recent_success_baseline(traces_conn)
        print(json.dumps(recent, indent=2, ensure_ascii=False))
    else:
        print("\n[SKIP] traces.db not found — no trace data to calibrate against")

    if entity_conn:
        print("\n--- Entity Density ---")
        density = compute_entity_density(entity_conn)
        print(json.dumps(density, indent=2, ensure_ascii=False))

    if traces_conn:
        traces_conn.close()
    if entity_conn:
        entity_conn.close()

    print("\n--- Evaluation Criteria for V6 ---")
    print("V6 model should outperform these baselines on:")
    print("  1. Tool path prediction: accuracy > frequency_baseline top-1 rate")
    print("  2. Stale action detection: recall > 0.5 on repeated-action patterns")
    print("  3. Task type classification: F1 > PLS-only terrain signals")
    print("  4. Must NOT reduce task diversity (measured by unique tool bigrams)")
    print("  5. Must NOT increase self-reference repetition rate")


if __name__ == "__main__":
    main()
