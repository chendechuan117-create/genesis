from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = REPO_ROOT / "runtime/pls_chapter_state_recovery"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from .builder import build_offline_chapter_state
    from .chapter_state_model import ChapterState
    from .renderer import render_chapter_state
    from .source_lanes import (
        CHAPTER_RECOVERY_HISTORY_PACKET,
        DECOY_BLOCK,
        DOC_EXCERPT_PACKET,
        RAW_HISTORY_PACKET,
        SOURCE_LANES,
        STRONG_DECOY_BLOCK,
    )
except ImportError:
    from builder import build_offline_chapter_state
    from chapter_state_model import ChapterState
    from renderer import render_chapter_state
    from source_lanes import (
        CHAPTER_RECOVERY_HISTORY_PACKET,
        DECOY_BLOCK,
        DOC_EXCERPT_PACKET,
        RAW_HISTORY_PACKET,
        SOURCE_LANES,
        STRONG_DECOY_BLOCK,
    )

DIRECT_TASK = """You are a fresh LLM entering the current Genesis/PLS design chapter.

Answer these questions in Chinese, concisely but substantively:
1. What is PLS primarily for now?
2. What direction has just been rejected or deprecated?
3. Why was the RKXOR validation result important but not the center?
4. What is the natural next topic if we do not buy the box and lose the pearl?
5. What should the assistant avoid doing next?
"""

OPEN_NEXT_TASK = """You are entering an ongoing Genesis/PLS design conversation.

Based only on the source packet, answer in Chinese:
1. What is the next research topic we should work on?
2. Why is that the right next topic?
3. What would be a misleading next step?
"""

COMPILE_TASK = """You are the chapter-state compiler for a discontinuous LLM system.

Compile the raw source material into a compact CURRENT PLS CHAPTER STATE packet.
Do not answer the user's next-step question. Produce only the state packet.

The packet must preserve:
- CANON: the current identity of PLS.
- DEPRECATED: directions rejected by newer evidence or user correction.
- BOUNDARIES: what the next assistant should not do.
- NATURAL NEXT QUESTION: the next topic implied by the current chapter.

If old notes contain concrete action items that conflict with later user correction or current canon, mark them as deprecated instead of following them.
"""

COMPILE_JSON_TASK = """You are the chapter-state compiler for a discontinuous LLM system.

Compile the raw source material into a compact JSON object. Return JSON only. Do not include markdown fences.

Use exactly these keys:
- canon: list of current identity claims.
- evidence: list of key evidence items that justify the current state.
- deprecated: list of directions rejected by newer evidence or user correction.
- boundaries: list of constraints for the next assistant.
- stale_actions: list of concrete old action items that should not be followed now.
- active_question: one string naming the natural next research question.
- source_refs: list of objects with source and claim strings.

If old notes contain concrete action items that conflict with later user correction or current canon, put them in stale_actions and deprecated instead of following them.
"""

TASKS = {
    "direct": DIRECT_TASK,
    "open_next": OPEN_NEXT_TASK,
}

GOLD = {
    "core_identity": "PLS is a local personal concept-world / current chapter-state layer for discontinuous LLM runs, closest to AI contextualizes AI.",
    "not_solver": "PLS should not be treated primarily as an external solver/task benchmark booster; RKXOR showed that raw activation can harm execution.",
    "state_not_dump": "PLS value is current-state rendering/epistemic identity, not top-k memory, RAG, or more context.",
    "boundaries": "A useful chapter state includes canon/draft/deprecated, what to remember, inhibit, verify, hide, and user value boundaries.",
    "next_topic": "The next topic is chapter-state recovery / conceptual continuity: can a fresh LLM enter the current concept chapter and avoid deprecated directions?",
}

CHAPTER_STATE_PACKET = """CURRENT PLS CHAPTER STATE

CANON
- Genesis trunk identity: local continuity for a person's conceptual world.
- PLS role: AI contextualizes AI. It controls the conceptual environment/current chapter state a fresh text LLM receives.
- The LLM executes language/tool work in the present; PLS carries continuity across discontinuous runs.
- PLS is not primarily a chatbot, agent benchmark helper, RAG layer, or solver enhancer.

CURRENT CLAIM UNDER TEST
- PLS value should be measured by whether a fresh LLM enters the right conceptual chapter: canon, deprecated paths, unresolved threads, user values, and next natural question.
- Compounding only matters if writeback changes future activation, not if more memories are merely stored.

DEPRECATED AFTER RKXOR PILOT
- Treating PLS as an external task-solving booster is rejected for now.
- Raw PLS activation on RKXOR was negative: baseline mean score 0.9417, PLS mean score 0.375, PLS failed/timed out 3 of 5 paired samples.
- The mistake is not that PLS must be bent toward RKXOR. The mistake is making the benchmark the center instead of asking what PLS naturally does.

BOUNDARIES
- Do not design the next step as another crypto challenge.
- Do not tune PLS to win a benchmark if that distorts its identity.
- Do not equate PLS with more retrieved memory.
- Do preserve user's correction: catch the pearl, not the box.

NATURAL NEXT QUESTION
- Chapter-state recovery: can a fresh LLM recover PLS's current conceptual state and avoid reverting to deprecated directions?
"""

