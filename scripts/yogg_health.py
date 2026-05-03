import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _default_db_paths() -> list[Path]:
    return [
        Path.home() / ".genesis" / "workshop_v4.sqlite",
        Path.home() / ".nanogenesis" / "workshop_v4.sqlite",
    ]


def _connect(path: Path):
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _tables(conn) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def _columns(conn, table: str) -> set[str]:
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.Error:
        return set()


def _rows(conn, sql: str, params=()) -> list[dict]:
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    except sqlite3.Error as exc:
        return [{"error": str(exc)}]


def _one(conn, sql: str, params=()) -> dict:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else {}


def _pick_db(explicit: str | None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.exists() else None
    for path in _default_db_paths():
        if path.exists():
            return path
    return None


def _db_metrics(path: Path, hours: int) -> dict:
    if not path or not path.exists():
        return {"available": False, "path": str(path) if path else ""}
    metrics = {"available": True, "path": str(path)}
    with _connect(path) as conn:
        tables = _tables(conn)
        metrics["tables"] = sorted(tables)
        if "knowledge_nodes" in tables:
            node_cols = _columns(conn, "knowledge_nodes")
            metrics["knowledge_node_columns"] = sorted(node_cols)
            metrics["node_types"] = _rows(
                conn,
                "SELECT type, COUNT(*) AS count FROM knowledge_nodes GROUP BY type ORDER BY count DESC",
            )
            if "created_at" in node_cols:
                metrics["recent_nodes"] = _rows(
                    conn,
                    "SELECT node_id, type, title, created_at FROM knowledge_nodes "
                    "WHERE created_at >= datetime('now', ?) ORDER BY created_at DESC LIMIT 20",
                    (f"-{hours} hours",),
                )
                metrics["recent_node_count"] = _one(
                    conn,
                    "SELECT COUNT(*) AS count FROM knowledge_nodes WHERE created_at >= datetime('now', ?)",
                    (f"-{hours} hours",),
                ).get("count", 0)
            virtual_clause = "node_id LIKE 'VIRT_%' OR title LIKE '饱和:%'"
            if "is_virtual" in node_cols:
                virtual_clause = f"COALESCE(is_virtual, 0) = 1 OR {virtual_clause}"
            metrics["virtual"] = _one(
                conn,
                f"SELECT COUNT(*) AS count, SUM(COALESCE(usage_count, 0)) AS usage_sum "
                f"FROM knowledge_nodes WHERE {virtual_clause}",
            )
        if "reasoning_lines" in tables:
            line_cols = _columns(conn, "reasoning_lines")
            metrics["reasoning_line_columns"] = sorted(line_cols)
            if {"new_point_id", "basis_point_id"}.issubset(line_cols):
                same_expr = "same_round" if "same_round" in line_cols else "0"
                metrics["reasoning_lines"] = _one(
                    conn,
                    f"SELECT COUNT(*) AS total, "
                    f"SUM(CASE WHEN {same_expr}=1 THEN 1 ELSE 0 END) AS same_round, "
                    f"SUM(CASE WHEN {same_expr}=0 OR {same_expr} IS NULL THEN 1 ELSE 0 END) AS cross_round, "
                    f"COUNT(DISTINCT new_point_id) AS new_points, "
                    f"COUNT(DISTINCT basis_point_id) AS basis_points FROM reasoning_lines",
                )
                if "created_at" in line_cols:
                    metrics["recent_reasoning_lines"] = _one(
                        conn,
                        "SELECT COUNT(*) AS count FROM reasoning_lines WHERE created_at >= datetime('now', ?)",
                        (f"-{hours} hours",),
                    ).get("count", 0)
                    if "source" in line_cols:
                        metrics["recent_reasoning_sources"] = _rows(
                            conn,
                            "SELECT source, COUNT(*) AS count FROM reasoning_lines "
                            "WHERE created_at >= datetime('now', ?) GROUP BY source ORDER BY count DESC",
                            (f"-{hours} hours",),
                        )
    return metrics


def _find_round_files(root: Path, limit: int) -> list[Path]:
    reports_dir = root / "runtime" / "auto_reports"
    if not reports_dir.exists():
        return []
    files = sorted(reports_dir.rglob("round_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        return {"_load_error": str(exc)}


def _auto_report_metrics(root: Path, limit: int) -> dict:
    files = _find_round_files(root, limit)
    metrics = {"round_files_scanned": len(files), "latest_round_file": str(files[0]) if files else ""}
    if not files:
        return metrics
    status_counts = Counter()
    progress_counts = Counter()
    event_tool_counts = Counter()
    totals = Counter()
    latest = None
    for path in files:
        data = _load_json(path)
        if latest is None:
            latest = data
        status_counts[str(data.get("status") or "unknown")] += 1
        progress_counts[str(data.get("progress_class") or "unknown")] += 1
        if data.get("outcome_detected"):
            totals["outcome_rounds"] += 1
        if data.get("kb_changed"):
            totals["kb_changed_rounds"] += 1
        if data.get("exception"):
            totals["exception_rounds"] += 1
        for event in data.get("events") or []:
            if isinstance(event, dict) and event.get("type") in ("tool_result", "search_result", "tool_start"):
                name = event.get("name")
                if name:
                    event_tool_counts[name] += 1
        pls = data.get("pls_telemetry") or {}
        if isinstance(pls, dict):
            for key, value in pls.items():
                if isinstance(value, int):
                    totals[f"pls_{key}"] += value
    metrics["status_counts"] = dict(status_counts)
    metrics["progress_counts"] = dict(progress_counts)
    metrics["top_tools"] = dict(event_tool_counts.most_common(12))
    metrics["totals"] = dict(totals)
    metrics["latest_round"] = {
        "session_id": latest.get("session_id") if latest else None,
        "round": latest.get("round") if latest else None,
        "status": latest.get("status") if latest else None,
        "progress_class": latest.get("progress_class") if latest else None,
        "activity_summary": latest.get("activity_summary") if latest else None,
        "kb_delta_summary": latest.get("kb_delta_summary") if latest else None,
        "pls_telemetry": latest.get("pls_telemetry") if latest else None,
        "exception": latest.get("exception") if latest else None,
    }
    return metrics


def _print_section(title: str):
    print(f"\n## {title}")


def _print_text(report: dict):
    _print_section("Database")
    db = report["database"]
    print(f"path: {db.get('path') or '(not found)'}")
    print(f"available: {db.get('available')}")
    if db.get("available"):
        print(f"node_types: {db.get('node_types', [])}")
        print(f"reasoning_lines: {db.get('reasoning_lines', {})}")
        print(f"recent_reasoning_lines: {db.get('recent_reasoning_lines', 0)}")
        print(f"virtual: {db.get('virtual', {})}")
        print(f"recent_node_count: {db.get('recent_node_count', 0)}")
    _print_section("Auto Reports")
    auto = report["auto_reports"]
    print(f"round_files_scanned: {auto.get('round_files_scanned', 0)}")
    print(f"latest_round_file: {auto.get('latest_round_file') or '(none)'}")
    print(f"status_counts: {auto.get('status_counts', {})}")
    print(f"progress_counts: {auto.get('progress_counts', {})}")
    print(f"top_tools: {auto.get('top_tools', {})}")
    print(f"totals: {auto.get('totals', {})}")
    print(f"latest_round: {auto.get('latest_round', {})}")


def build_report(args) -> dict:
    root = Path(args.root).expanduser().resolve() if args.root else PROJECT_ROOT
    db_path = _pick_db(args.db)
    return {
        "root": str(root),
        "database": _db_metrics(db_path, args.hours),
        "auto_reports": _auto_report_metrics(root, args.round_limit),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(PROJECT_ROOT))
    parser.add_argument("--db", default="")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--round-limit", type=int, default=200)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_report(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)


if __name__ == "__main__":
    main()
