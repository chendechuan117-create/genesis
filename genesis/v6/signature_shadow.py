from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .baseline_pls_predictability import (
        DEFAULT_NODEVAULT_DB,
        build_label_counts,
        load_signature_samples,
        train_multinomial_nb,
        tokenize,
    )
except ImportError:
    from baseline_pls_predictability import (
        DEFAULT_NODEVAULT_DB,
        build_label_counts,
        load_signature_samples,
        train_multinomial_nb,
        tokenize,
    )

DEFAULT_FIELDS = ["error_kind", "framework", "task_kind", "runtime", "target_kind"]
DEFAULT_LOG_PATH = Path(__file__).resolve().parents[2] / "runtime" / "v6_shadow_predictions.jsonl"


class SignatureShadowError(RuntimeError):
    pass


class SignatureShadowPredictor:
    def __init__(self, fields: list[str], min_label_count: int, max_tokens: int, alpha: float):
        self.fields = fields
        self.min_label_count = min_label_count
        self.max_tokens = max_tokens
        self.alpha = alpha
        self.models: dict[str, dict[str, Any]] = {}
        self.label_counts: dict[str, Counter[str]] = {}
        self.sample_count = 0

    def fit(self, nodevault_db: Path) -> None:
        samples = load_signature_samples(nodevault_db, self.max_tokens)
        self.sample_count = len(samples)
        if not samples:
            raise SignatureShadowError("no signature samples available")
        for field in self.fields:
            counts = build_label_counts(samples, field, self.min_label_count)
            if len(counts) < 2:
                continue
            model = train_multinomial_nb(samples, field, set(counts.keys()))
            if not model["label_doc_counts"]:
                continue
            self.label_counts[field] = counts
            self.models[field] = model
        if not self.models:
            raise SignatureShadowError("no fields have enough stable labels")

    def predict(self, text: str, top_k: int) -> dict[str, Any]:
        tokens = tokenize(text, self.max_tokens)
        if not tokens:
            raise SignatureShadowError("input text produced no usable tokens")
        predictions = {}
        baselines = {}
        for field, model in self.models.items():
            predictions[field] = self._predict_field(model, tokens, top_k)
            baselines[field] = self._frequency_baseline(field, top_k)
        return {
            "fields": list(self.models.keys()),
            "sample_count": self.sample_count,
            "token_count": len(tokens),
            "predictions": predictions,
            "baseline": baselines,
        }

    def _predict_field(self, model: dict[str, Any], tokens: list[str], top_k: int) -> list[list[Any]]:
        label_doc_counts = model["label_doc_counts"]
        token_counts = model["token_counts"]
        token_totals = model["token_totals"]
        vocabulary_size = model["vocabulary_size"]
        total_docs = model["total_docs"]
        labels = list(label_doc_counts.keys())
        scored = []
        for label in labels:
            score = math.log((label_doc_counts[label] + self.alpha) / (total_docs + self.alpha * len(labels)))
            denominator = token_totals[label] + self.alpha * vocabulary_size
            counts = token_counts[label]
            for token in tokens:
                score += math.log((counts[token] + self.alpha) / denominator)
            scored.append((label, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        top = scored[:top_k]
        probabilities = self._softmax([score for _, score in top])
        return [[label, round(probability, 4)] for (label, _), probability in zip(top, probabilities)]

    def _frequency_baseline(self, field: str, top_k: int) -> list[list[Any]]:
        counts = self.label_counts[field]
        total = sum(counts.values())
        if not total:
            return []
        return [[label, round(count / total, 4)] for label, count in counts.most_common(top_k)]

    @staticmethod
    def _softmax(scores: list[float]) -> list[float]:
        if not scores:
            return []
        max_score = max(scores)
        exps = [math.exp(score - max_score) for score in scores]
        total = sum(exps)
        if not total:
            return [0.0 for _ in scores]
        return [value / total for value in exps]


def resolve_input(args: argparse.Namespace) -> str:
    if args.input_text:
        return args.input_text
    if args.input_file:
        return Path(args.input_file).expanduser().read_text(encoding="utf-8")
    raise SignatureShadowError("provide --input-text or --input-file")


def build_record(args: argparse.Namespace) -> dict[str, Any]:
    predictor = SignatureShadowPredictor(args.fields, args.min_label_count, args.max_tokens, args.alpha)
    predictor.fit(Path(args.nodevault_db).expanduser())
    text = resolve_input(args)
    result = predictor.predict(text, args.top_k)
    return {
        "mode": "shadow_only",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "trace_id": args.trace_id or None,
        "user_input_preview": text[:300],
        "nodevault_db": str(Path(args.nodevault_db).expanduser()),
        **result,
    }


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def render_text(record: dict[str, Any]) -> str:
    lines = []
    lines.append("=== Genesis V6 Signature Shadow Prediction ===")
    lines.append(f"mode: {record['mode']}")
    lines.append(f"trace_id: {record.get('trace_id') or 'none'}")
    lines.append(f"sample_count: {record['sample_count']}")
    lines.append(f"token_count: {record['token_count']}")
    lines.append(f"fields: {', '.join(record['fields'])}")
    lines.append("")
    for field in record["fields"]:
        predictions = ", ".join(f"{label}:{score}" for label, score in record["predictions"].get(field, []))
        baseline = ", ".join(f"{label}:{score}" for label, score in record["baseline"].get(field, []))
        lines.append(f"{field}")
        lines.append(f"  shadow:  {predictions}")
        lines.append(f"  baseline:{baseline}")
    lines.append("")
    lines.append("decision: record-only; do not use for routing, filtering, or prompt injection yet.")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone read-only V6 signature shadow predictor")
    parser.add_argument("--nodevault-db", default=str(DEFAULT_NODEVAULT_DB))
    parser.add_argument("--input-text", default="")
    parser.add_argument("--input-file", default="")
    parser.add_argument("--trace-id", default="")
    parser.add_argument("--fields", nargs="+", default=DEFAULT_FIELDS)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--min-label-count", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=160)
    parser.add_argument("--alpha", type=float, default=1.0)
    parser.add_argument("--format", choices={"text", "json"}, default="text")
    parser.add_argument("--log-jsonl", nargs="?", const=str(DEFAULT_LOG_PATH), default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    record = build_record(args)
    if args.log_jsonl:
        append_jsonl(Path(args.log_jsonl).expanduser(), record)
    if args.format == "json":
        print(json.dumps(record, ensure_ascii=False, indent=2))
    else:
        print(render_text(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