COMPILER_SOURCES = {
    "raw_history": RAW_HISTORY_PACKET,
    "raw_history_docs": RAW_HISTORY_PACKET + "\n\n" + DOC_EXCERPT_PACKET,
    "raw_history_docs_strong_decoy": RAW_HISTORY_PACKET + "\n\n" + DOC_EXCERPT_PACKET + "\n\n" + STRONG_DECOY_BLOCK,
    "full_experiment_history_strong_decoy": RAW_HISTORY_PACKET + "\n\n" + DOC_EXCERPT_PACKET + "\n\n" + CHAPTER_RECOVERY_HISTORY_PACKET + "\n\n" + STRONG_DECOY_BLOCK,
}

ARMS = {
    "doc_excerpts": DOC_EXCERPT_PACKET,
    "raw_history": RAW_HISTORY_PACKET,
    "chapter_state": CHAPTER_STATE_PACKET,
    "doc_excerpts_with_decoy": DOC_EXCERPT_PACKET + "\n\n" + DECOY_BLOCK,
    "raw_history_with_decoy": RAW_HISTORY_PACKET + "\n\n" + DECOY_BLOCK,
    "chapter_state_with_decoy": CHAPTER_STATE_PACKET + "\n\n" + DECOY_BLOCK,
    "doc_excerpts_strong_decoy": DOC_EXCERPT_PACKET + "\n\n" + STRONG_DECOY_BLOCK,
    "raw_history_strong_decoy": RAW_HISTORY_PACKET + "\n\n" + STRONG_DECOY_BLOCK,
    "chapter_state_strong_decoy": CHAPTER_STATE_PACKET + "\n\n" + STRONG_DECOY_BLOCK,
}


RUBRIC = {
    "core_identity": {
        "weight": 2,
        "positive": ["local continuity", "conceptual world", "概念世界", "current chapter", "章节状态", "AI contextualizes", "AI语境化AI", "上下文化", "状态编译"],
    },
    "not_solver_benchmark": {
        "weight": 2,
        "positive": [
            "不是.*(solver|解题|benchmark|外部任务)",
            "拒绝.*(solver|解题|benchmark|外部任务|RKXOR|crypto|加密)",
            "废弃.*(solver|解题|benchmark|外部任务|RKXOR|crypto|加密)",
            "不要.*(crypto|加密|RKXOR|benchmark|外部任务)",
        ],
        "negative": [
            "(下一|下一个|继续|应该|自然).*?(RKXOR|crypto|加密|AES-ECB|padding|Cryptopals|hidden judge|外部任务)",
            "disciplined_pls.*?(下一|继续|应该|自然)",
            "(调|优化|tune).*?(PLS).*?(benchmark|judge|RKXOR)",
        ],
    },
    "state_not_dump": {
        "weight": 2,
        "positive": ["不是.*top-k", "不是.*RAG", "不是.*更多", "状态", "current-state", "activation state", "证据身份", "epistemic"],
    },
    "boundaries_inhibition": {
        "weight": 2,
        "positive": ["inhibit", "抑制", "deprecated", "废弃", "canon", "边界", "verify", "隐藏", "用户.*价值"],
    },
    "next_topic": {
        "weight": 2,
        "positive": [
            "chapter-state recovery",
            "章节状态恢复",
            "概念连续",
            "conceptual continuity",
            "fresh LLM",
            "当前章节",
            "ChapterStateBuilder",
            "状态编译",
            "抗诱饵",
            "anti-decoy",
        ],
    },
}

