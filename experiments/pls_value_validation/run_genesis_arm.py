#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

KNOWLEDGE_TOOLS = {
    "search_knowledge_nodes",
    "pls_query",
    "trace_query",
    "record_context_node",
    "record_lesson_node",
    "record_point",
    "record_line",
    "create_meta_node",
    "delete_node",
    "create_graph_node",
    "create_node_edge",
    "record_tool_node",
    "record_discovery",
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def response_to_dict(response: Any) -> dict:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if hasattr(response, "dict"):
        return response.dict()
    return {"response": str(response)}


def clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def build_agent_kwargs(args: argparse.Namespace) -> dict:
    provider = clean(args.llm_provider) or "auto"
    if provider == "auto":
        return {}
    if provider == "deepseek":
        from genesis.core.config import config

        api_key = clean(args.llm_api_key) or clean(config.deepseek_api_key) or clean(os.environ.get("DEEPSEEK_API_KEY"))
        if not api_key:
            raise SystemExit("DEEPSEEK_API_KEY is required for --llm-provider deepseek")
        return {
            "api_key": api_key,
            "base_url": clean(args.llm_base_url) or "https://api.deepseek.com/v1",
            "model": clean(args.llm_model) or "deepseek-chat",
        }
    if provider == "custom":
        api_key = clean(args.llm_api_key)
        base_url = clean(args.llm_base_url)
        model = clean(args.llm_model)
        if not api_key or not base_url or not model:
            raise SystemExit("--llm-api-key, --llm-base-url, and --llm-model are required for --llm-provider custom")
        return {"api_key": api_key, "base_url": base_url, "model": model}
    raise SystemExit(f"Unsupported --llm-provider: {provider}")


def apply_baseline_isolation(agent: Any) -> None:
    for name in KNOWLEDGE_TOOLS:
        agent.tools.unregister(name)

    from genesis.v4.loop import V4Loop
    from genesis.v4.manager import NodeVault
    from genesis.v4.trace_pipeline import runner as trace_runner

    V4Loop._apply_knowledge_routing = lambda self: None
    NodeVault.get_recent_memory = lambda self: ""
    NodeVault.get_daemon_status_summary = lambda self: ""
    NodeVault.generate_l1_digest = lambda self: ""
    trace_runner.generate_experience_summary = lambda: ""


def apply_freeze_knowledge(agent: Any) -> None:
    for name in {
        "record_context_node",
        "record_lesson_node",
        "record_point",
        "record_line",
        "create_meta_node",
        "delete_node",
        "create_graph_node",
        "create_node_edge",
        "record_tool_node",
        "record_discovery",
    }:
        agent.tools.unregister(name)

    from genesis.v4.c_phase import CPhaseMixin
    from genesis.v4.loop import V4Loop

    CPhaseMixin._determine_c_phase_mode = lambda self: "SKIP"
    V4Loop._save_memory = lambda self, final_response: None


def build_prompt(workspace: Path, arm: str, judge_timeout: float) -> str:
    instructions = (workspace / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    judge_cmd = (
        f"python3 {REPO_ROOT / 'experiments/pls_value_validation/rkxor_experiment.py'} judge "
        f"--challenge {workspace / 'challenge.json'} "
        f"--solver-cmd \"python3 solver.py\" "
        f"--timeout {judge_timeout}"
    )
    return f"""You are running one arm of a PLS external capability validation experiment.

Arm: {arm}
Workspace: {workspace}

Hard constraints:
- Work only inside the workspace above.
- Create or update `{workspace / 'solver.py'}`.
- Do not read any `private/` directory, prior RKXOR solver artifact, benchmark JSON, old sandbox artifact, or old challenge report.
- Do not use network access.
- The only acceptance signal is the external judge score.
- Stop when `solver.py` exists and the judge has been run at least once.

{instructions}

Use this exact judge command from any directory:

```bash
{judge_cmd}
```

Return a concise final summary with the final judge score, pass/fail, and what strategy the solver used.
"""


def run_judge(workspace: Path, timeout: float) -> dict:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "experiments/pls_value_validation/rkxor_experiment.py"),
        "judge",
        "--challenge",
        str(workspace / "challenge.json"),
        "--solver-cmd",
        "python3 solver.py",
        "--timeout",
        str(timeout),
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True, timeout=timeout + 10)
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


async def run_arm(args: argparse.Namespace) -> None:
    workspace = Path(args.workspace).resolve()
    if not (workspace / "challenge.json").exists():
        raise SystemExit(f"challenge.json not found in {workspace}")

    os.environ.setdefault("GENESIS_DISABLE_MULTI_G", "1")
    os.environ.setdefault("GENESIS_GP_MAX_ITERATIONS_OVERRIDE", str(args.max_iterations))

    from factory import create_agent

    agent_kwargs = build_agent_kwargs(args)
    agent = create_agent(**agent_kwargs)
    agent.max_iterations = args.max_iterations
    agent.c_phase_blocking = False

    if args.freeze_knowledge:
        apply_freeze_knowledge(agent)
    if args.arm == "baseline":
        apply_baseline_isolation(agent)

    events_path = workspace / f"{args.arm}_events.jsonl"
    events_path.write_text("", encoding="utf-8")

    def callback(event: str, data: Any) -> None:
        payload = {"t": time.time(), "event": event, "data": data}
        with events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    prompt = build_prompt(workspace, args.arm, args.judge_timeout)
    start = time.time()
    response = await agent.process(
        prompt,
        step_callback=callback,
        c_phase_blocking=False,
        loop_config={"disable_multi_g": True},
        initial_knowledge_state={
            "issue": f"PLS external validation {args.arm} RKXOR hidden judge",
            "verified_facts": [],
            "failed_attempts": [],
        },
    )
    elapsed = time.time() - start

    judge_after = None
    if (workspace / "solver.py").exists():
        judge_after = run_judge(workspace, args.judge_timeout)

    result = {
        "arm": args.arm,
        "workspace": str(workspace),
        "elapsed_sec": round(elapsed, 3),
        "freeze_knowledge": args.freeze_knowledge,
        "llm_provider": args.llm_provider,
        "llm_base_url": agent_kwargs.get("base_url"),
        "llm_model": agent_kwargs.get("model"),
        "llm_api_key_present": bool(agent_kwargs.get("api_key")),
        "max_iterations": args.max_iterations,
        "response": response_to_dict(response),
        "post_run_judge": judge_after,
    }
    write_json(workspace / f"{args.arm}_genesis_result.json", result)
    print(json.dumps({"arm": args.arm, "workspace": str(workspace), "elapsed_sec": round(elapsed, 3), "solver_exists": (workspace / "solver.py").exists(), "llm_provider": args.llm_provider, "post_run_judge": judge_after}, ensure_ascii=False, default=str))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=["baseline", "pls"], required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--max-iterations", type=int, default=80)
    parser.add_argument("--judge-timeout", type=float, default=30.0)
    parser.add_argument("--freeze-knowledge", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--llm-provider", choices=["auto", "deepseek", "custom"], default=os.environ.get("GENESIS_ARM_LLM_PROVIDER", "auto"))
    parser.add_argument("--llm-api-key", default=os.environ.get("GENESIS_ARM_LLM_API_KEY"))
    parser.add_argument("--llm-base-url", default=os.environ.get("GENESIS_ARM_LLM_BASE_URL"))
    parser.add_argument("--llm-model", default=os.environ.get("GENESIS_ARM_LLM_MODEL"))
    args = parser.parse_args()
    asyncio.run(run_arm(args))


if __name__ == "__main__":
    main()
