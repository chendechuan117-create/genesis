from __future__ import annotations

import argparse
import json
import math
import random
import re
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
STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "when", "then",
    "are", "was", "were", "you", "your", "has", "have", "not", "but", "can",
    "should", "will", "would", "could", "about", "after", "before", "using",
    "一个", "这个", "需要", "可以", "不是", "如果", "因为", "所以", "已经", "应该",
}


class BaselineError(RuntimeError):
    pass


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise BaselineError(f"database not found: {path}")
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


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


def tokenize(text: str, max_tokens: int) -> list[str]:
    raw_tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}|\d+[a-zA-Z_]+|[\u4e00-\u9fff]{2,}", text.lower())
    tokens = []
    seen = set()
    for token in raw_tokens:
        if token in STOPWORDS or len(token) < 2:
            continue
        if token not in seen:
            seen.add(token)
            tokens.append(token)
        if len(tokens) >= max_tokens:
            break
    return tokens


def load_signature_samples(path: Path, max_tokens: int) -> list[dict[str, Any]]:
    conn = connect_readonly(path)
    try:
        rows = conn.execute(
            """
            SELECT k.node_id, k.type, k.title, k.human_translation, k.tags, k.resolves,
                   k.metadata_signature, nc.full_content
            FROM knowledge_nodes k
            LEFT JOIN node_contents nc ON nc.node_id = k.node_id
            WHERE k.node_id NOT LIKE 'MEM_CONV%'
              AND k.metadata_signature IS NOT NULL
              AND TRIM(k.metadata_signature) != ''
              AND TRIM(k.metadata_signature) != '{}'
            """
        ).fetchall()
        samples = []
        for row in rows:
            signature = parse_json_object(row["metadata_signature"])
            if not signature:
                continue
            labels = {}
            for field in CORE_LABEL_FIELDS:
                values = normalize_values(signature.get(field))
                if values:
                    labels[field] = values
            if not labels:
                continue
            text_parts = [
                row["type"] or "",
                row["title"] or "",
                row["human_translation"] or "",
                row["tags"] or "",
                row["resolves"] or "",
                row["full_content"] or "",
            ]
            tokens = tokenize("\n".join(text_parts), max_tokens)
            if not tokens:
                continue
            samples.append({"id": row["node_id"], "tokens": tokens, "labels": labels})
        return samples
    finally:
        conn.close()


def load_tool_samples(path: Path, max_tokens: int) -> list[dict[str, Any]]:
    conn = connect_readonly(path)
    try:
        rows = conn.execute(
            """
            SELECT t.trace_id, t.user_input, s.tool_name
            FROM traces t
            JOIN spans s ON s.trace_id = t.trace_id
            WHERE s.span_type = 'tool_call'
              AND s.tool_name IS NOT NULL
              AND TRIM(s.tool_name) != ''
              AND t.user_input IS NOT NULL
              AND TRIM(t.user_input) != ''
            """
        ).fetchall()
        by_trace: dict[str, dict[str, Any]] = {}
        for row in rows:
            trace_id = row["trace_id"]
            sample = by_trace.setdefault(
                trace_id,
                {
                    "id": trace_id,
                    "tokens": tokenize(row["user_input"] or "", max_tokens),
                    "labels": {"tool_name": []},
                },
            )
            tool_name = str(row["tool_name"] or "").strip()
            if tool_name and tool_name not in sample["labels"]["tool_name"]:
                sample["labels"]["tool_name"].append(tool_name)
        return [sample for sample in by_trace.values() if sample["tokens"] and sample["labels"]["tool_name"]]
    finally:
        conn.close()