NEGATION_MARKERS = [
    "避免",
    "不要",
    "不应",
    "不再",
    "不是",
    "而非",
    "拒绝",
    "废弃",
    "弃用",
    "误导",
    "偏离",
    "冲突",
    "已拒绝",
    "not",
    "avoid",
    "reject",
    "rejected",
    "deprecated",
    "misleading",
    "conflict",
]


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def extract_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end < start:
            raise
        parsed = json.loads(candidate[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("compiled chapter state JSON must be an object")
    return parsed


def find_unnegated_hits(text: str, patterns: list[str]) -> list[str]:
    hits = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            start = max(0, match.start() - 120)
            end = min(len(text), match.end() + 120)
            context = text[start:end]
            if any(marker.lower() in context.lower() for marker in NEGATION_MARKERS):
                continue
            hits.append(pattern)
            break
    return hits


def score_text(text: str) -> dict[str, Any]:
    total = 0
    details: dict[str, Any] = {}
    for name, spec in RUBRIC.items():
        positives = spec.get("positive", [])
        negatives = spec.get("negative", [])
        pos_hits = [p for p in positives if re.search(p, text, flags=re.IGNORECASE | re.DOTALL)]
        neg_hits = find_unnegated_hits(text, negatives)
        score = spec["weight"] if pos_hits else 0
        if neg_hits:
            score = max(0, score - spec["weight"])
        total += score
        details[name] = {"score": score, "weight": spec["weight"], "positive_hits": pos_hits, "negative_hits": neg_hits}
    return {"score": total, "max_score": sum(item["weight"] for item in RUBRIC.values()), "details": details}


def build_messages(packet: str, task: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "You are evaluating conceptual continuity. Do not invent project facts not present in the packet. Answer in Chinese."},
        {"role": "user", "content": f"SOURCE PACKET:\n\n{packet}\n\nTASK:\n{task}"},
    ]


def build_compile_messages(source: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "You compile conceptual continuity state. Output only the requested packet, in English headings with concise Chinese bullets."},
        {"role": "user", "content": f"RAW SOURCE MATERIAL:\n\n{source}\n\nCOMPILER TASK:\n{COMPILE_TASK}"},
    ]


def build_structured_compile_messages(source: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "You compile conceptual continuity state. Output JSON only."},
        {"role": "user", "content": f"RAW SOURCE MATERIAL:\n\n{source}\n\nCOMPILER TASK:\n{COMPILE_JSON_TASK}"},
    ]


async def call_llm(args: argparse.Namespace, messages: list[dict[str, str]]) -> str:
    from genesis.core.config import config
    from genesis.core.provider import NativeHTTPProvider

    provider_name = clean(args.llm_provider) or "deepseek"
    if provider_name != "deepseek":
        raise SystemExit("Only --llm-provider deepseek is supported in this minimal runner")
    api_key = clean(args.llm_api_key) or clean(config.deepseek_api_key) or clean(os.environ.get("DEEPSEEK_API_KEY"))
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY is required")
    provider = NativeHTTPProvider(
        api_key=api_key,
        base_url=clean(args.llm_base_url) or "https://api.deepseek.com/v1",
        default_model=clean(args.llm_model) or "deepseek-chat",
        provider_name="deepseek",
    )
    response = await provider.chat(messages, temperature=args.temperature, max_tokens=args.max_tokens)
    return response.content or ""


async def compile_chapter_state(args: argparse.Namespace, out_dir: Path) -> str:
    compile_path = out_dir / "compiled_state.json"
    if (args.resume or args.rescore) and compile_path.exists():
        data = json.loads(compile_path.read_text(encoding="utf-8"))
        return data["compiled_state"]
    if args.rescore:
        raise SystemExit(f"cannot rescore without compiled state: {compile_path}")
    source = COMPILER_SOURCES[args.compiler_source]
    messages = build_compile_messages(source)
    compiled_state = "" if args.dry_run else await call_llm(args, messages)
    result = {
        "compiler_source": args.compiler_source,
        "source_chars": len(source),
        "messages": messages,
        "compiled_state": compiled_state,
    }
    compile_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return compiled_state


async def compile_structured_chapter_state(args: argparse.Namespace, out_dir: Path) -> str:
    compile_path = out_dir / "structured_state.json"
    if (args.resume or args.rescore) and compile_path.exists():
        data = json.loads(compile_path.read_text(encoding="utf-8"))
        return data["rendered_state"]
    if args.rescore:
        raise SystemExit(f"cannot rescore without structured state: {compile_path}")
    source = COMPILER_SOURCES[args.compiler_source]
    messages = build_structured_compile_messages(source)
    raw_output = "" if args.dry_run else await call_llm(args, messages)
    state = ChapterState.from_dict({}) if args.dry_run else ChapterState.from_dict(extract_json_object(raw_output))
    rendered_state = render_chapter_state(state)
    result = {
        "compiler_source": args.compiler_source,
        "source_chars": len(source),
        "messages": messages,
        "raw_output": raw_output,
        "state": state.to_dict(),
        "rendered_state": rendered_state,
    }
    compile_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return rendered_state


