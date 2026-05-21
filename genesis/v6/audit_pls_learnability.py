from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from genesis.v4.signature_constants import METADATA_SIGNATURE_FIELDS
except Exception:
    METADATA_SIGNATURE_FIELDS = [
        "os_family",
        "runtime",
        "language",
        "framework",
        "task_kind",
        "target_kind",
        "error_kind",
        "environment_scope",
        "validation_status",
        "knowledge_state",
        "invalidation_reason",
        "valid_from",
        "valid_until",
    ]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_NODEVAULT_DB = Path.home() / ".nanogenesis" / "workshop_v4.sqlite"
DEFAULT_TRACES_DB = PROJECT_ROOT / "runtime" / "traces.db"
CORE_LABEL_FIELDS = [
    field for field in METADATA_SIGNATURE_FIELDS
    if field not in {"valid_from", "valid_until"}
]


class AuditError(RuntimeError):
    pass


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise AuditError(f"database not found: {path}")
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        return column in {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    except Exception:
        return False


def scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int | float | str | None:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    return row[0]


def safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return float(numerator) / float(denominator)


def parse_json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def normalize_values(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    normalized = []
    for item in values:
        text = str(item).strip().lower()
        if text and text not in {"none", "null", "[]", "{}"}:
            normalized.append(text)
    return normalized


def top_items(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def label_group_stats(name: str, counter: Counter[str], min_count: int) -> dict[str, Any]:
    total = sum(counter.values())
    top_value = None
    top_count = 0
    if counter:
        top_value, top_count = counter.most_common(1)[0]
    stable_classes = sum(1 for count in counter.values() if count >= min_count)
    return {
        "name": name,
        "total": total,
        "classes": len(counter),
        "stable_classes": stable_classes,
        "dominant_value": top_value,
        "dominant_count": top_count,
        "dominant_ratio": safe_ratio(top_count, total),
        "frequency_baseline_accuracy": safe_ratio(top_count, total),
    }


def classify_error_kind(error: str, result_preview: str = "") -> str:
    text = f"{error or ''}\n{result_preview or ''}".lower()
    if not text.strip():
        return "none"
    permission_markers = [
        "permission denied", "eacces", "operation not permitted", "forbidden",
        "unauthorized", "not authorized", "access denied",
    ]
    dependency_markers = [
        "no module named", "modulenotfounderror", "importerror", "cannot import",
        "command not found", "executable file not found", "missing dependency",
    ]
    timeout_markers = ["timeout", "timed out", "deadline exceeded"]
    network_markers = [
        "connection refused", "connection reset", "connection aborted", "dns",
        "network", "proxy", "ssl", "tls", "http 502", "http 503", "http 504",
        "rate limit", "too many requests",
    ]
    syntax_markers = [
        "syntaxerror", "invalid syntax", "indentationerror", "parse error",
        "unterminated string",
    ]
    oom_markers = ["out of memory", "memoryerror", "cannot allocate memory", "killed"]
    groups = [
        ("permission", permission_markers),
        ("missing_dependency", dependency_markers),
        ("timeout", timeout_markers),
        ("network", network_markers),
        ("syntax", syntax_markers),
        ("oom", oom_markers),
    ]
    for kind, markers in groups:
        if any(marker in text for marker in markers):
            return kind
    return "unknown"


def inspect_embedding_dimensions(conn: sqlite3.Connection, sample_limit: int) -> dict[str, Any]:
    dimensions = Counter()
    malformed = 0
    sampled = 0
    if not column_exists(conn, "knowledge_nodes", "embedding"):
        return {"sampled": 0, "malformed": 0, "dimensions": [], "consensus_dimension": None}
    rows = conn.execute(
        """
        SELECT embedding FROM knowledge_nodes
        WHERE node_id NOT LIKE 'MEM_CONV%'
          AND embedding IS NOT NULL
          AND TRIM(embedding) != ''
        LIMIT ?
        """,
        (sample_limit,),
    ).fetchall()
    for row in rows:
        sampled += 1
        try:
            vector = json.loads(row["embedding"])
            if isinstance(vector, list):
                dimensions[str(len(vector))] += 1
            else:
                malformed += 1
        except Exception:
            malformed += 1
    consensus = None
    if dimensions:
        consensus = int(dimensions.most_common(1)[0][0])
    return {
        "sampled": sampled,
        "malformed": malformed,
        "dimensions": top_items(dimensions, 10),
        "consensus_dimension": consensus,
    }


def audit_nodevault(path: Path, value_limit: int, embedding_sample_limit: int, min_label_count: int) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "available": False, "error": None}
    try:
        conn = connect_readonly(path)
    except AuditError as exc:
        result["error"] = str(exc)
        return result
    try:
        if not table_exists(conn, "knowledge_nodes"):
            result["error"] = "knowledge_nodes table not found"
            return result
        result["available"] = True
        total_nodes = scalar(conn, "SELECT COUNT(*) FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%'") or 0
        active_nodes = total_nodes
        if column_exists(conn, "knowledge_nodes", "is_virtual") and column_exists(conn, "knowledge_nodes", "ablation_active"):
            active_nodes = scalar(
                conn,
                """
                SELECT COUNT(*) FROM knowledge_nodes
                WHERE node_id NOT LIKE 'MEM_CONV%'
                  AND COALESCE(is_virtual, 0) = 0
                  AND COALESCE(ablation_active, 0) = 0
                """,
            ) or 0
        signature_rows = conn.execute(
            """
            SELECT node_id, type, title, tags, resolves, metadata_signature,
                   embedding, usage_count, usage_success_count, usage_fail_count,
                   confidence_score, verification_source, trust_tier
            FROM knowledge_nodes
            WHERE node_id NOT LIKE 'MEM_CONV%'
            """
        ).fetchall()
        type_counter = Counter()
        trust_counter = Counter()
        field_counters: dict[str, Counter[str]] = defaultdict(Counter)
        parsed_signatures = 0
        malformed_signatures = 0
        nonempty_signatures = 0
        embedding_count = 0
        usage_feedback_count = 0
        human_or_validated = 0
        for row in signature_rows:
            type_counter[str(row["type"] or "unknown")] += 1
            trust_counter[str(row["trust_tier"] or "unknown")] += 1
            if row["embedding"]:
                embedding_count += 1
            usage_total = int(row["usage_count"] or 0) + int(row["usage_success_count"] or 0) + int(row["usage_fail_count"] or 0)
            if usage_total > 0:
                usage_feedback_count += 1
            sig_raw = row["metadata_signature"]
            if isinstance(sig_raw, str) and sig_raw.strip() and sig_raw.strip() != "{}":
                nonempty_signatures += 1
                sig = parse_json_object(sig_raw)
                if sig is None:
                    malformed_signatures += 1
                    continue
                parsed_signatures += 1
                trust = str(row["trust_tier"] or "").upper()
                validation_values = normalize_values(sig.get("validation_status"))
                if trust == "HUMAN" or "validated" in validation_values:
                    human_or_validated += 1
                for field in CORE_LABEL_FIELDS:
                    for value in normalize_values(sig.get(field)):
                        field_counters[field][value] += 1
        label_groups = [
            label_group_stats(f"signature.{field}", counter, min_label_count)
            for field, counter in sorted(field_counters.items())
            if counter
        ]
        result.update({
            "counts": {
                "total_nodes": total_nodes,
                "active_nodes": active_nodes,
                "embedding_nodes": embedding_count,
                "nonempty_signature_nodes": nonempty_signatures,
                "parsed_signature_nodes": parsed_signatures,
                "malformed_signature_nodes": malformed_signatures,
                "usage_feedback_nodes": usage_feedback_count,
                "human_or_validated_signature_nodes": human_or_validated,
            },
            "rates": {
                "embedding_coverage": safe_ratio(embedding_count, total_nodes),
                "signature_coverage": safe_ratio(nonempty_signatures, total_nodes),
                "signature_usable_rate": safe_ratio(parsed_signatures, total_nodes),
                "signature_parse_rate_among_nonempty": safe_ratio(parsed_signatures, nonempty_signatures),
                "usage_feedback_coverage": safe_ratio(usage_feedback_count, total_nodes),
            },
            "type_distribution": top_items(type_counter, value_limit),
            "trust_tier_distribution": top_items(trust_counter, value_limit),
            "signature_value_distribution": {
                field: top_items(counter, value_limit)
                for field, counter in sorted(field_counters.items())
            },
            "label_groups": label_groups,
            "embedding_dimensions": inspect_embedding_dimensions(conn, embedding_sample_limit),
        })
        return result
    finally:
        conn.close()


def audit_traces(path: Path, value_limit: int, min_label_count: int) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "available": False, "error": None}
    try:
        conn = connect_readonly(path)
    except AuditError as exc:
        result["error"] = str(exc)
        return result
    try:
        if not table_exists(conn, "traces") or not table_exists(conn, "spans"):
            result["error"] = "traces/spans tables not found"
            return result
        result["available"] = True
        trace_total = scalar(conn, "SELECT COUNT(*) FROM traces") or 0
        trace_status_counter = Counter({
            str(row["status"] or "unknown"): int(row["c"])
            for row in conn.execute("SELECT status, COUNT(*) c FROM traces GROUP BY status")
        })
        spans_total = scalar(conn, "SELECT COUNT(*) FROM spans") or 0
        span_type_counter = Counter({
            str(row["span_type"] or "unknown"): int(row["c"])
            for row in conn.execute("SELECT span_type, COUNT(*) c FROM spans GROUP BY span_type")
        })
        tool_rows = conn.execute(
            """
            SELECT s.trace_id, s.tool_name, s.status, s.error, s.tool_result_preview,
                   s.duration_ms, t.user_input, t.status AS trace_status
            FROM spans s
            LEFT JOIN traces t ON t.trace_id = s.trace_id
            WHERE s.span_type = 'tool_call'
            """
        ).fetchall()
        tool_counter = Counter()
        error_kind_counter = Counter()
        empty_tool_name = 0
        error_span_count = 0
        trace_ids_with_user_and_tool = set()
        slow_tool_spans = 0
        durations = []
        for row in tool_rows:
            tool_name = str(row["tool_name"] or "").strip()
            if tool_name:
                tool_counter[tool_name] += 1
                if str(row["user_input"] or "").strip():
                    trace_ids_with_user_and_tool.add(row["trace_id"])
            else:
                empty_tool_name += 1
            if row["duration_ms"] is not None:
                duration = float(row["duration_ms"])
                durations.append(duration)
                if duration >= 5000:
                    slow_tool_spans += 1
            if row["error"]:
                error_span_count += 1
                error_kind_counter[classify_error_kind(row["error"], row["tool_result_preview"] or "")] += 1
        tool_label_group = label_group_stats("tool.name", tool_counter, min_label_count)
        error_label_group = label_group_stats("tool.error_kind", error_kind_counter, min_label_count)
        duration_summary = {}
        if durations:
            sorted_durations = sorted(durations)
            duration_summary = {
                "min_ms": sorted_durations[0],
                "p50_ms": sorted_durations[len(sorted_durations) // 2],
                "p95_ms": sorted_durations[int((len(sorted_durations) - 1) * 0.95)],
                "max_ms": sorted_durations[-1],
            }
        result.update({
            "counts": {
                "total_traces": trace_total,
                "total_spans": spans_total,
                "tool_call_spans": len(tool_rows),
                "nonempty_tool_call_spans": len(tool_rows) - empty_tool_name,
                "empty_tool_name_spans": empty_tool_name,
                "error_tool_spans": error_span_count,
                "slow_tool_spans_ge_5s": slow_tool_spans,
                "traces_with_user_input_and_tool": len(trace_ids_with_user_and_tool),
            },
            "rates": {
                "tool_label_nonempty_rate": safe_ratio(len(tool_rows) - empty_tool_name, len(tool_rows)),
                "tool_error_rate": safe_ratio(error_span_count, len(tool_rows)),
                "error_kind_unknown_rate": safe_ratio(error_kind_counter.get("unknown", 0), error_span_count),
                "slow_tool_span_rate_ge_5s": safe_ratio(slow_tool_spans, len(tool_rows)),
            },
            "trace_status_distribution": top_items(trace_status_counter, value_limit),
            "span_type_distribution": top_items(span_type_counter, value_limit),
            "tool_distribution": top_items(tool_counter, value_limit),
            "error_kind_distribution": top_items(error_kind_counter, value_limit),
            "duration_summary": duration_summary,
            "label_groups": [tool_label_group, error_label_group],
        })
        return result
    finally:
        conn.close()


def best_label_group(groups: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not groups:
        return None
    eligible = [group for group in groups if group["stable_classes"] >= 3]
    if eligible:
        return sorted(eligible, key=lambda group: (group["dominant_ratio"], -group["total"]))[0]
    return sorted(groups, key=lambda group: (-group["stable_classes"], group["dominant_ratio"]))[0]


def evaluate_gates(nodevault: dict[str, Any], traces: dict[str, Any], min_samples: int, min_label_count: int) -> dict[str, Any]:
    groups = []
    if nodevault.get("available"):
        groups.extend(nodevault.get("label_groups", []))
    if traces.get("available"):
        groups.extend(traces.get("label_groups", []))
    best_group = best_label_group(groups)
    node_counts = nodevault.get("counts", {}) if nodevault.get("available") else {}
    trace_counts = traces.get("counts", {}) if traces.get("available") else {}
    node_rates = nodevault.get("rates", {}) if nodevault.get("available") else {}
    trace_rates = traces.get("rates", {}) if traces.get("available") else {}
    signature_samples = int(node_counts.get("parsed_signature_nodes", 0))
    tool_samples = int(trace_counts.get("traces_with_user_input_and_tool", 0))
    trainable_units = signature_samples + tool_samples
    embedding_dim = None
    if nodevault.get("available"):
        embedding_dim = nodevault.get("embedding_dimensions", {}).get("consensus_dimension")
    error_spans = int(trace_counts.get("error_tool_spans", 0))
    error_unknown_rate = trace_rates.get("error_kind_unknown_rate", 0.0)
    gates = [
        {
            "name": "nodevault_available",
            "passed": bool(nodevault.get("available")),
            "observed": nodevault.get("error") or nodevault.get("path"),
            "threshold": "read-only knowledge_nodes access",
        },
        {
            "name": "traces_available",
            "passed": bool(traces.get("available")),
            "observed": traces.get("error") or traces.get("path"),
            "threshold": "read-only traces/spans access",
        },
        {
            "name": "minimum_trainable_units",
            "passed": trainable_units >= min_samples,
            "observed": trainable_units,
            "threshold": f">= {min_samples}",
        },
        {
            "name": "signature_usable_rate",
            "passed": node_rates.get("signature_usable_rate", 0.0) >= 0.60,
            "observed": round(node_rates.get("signature_usable_rate", 0.0), 4),
            "threshold": ">= 0.60",
        },
        {
            "name": "tool_label_nonempty_rate",
            "passed": trace_rates.get("tool_label_nonempty_rate", 0.0) >= 0.70,
            "observed": round(trace_rates.get("tool_label_nonempty_rate", 0.0), 4),
            "threshold": ">= 0.70",
        },
        {
            "name": "label_diversity_no_collapse",
            "passed": bool(best_group and best_group["stable_classes"] >= 3 and best_group["dominant_ratio"] <= 0.80),
            "observed": best_group,
            "threshold": f">=3 labels with count>={min_label_count}, dominant_ratio<=0.80",
        },
        {
            "name": "embedding_dimension_512_or_absent",
            "passed": embedding_dim in {None, 512},
            "observed": embedding_dim,
            "threshold": "512 when embeddings exist",
        },
        {
            "name": "error_kind_unknown_rate",
            "passed": error_spans == 0 or error_unknown_rate <= 0.50,
            "observed": "no error spans" if error_spans == 0 else round(error_unknown_rate, 4),
            "threshold": "<= 0.50 when error spans exist",
        },
    ]
    passed = all(gate["passed"] for gate in gates)
    warnings = []
    if error_spans == 0:
        warnings.append("No tool error spans found; failure-aware labels cannot be validated yet.")
    if not node_counts.get("usage_feedback_nodes"):
        warnings.append("No NodeVault usage feedback found; success/failure labels will be trace-driven only.")
    if best_group and best_group["dominant_ratio"] > 0.65:
        warnings.append("Best available label group is somewhat imbalanced; compare against frequency baseline before modeling.")
    decision = "PROCEED_TO_BASELINE_EXPERIMENT" if passed else "HOLD_V6_MODEL"
    return {
        "decision": decision,
        "passed": passed,
        "gates": gates,
        "warnings": warnings,
        "sample_summary": {
            "signature_samples": signature_samples,
            "tool_trace_samples": tool_samples,
            "trainable_units": trainable_units,
        },
        "best_label_group": best_group,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    nodevault = audit_nodevault(
        Path(args.nodevault_db).expanduser(),
        args.value_limit,
        args.embedding_sample_limit,
        args.min_label_count,
    )
    traces = audit_traces(
        Path(args.traces_db).expanduser(),
        args.value_limit,
        args.min_label_count,
    )
    gates = evaluate_gates(nodevault, traces, args.min_samples, args.min_label_count)
    return {
        "audit": "genesis_v6_pls_learnability",
        "mode": "read_only",
        "nodevault": nodevault,
        "traces": traces,
        "evaluation": gates,
    }


def format_percent(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return str(value)
    return f"{value * 100:.1f}%"


def render_distribution(items: list[dict[str, Any]], limit: int = 8) -> str:
    if not items:
        return "none"
    return ", ".join(f"{item['value']}={item['count']}" for item in items[:limit])


def render_text(report: dict[str, Any]) -> str:
    nodevault = report["nodevault"]
    traces = report["traces"]
    evaluation = report["evaluation"]
    lines = []
    lines.append("=== Genesis V6 PLS Learnability Audit ===")
    lines.append(f"mode: {report['mode']}")
    lines.append(f"decision: {evaluation['decision']}")
    lines.append("")
    lines.append("-- gates --")
    for gate in evaluation["gates"]:
        mark = "PASS" if gate["passed"] else "FAIL"
        observed = gate["observed"]
        if isinstance(observed, dict):
            observed = json.dumps(observed, ensure_ascii=False)
        lines.append(f"[{mark}] {gate['name']}: observed={observed} threshold={gate['threshold']}")
    if evaluation["warnings"]:
        lines.append("")
        lines.append("-- warnings --")
        for warning in evaluation["warnings"]:
            lines.append(f"- {warning}")
    lines.append("")
    lines.append("-- samples --")
    for key, value in evaluation["sample_summary"].items():
        lines.append(f"{key}: {value}")
    if evaluation.get("best_label_group"):
        lines.append(f"best_label_group: {json.dumps(evaluation['best_label_group'], ensure_ascii=False)}")
    lines.append("")
    lines.append("-- nodevault --")
    lines.append(f"path: {nodevault.get('path')}")
    if not nodevault.get("available"):
        lines.append(f"error: {nodevault.get('error')}")
    else:
        counts = nodevault["counts"]
        rates = nodevault["rates"]
        for key, value in counts.items():
            lines.append(f"{key}: {value}")
        for key, value in rates.items():
            lines.append(f"{key}: {format_percent(value)}")
        lines.append(f"types: {render_distribution(nodevault.get('type_distribution', []))}")
        lines.append(f"trust_tiers: {render_distribution(nodevault.get('trust_tier_distribution', []))}")
        lines.append(f"embedding_dimensions: {json.dumps(nodevault.get('embedding_dimensions'), ensure_ascii=False)}")
        lines.append("signature_top_values:")
        for field, items in nodevault.get("signature_value_distribution", {}).items():
            lines.append(f"  {field}: {render_distribution(items, 6)}")
    lines.append("")
    lines.append("-- traces --")
    lines.append(f"path: {traces.get('path')}")
    if not traces.get("available"):
        lines.append(f"error: {traces.get('error')}")
    else:
        counts = traces["counts"]
        rates = traces["rates"]
        for key, value in counts.items():
            lines.append(f"{key}: {value}")
        for key, value in rates.items():
            lines.append(f"{key}: {format_percent(value)}")
        lines.append(f"trace_status: {render_distribution(traces.get('trace_status_distribution', []))}")
        lines.append(f"span_types: {render_distribution(traces.get('span_type_distribution', []))}")
        lines.append(f"tools: {render_distribution(traces.get('tool_distribution', []))}")
        lines.append(f"error_kinds: {render_distribution(traces.get('error_kind_distribution', []))}")
        lines.append(f"duration_summary: {json.dumps(traces.get('duration_summary'), ensure_ascii=False)}")
    lines.append("")
    if evaluation["passed"]:
        lines.append("next: run baseline experiments; still do not integrate with runtime.")
    else:
        lines.append("next: do not implement V6 model; fix data coverage/label quality first.")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only Genesis V6 PLS learnability audit")
    parser.add_argument("--nodevault-db", default=str(DEFAULT_NODEVAULT_DB))
    parser.add_argument("--traces-db", default=str(DEFAULT_TRACES_DB))
    parser.add_argument("--format", choices={"text", "json"}, default="text")
    parser.add_argument("--value-limit", type=int, default=12)
    parser.add_argument("--embedding-sample-limit", type=int, default=200)
    parser.add_argument("--min-samples", type=int, default=100)
    parser.add_argument("--min-label-count", type=int, default=3)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
