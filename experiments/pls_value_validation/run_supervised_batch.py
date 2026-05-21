from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
ARM_SCRIPT = REPO_ROOT / "experiments/pls_value_validation/run_genesis_arm.py"
JUDGE_SCRIPT = REPO_ROOT / "experiments/pls_value_validation/rkxor_experiment.py"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def parse_judge(stdout: str) -> dict[str, Any]:
    try:
        value = json.loads(stdout or "{}")
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def judge_workspace(workspace: Path, timeout: float) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(JUDGE_SCRIPT),
        "judge",
        "--challenge",
        str(workspace / "challenge.json"),
        "--solver-cmd",
        "python3 solver.py",
        "--timeout",
        str(timeout),
    ]
    try:
        proc = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True, timeout=timeout + 10)
        return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "parsed": parse_judge(proc.stdout)}
    except subprocess.TimeoutExpired as e:
        return {"returncode": None, "stdout": e.stdout or "", "stderr": e.stderr or "", "timeout_expired": True, "parsed": {}}


def terminate_group(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.time() + 5
    while time.time() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.2)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def arm_result(path: Path) -> dict[str, Any] | None:
    data = read_json(path)
    if not data:
        return None
    judge = data.get("post_run_judge") or {}
    return {
        "elapsed_sec": data.get("elapsed_sec"),
        "iterations": (data.get("response") or {}).get("iterations"),
        "total_tokens": (data.get("response") or {}).get("total_tokens"),
        "judge": {**judge, "parsed": parse_judge(judge.get("stdout") or "")},
    }


def command(args: argparse.Namespace, arm: str, workspace: Path) -> list[str]:
    cmd = [
        sys.executable,
        str(ARM_SCRIPT),
        "--arm",
        arm,
        "--workspace",
        str(workspace),
        "--max-iterations",
        str(args.max_iterations),
        "--judge-timeout",
        str(args.judge_timeout),
        "--llm-provider",
        args.llm_provider,
    ]
    if args.llm_api_key:
        cmd += ["--llm-api-key", args.llm_api_key]
    if args.llm_base_url:
        cmd += ["--llm-base-url", args.llm_base_url]
    if args.llm_model:
        cmd += ["--llm-model", args.llm_model]
    return cmd


def run_one(args: argparse.Namespace, pair: Path, arm: str) -> dict[str, Any]:
    workspace = pair / arm
    result_path = workspace / f"{arm}_genesis_result.json"
    supervised_path = workspace / f"{arm}_supervised_result.json"
    existing_supervised = read_json(supervised_path)
    if args.skip_existing and existing_supervised and existing_supervised.get("status") in {
        "existing_arm_result",
        "existing_solver_judged",
        "arm_completed",
        "pass_terminated",
        "wall_timeout",
        "process_exited",
    }:
        existing_supervised["skipped"] = True
        return existing_supervised
    existing = arm_result(result_path)
    if args.skip_existing and existing:
        result = {"pair": pair.name, "arm": arm, "status": "existing_arm_result", "workspace": str(workspace), "arm_result": existing}
        write_json(supervised_path, result)
        return result
    if args.adopt_existing_solver and (workspace / "solver.py").exists():
        judge = judge_workspace(workspace, args.judge_timeout)
        result = {"pair": pair.name, "arm": arm, "status": "existing_solver_judged", "workspace": str(workspace), "judge": judge}
        write_json(supervised_path, result)
        return result

    start = time.time()
    stdout_path = workspace / f"{arm}_supervisor_stdout.log"
    stderr_path = workspace / f"{arm}_supervisor_stderr.log"
    judge_history: list[dict[str, Any]] = []
    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
        proc = subprocess.Popen(command(args, arm, workspace), cwd=REPO_ROOT, text=True, stdout=out, stderr=err, start_new_session=True)
        status = "running"
        stop_reason = ""
        last_judge = 0.0
        while True:
            elapsed = time.time() - start
            completed = arm_result(result_path)
            if completed:
                status = "arm_completed"
                stop_reason = "arm_result_written"
                break
            if (workspace / "solver.py").exists() and elapsed - last_judge >= args.judge_interval:
                last_judge = elapsed
                judge = judge_workspace(workspace, args.judge_timeout)
                judge["elapsed_sec"] = round(elapsed, 3)
                judge_history.append(judge)
                if (judge.get("parsed") or {}).get("pass") is True:
                    terminate_group(proc)
                    status = "pass_terminated"
                    stop_reason = "external_judge_passed"
                    break
            if proc.poll() is not None:
                status = "process_exited"
                stop_reason = f"returncode={proc.returncode}"
                break
            if elapsed >= args.arm_timeout:
                terminate_group(proc)
                status = "wall_timeout"
                stop_reason = f"arm_timeout={args.arm_timeout}"
                break
            time.sleep(args.poll_interval)

    final_arm = arm_result(result_path)
    final_judge = None if final_arm or not (workspace / "solver.py").exists() else judge_workspace(workspace, args.judge_timeout)
    result = {
        "pair": pair.name,
        "arm": arm,
        "status": status,
        "stop_reason": stop_reason,
        "workspace": str(workspace),
        "elapsed_sec": round(time.time() - start, 3),
        "solver_exists": (workspace / "solver.py").exists(),
        "answers_exists": (workspace / "answers.json").exists(),
        "arm_result": final_arm,
        "judge_history": judge_history,
        "final_judge": final_judge,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    write_json(supervised_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--pairs", default="")
    parser.add_argument("--arms", default="baseline,pls")
    parser.add_argument("--max-iterations", type=int, default=80)
    parser.add_argument("--arm-timeout", type=float, default=420.0)
    parser.add_argument("--judge-interval", type=float, default=20.0)
    parser.add_argument("--judge-timeout", type=float, default=30.0)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--llm-provider", choices=["auto", "deepseek", "custom"], default=os.environ.get("GENESIS_ARM_LLM_PROVIDER", "deepseek"))
    parser.add_argument("--llm-api-key", default=os.environ.get("GENESIS_ARM_LLM_API_KEY"))
    parser.add_argument("--llm-base-url", default=os.environ.get("GENESIS_ARM_LLM_BASE_URL"))
    parser.add_argument("--llm-model", default=os.environ.get("GENESIS_ARM_LLM_MODEL"))
    parser.add_argument("--skip-existing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--adopt-existing-solver", action=argparse.BooleanOptionalAction, default=False)
    args = parser.parse_args()

    public = Path(args.run_dir).resolve() / "public"
    selected_pairs = {item.strip() for item in args.pairs.split(",") if item.strip()}
    selected_arms = {item.strip() for item in args.arms.split(",") if item.strip()}
    batch_path = public.parent / "supervised_batch_results.jsonl"
    for pair in sorted(public.glob("pair_*")):
        if selected_pairs and pair.name not in selected_pairs:
            continue
        for arm in ("baseline", "pls"):
            if arm not in selected_arms:
                continue
            print(f"RUN {pair.name} {arm}", flush=True)
            result = run_one(args, pair, arm)
            with batch_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
            parsed = (((result.get("arm_result") or {}).get("judge") or result.get("judge") or result.get("final_judge") or {}).get("parsed") or {})
            print(f"DONE {pair.name} {arm} status={result.get('status')} score={parsed.get('score')} pass={parsed.get('pass')}", flush=True)


if __name__ == "__main__":
    main()