def build_chapter_state(args: argparse.Namespace, out_dir: Path) -> str:
    build_path = out_dir / "built_state.json"
    if (args.resume or args.rescore) and build_path.exists():
        data = json.loads(build_path.read_text(encoding="utf-8"))
        return data["rendered_state"]
    if args.rescore:
        raise SystemExit(f"cannot rescore without built state: {build_path}")
    state = build_offline_chapter_state()
    rendered_state = render_chapter_state(state)
    result = {
        "builder": "offline_experiment_builder",
        "source_lanes": [lane.__dict__ for lane in SOURCE_LANES],
        "state": state.to_dict(),
        "rendered_state": rendered_state,
    }
    build_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return rendered_state


async def run(args: argparse.Namespace) -> None:
    run_id = args.run_id or time.strftime("chapter_state_%Y%m%d_%H%M%S")
    out_dir = (Path(args.out) / run_id).resolve()
    if out_dir.exists() and not args.resume and not args.rescore:
        raise SystemExit(f"run already exists: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "gold.json").write_text(json.dumps(GOLD, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = []
    task = TASKS[args.task_mode]
    arms = dict(ARMS)
    if args.build_state:
        compiled_state = build_chapter_state(args, out_dir)
        arms["compiled_state"] = compiled_state
        arms["compiled_state_strong_decoy"] = compiled_state + "\n\n" + STRONG_DECOY_BLOCK
    elif args.compile_state:
        if args.structured_state:
            compiled_state = await compile_structured_chapter_state(args, out_dir)
        else:
            compiled_state = await compile_chapter_state(args, out_dir)
        arms["compiled_state"] = compiled_state
        arms["compiled_state_strong_decoy"] = compiled_state + "\n\n" + STRONG_DECOY_BLOCK
    selected_arms = set(args.only.split(",")) if args.only else set(arms)
    for arm, packet in arms.items():
        if arm not in selected_arms:
            continue
        messages = build_messages(packet, task)
        arm_path = out_dir / f"{arm}.json"
        if (args.resume or args.rescore) and arm_path.exists():
            result = json.loads(arm_path.read_text(encoding="utf-8"))
            if args.rescore:
                result["score"] = score_text(result.get("answer", ""))
                arm_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        else:
            if args.rescore:
                raise SystemExit(f"cannot rescore missing arm result: {arm_path}")
            if args.dry_run:
                answer = ""
            else:
                answer = await call_llm(args, messages)
            result = {
                "arm": arm,
                "task_mode": args.task_mode,
                "source_chars": len(packet),
                "messages": messages,
                "answer": answer,
                "score": score_text(answer),
            }
            arm_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        rows.append({"arm": arm, "source_chars": result["source_chars"], **result["score"]})
    summary = {
        "run_id": run_id,
        "out_dir": str(out_dir),
        "task_mode": args.task_mode,
        "only": sorted(selected_arms),
        "build_state": args.build_state,
        "compile_state": args.compile_state,
        "structured_state": args.structured_state,
        "compiler_source": args.compiler_source if args.compile_state else None,
        "rows": rows,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(RUNTIME_ROOT))
    parser.add_argument("--run-id")
    parser.add_argument("--task-mode", choices=sorted(TASKS), default="direct")
    parser.add_argument("--only")
    parser.add_argument("--build-state", action="store_true")
    parser.add_argument("--compile-state", action="store_true")
    parser.add_argument("--structured-state", action="store_true")
    parser.add_argument("--compiler-source", choices=sorted(COMPILER_SOURCES), default="raw_history_docs_strong_decoy")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--rescore", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--llm-provider", default=os.environ.get("GENESIS_ARM_LLM_PROVIDER", "deepseek"))
    parser.add_argument("--llm-api-key", default=os.environ.get("GENESIS_ARM_LLM_API_KEY"))
    parser.add_argument("--llm-base-url", default=os.environ.get("GENESIS_ARM_LLM_BASE_URL"))
    parser.add_argument("--llm-model", default=os.environ.get("GENESIS_ARM_LLM_MODEL"))
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=1200)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