def split_samples(samples: list[dict[str, Any]], test_ratio: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    shuffled = list(samples)
    random.Random(seed).shuffle(shuffled)
    test_size = max(1, int(len(shuffled) * test_ratio)) if len(shuffled) >= 2 else 0
    test = shuffled[:test_size]
    train = shuffled[test_size:]
    return train, test


def build_label_counts(samples: list[dict[str, Any]], field: str, min_label_count: int) -> Counter[str]:
    counts = Counter()
    for sample in samples:
        for label in sample["labels"].get(field, []):
            counts[label] += 1
    return Counter({label: count for label, count in counts.items() if count >= min_label_count})


def train_multinomial_nb(samples: list[dict[str, Any]], field: str, stable_labels: set[str]) -> dict[str, Any]:
    label_doc_counts = Counter()
    token_counts: dict[str, Counter[str]] = defaultdict(Counter)
    token_totals = Counter()
    vocabulary = set()
    for sample in samples:
        labels = [label for label in sample["labels"].get(field, []) if label in stable_labels]
        if not labels:
            continue
        tokens = sample["tokens"]
        for label in labels:
            label_doc_counts[label] += 1
            token_counts[label].update(tokens)
            token_totals[label] += len(tokens)
            vocabulary.update(tokens)
    return {
        "label_doc_counts": label_doc_counts,
        "token_counts": token_counts,
        "token_totals": token_totals,
        "vocabulary_size": max(1, len(vocabulary)),
        "total_docs": sum(label_doc_counts.values()),
    }


def predict_frequency(label_counts: Counter[str], top_k: int) -> list[str]:
    return [label for label, _ in label_counts.most_common(top_k)]


def predict_nb(model: dict[str, Any], tokens: list[str], top_k: int, alpha: float) -> list[str]:
    label_doc_counts: Counter[str] = model["label_doc_counts"]
    if not label_doc_counts:
        return []
    token_counts: dict[str, Counter[str]] = model["token_counts"]
    token_totals: Counter[str] = model["token_totals"]
    vocabulary_size = model["vocabulary_size"]
    total_docs = model["total_docs"]
    labels = list(label_doc_counts.keys())
    scores = []
    for label in labels:
        prior = math.log((label_doc_counts[label] + alpha) / (total_docs + alpha * len(labels)))
        denominator = token_totals[label] + alpha * vocabulary_size
        score = prior
        counts = token_counts[label]
        for token in tokens:
            score += math.log((counts[token] + alpha) / denominator)
        scores.append((score, label))
    scores.sort(reverse=True)
    return [label for _, label in scores[:top_k]]


def hit_any(predictions: list[str], actual: set[str], k: int) -> bool:
    return any(label in actual for label in predictions[:k])


def evaluate_field(
    train: list[dict[str, Any]],
    test: list[dict[str, Any]],
    field: str,
    min_label_count: int,
    top_k: int,
    alpha: float,
) -> dict[str, Any] | None:
    label_counts = build_label_counts(train, field, min_label_count)
    if len(label_counts) < 2:
        return None
    stable_labels = set(label_counts.keys())
    model = train_multinomial_nb(train, field, stable_labels)
    freq_predictions = predict_frequency(label_counts, top_k)
    eligible = 0
    freq_top1 = 0
    freq_topk = 0
    nb_top1 = 0
    nb_topk = 0
    for sample in test:
        actual = {label for label in sample["labels"].get(field, []) if label in stable_labels}
        if not actual:
            continue
        eligible += 1
        nb_predictions = predict_nb(model, sample["tokens"], top_k, alpha)
        if hit_any(freq_predictions, actual, 1):
            freq_top1 += 1
        if hit_any(freq_predictions, actual, top_k):
            freq_topk += 1
        if hit_any(nb_predictions, actual, 1):
            nb_top1 += 1
        if hit_any(nb_predictions, actual, top_k):
            nb_topk += 1
    if not eligible:
        return None
    return {
        "field": field,
        "train_samples": len(train),
        "test_samples": len(test),
        "eligible_test_samples": eligible,
        "stable_labels": len(stable_labels),
        "dominant_label": label_counts.most_common(1)[0][0],
        "dominant_ratio_train": label_counts.most_common(1)[0][1] / sum(label_counts.values()),
        "frequency_top1": freq_top1 / eligible,
        "frequency_topk": freq_topk / eligible,
        "nb_top1": nb_top1 / eligible,
        "nb_topk": nb_topk / eligible,
        "gain_top1": (nb_top1 - freq_top1) / eligible,
        "gain_topk": (nb_topk - freq_topk) / eligible,
    }


def run_dataset(
    name: str,
    samples: list[dict[str, Any]],
    fields: list[str],
    args: argparse.Namespace,
) -> dict[str, Any]:
    train, test = split_samples(samples, args.test_ratio, args.seed)
    field_results = []
    for field in fields:
        result = evaluate_field(train, test, field, args.min_label_count, args.top_k, args.alpha)
        if result:
            field_results.append(result)
    field_results.sort(key=lambda item: (item["gain_top1"], item["nb_topk"]), reverse=True)
    eligible_results = [item for item in field_results if item["eligible_test_samples"] >= args.min_eval_samples]
    fields_with_top1_gain = [item for item in eligible_results if item["gain_top1"] >= args.min_gain]
    fields_with_topk_gain = [item for item in eligible_results if item["gain_topk"] >= args.min_gain]
    avg_gain_top1 = 0.0
    avg_gain_topk = 0.0
    if eligible_results:
        avg_gain_top1 = sum(item["gain_top1"] for item in eligible_results) / len(eligible_results)
        avg_gain_topk = sum(item["gain_topk"] for item in eligible_results) / len(eligible_results)
    return {
        "name": name,
        "sample_count": len(samples),
        "train_count": len(train),
        "test_count": len(test),
        "evaluated_fields": len(field_results),
        "eligible_fields": len(eligible_results),
        "fields_with_top1_gain": len(fields_with_top1_gain),
        "fields_with_topk_gain": len(fields_with_topk_gain),
        "avg_gain_top1": avg_gain_top1,
        "avg_gain_topk": avg_gain_topk,
        "field_results": field_results,
    }


def decide(signature_report: dict[str, Any], tool_report: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    signature_pass = (
        signature_report["fields_with_top1_gain"] >= args.min_passing_fields
        or signature_report["fields_with_topk_gain"] >= args.min_passing_fields
        or signature_report["avg_gain_topk"] >= args.min_avg_gain
    )
    tool_pass = (
        tool_report["fields_with_top1_gain"] >= 1
        or tool_report["fields_with_topk_gain"] >= 1
        or tool_report["avg_gain_topk"] >= args.min_avg_gain
    )
    passed = signature_pass or tool_pass
    if passed:
        decision = "PROCEED_TO_SHADOW_DESIGN"
    else:
        decision = "HOLD_V6_MODEL_BASELINE_WEAK"
    return {
        "decision": decision,
        "passed": passed,
        "signature_pass": signature_pass,
        "tool_pass": tool_pass,
        "thresholds": {
            "min_gain": args.min_gain,
            "min_avg_gain": args.min_avg_gain,
            "min_passing_fields": args.min_passing_fields,
            "top_k": args.top_k,
        },
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    signature_samples = load_signature_samples(Path(args.nodevault_db).expanduser(), args.max_tokens)
    tool_samples = load_tool_samples(Path(args.traces_db).expanduser(), args.max_tokens)
    signature_report = run_dataset("signature", signature_samples, CORE_LABEL_FIELDS, args)
    tool_report = run_dataset("tool", tool_samples, ["tool_name"], args)
    evaluation = decide(signature_report, tool_report, args)
    return {
        "experiment": "genesis_v6_pls_baseline_predictability",
        "mode": "read_only",
        "nodevault_db": str(Path(args.nodevault_db).expanduser()),
        "traces_db": str(Path(args.traces_db).expanduser()),
        "signature": signature_report,
        "tool": tool_report,
        "evaluation": evaluation,
    }


def percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_field_result(result: dict[str, Any]) -> str:
    return (
        f"{result['field']}: labels={result['stable_labels']} eligible={result['eligible_test_samples']} "
        f"freq@1={percent(result['frequency_top1'])} nb@1={percent(result['nb_top1'])} "
        f"gain@1={percent(result['gain_top1'])} freq@k={percent(result['frequency_topk'])} "
        f"nb@k={percent(result['nb_topk'])} gain@k={percent(result['gain_topk'])} "
        f"dominant={result['dominant_label']}({percent(result['dominant_ratio_train'])})"
    )


def render_dataset(report: dict[str, Any], limit: int) -> list[str]:
    lines = []
    lines.append(f"-- {report['name']} baseline --")
    lines.append(f"samples: {report['sample_count']} train={report['train_count']} test={report['test_count']}")
    lines.append(
        f"evaluated_fields: {report['evaluated_fields']} eligible_fields={report['eligible_fields']} "
        f"fields_with_top1_gain={report['fields_with_top1_gain']} fields_with_topk_gain={report['fields_with_topk_gain']}"
    )
    lines.append(f"avg_gain_top1: {percent(report['avg_gain_top1'])}")
    lines.append(f"avg_gain_topk: {percent(report['avg_gain_topk'])}")
    for result in report["field_results"][:limit]:
        lines.append(render_field_result(result))
    return lines


def render_text(report: dict[str, Any], limit: int) -> str:
    lines = []
    lines.append("=== Genesis V6 PLS Baseline Predictability ===")
    lines.append(f"mode: {report['mode']}")
    lines.append(f"decision: {report['evaluation']['decision']}")
    lines.append(f"signature_pass: {report['evaluation']['signature_pass']}")
    lines.append(f"tool_pass: {report['evaluation']['tool_pass']}")
    lines.append(f"thresholds: {json.dumps(report['evaluation']['thresholds'], ensure_ascii=False)}")
    lines.append("")
    lines.extend(render_dataset(report["signature"], limit))
    lines.append("")
    lines.extend(render_dataset(report["tool"], limit))
    lines.append("")
    if report["evaluation"]["passed"]:
        lines.append("next: design shadow-mode logging; still do not alter runtime decisions.")
    else:
        lines.append("next: hold V6 model; improve labels or data before shadow mode.")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only Genesis V6 baseline predictability experiment")
    parser.add_argument("--nodevault-db", default=str(DEFAULT_NODEVAULT_DB))
    parser.add_argument("--traces-db", default=str(DEFAULT_TRACES_DB))
    parser.add_argument("--format", choices={"text", "json"}, default="text")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-ratio", type=float, default=0.2)
    parser.add_argument("--min-label-count", type=int, default=3)
    parser.add_argument("--min-eval-samples", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--alpha", type=float, default=1.0)
    parser.add_argument("--max-tokens", type=int, default=160)
    parser.add_argument("--min-gain", type=float, default=0.05)
    parser.add_argument("--min-avg-gain", type=float, default=0.03)
    parser.add_argument("--min-passing-fields", type=int, default=2)
    parser.add_argument("--display-limit", type=int, default=12)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report, args.display_limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
