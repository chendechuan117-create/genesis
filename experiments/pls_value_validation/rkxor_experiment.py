#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import random
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

WORDS = """
analysis attack signal cipher plaintext context random hidden sample method verifier window
memory solver score threshold candidate column transpose byte xor distance hamming index english
function return value buffer string integer module branch result evidence judge private public
network model agent surface concept relation path loop error success failure baseline metric
""".split()

CODE_FRAGMENTS = [
    "def score_candidate(buf):\n    return sum(table.get(chr(b), -4) for b in buf)\n",
    "for keysize in range(2, 41):\n    normalized.append((estimate(keysize), keysize))\n",
    "if plaintext_hash == expected_hash:\n    print('verified')\n",
    "candidate = bytes(c ^ key[i % len(key)] for i, c in enumerate(ciphertext))\n",
    "while queue:\n    item = queue.pop(0)\n    seen.add(item)\n",
]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def xor_repeat(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def make_key(rng: random.Random) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(3, 16)))


def make_plaintext(rng: random.Random) -> str:
    target = rng.randint(360, 1100)
    parts: list[str] = []
    while len("".join(parts)) < target:
        mode = rng.random()
        if mode < 0.62:
            n = rng.randint(7, 18)
            sentence = " ".join(rng.choice(WORDS) for _ in range(n))
            parts.append(sentence.capitalize() + rng.choice([". ", "; ", ": ", "\n"]))
        elif mode < 0.82:
            parts.append(rng.choice(CODE_FRAGMENTS))
        else:
            nums = " ".join(str(rng.randint(0, 9999)) for _ in range(rng.randint(4, 12)))
            parts.append(f"metrics [{nums}] status={rng.choice(['ok', 'retry', 'fail', 'pass'])}\n")
    text = "".join(parts)[:target]
    return text.rstrip() + "\n"


def make_case(rng: random.Random, case_id: str, reveal: bool) -> tuple[dict, dict]:
    key = make_key(rng)
    plaintext = make_plaintext(rng)
    cipher = xor_repeat(plaintext.encode("utf-8"), key.encode("utf-8"))
    public = {
        "id": case_id,
        "ciphertext_b64": base64.b64encode(cipher).decode("ascii"),
        "ciphertext_bytes": len(cipher),
    }
    if reveal:
        public["key"] = key
        public["plaintext"] = plaintext
    secret = {
        "id": case_id,
        "key": key,
        "plaintext": plaintext,
        "plaintext_sha256": hashlib.sha256(plaintext.encode("utf-8")).hexdigest(),
        "ciphertext_b64": public["ciphertext_b64"],
    }
    return public, secret


def make_bundle(rng: random.Random, challenge_id: str, public_count: int, hidden_count: int) -> tuple[dict, dict]:
    public_examples = []
    hidden_cases = []
    hidden_secrets = []
    for i in range(public_count):
        public, _ = make_case(rng, f"public_{i:03d}", True)
        public_examples.append(public)
    for i in range(hidden_count):
        public, secret = make_case(rng, f"hidden_{i:03d}", False)
        hidden_cases.append(public)
        hidden_secrets.append(secret)
    challenge = {
        "schema": "pls-rkxor-v1",
        "challenge_id": challenge_id,
        "task": "break_repeating_key_xor_hidden_bundle",
        "solver_contract": "Run as: python solver.py challenge.json answers.json. Write JSON with answers: [{id, key?, plaintext?}].",
        "pass_threshold": 0.85,
        "public_examples": public_examples,
        "hidden_cases": hidden_cases,
    }
    secrets = {"schema": "pls-rkxor-v1-secret", "challenge_id": challenge_id, "hidden_cases": hidden_secrets}
    return challenge, secrets


def instructions(script_path: Path, arm: str) -> str:
    if arm == "baseline":
        rule = "Do not use PLS, NodeVault, prior RKXOR artifacts, old solver files, or prior challenge reports. Treat this as a fresh external task."
    else:
        rule = "You may use compact PLS/NodeVault conceptual memory, but do not read prior RKXOR solver files, benchmark JSON, old sandbox artifacts, or private secrets."
    return f"""# RKXOR {arm} arm

{rule}

Goal: create `solver.py` in this directory. It must read `challenge.json` and write `answers.json` using this contract:

```text
python3 solver.py challenge.json answers.json
```

Use the judge only as an external verifier:

```text
python3 {script_path} judge --challenge challenge.json --solver-cmd "python3 solver.py"
```

The judge result is the only acceptance signal. Prefer a reusable solver over manual answer guessing.
"""


def init_run(args: argparse.Namespace) -> None:
    run_id = args.run_id or time.strftime("run_%Y%m%d_%H%M%S")
    root = (Path(args.out) / run_id).resolve()
    if root.exists():
        raise SystemExit(f"run already exists: {root}")
    public_root = root / "public"
    private_root = root / "private"
    rng = random.Random(args.seed)
    registry: dict[str, str] = {}
    manifest = {"schema": "pls-rkxor-run-v1", "run_id": run_id, "seed": args.seed, "pairs": []}
    script_path = Path(__file__).resolve()
    for pair_index in range(args.pairs):
        pair_name = f"pair_{pair_index:03d}"
        pair_info = {"pair": pair_name, "assignments": {}, "bundles": {}}
        for bundle_name in ("a", "b"):
            challenge_id = f"{run_id}_{pair_name}_bundle_{bundle_name}"
            challenge, secrets = make_bundle(rng, challenge_id, args.public, args.hidden)
            pub_path = public_root / pair_name / f"bundle_{bundle_name}" / "challenge.json"
            sec_path = private_root / pair_name / f"bundle_{bundle_name}" / "secrets.json"
            write_json(pub_path, challenge)
            write_json(sec_path, secrets)
            registry[challenge_id] = str(sec_path.relative_to(private_root))
            pair_info["bundles"][bundle_name] = {"challenge_id": challenge_id}
        baseline_bundle = "a" if pair_index % 2 == 0 else "b"
        pls_bundle = "b" if baseline_bundle == "a" else "a"
        for arm, bundle_name in (("baseline", baseline_bundle), ("pls", pls_bundle)):
            arm_dir = public_root / pair_name / arm
            arm_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(public_root / pair_name / f"bundle_{bundle_name}" / "challenge.json", arm_dir / "challenge.json")
            (arm_dir / "INSTRUCTIONS.md").write_text(instructions(script_path, arm), encoding="utf-8")
            pair_info["assignments"][arm] = {"bundle": bundle_name, "workspace": str(arm_dir)}
        manifest["pairs"].append(pair_info)
    write_json(private_root / "registry.json", registry)
    write_json(root / "run_manifest.json", manifest)
    print(root)


def find_registry(challenge_path: Path, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    for parent in challenge_path.resolve().parents:
        candidate = parent / "private" / "registry.json"
        if candidate.exists():
            return candidate
    raise SystemExit("private registry not found; pass --private-registry")


def normalize_answers(raw: object) -> dict[str, dict]:
    if isinstance(raw, dict) and isinstance(raw.get("answers"), list):
        items = raw["answers"]
    elif isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = []
        for key, value in raw.items():
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", key)
            else:
                item = {"id": key, "plaintext": value}
            items.append(item)
    else:
        return {}
    out = {}
    for item in items:
        if isinstance(item, dict) and item.get("id"):
            out[str(item["id"])] = item
    return out


def plaintext_from_answer(answer: dict, secret: dict) -> str | None:
    if "plaintext" in answer:
        return str(answer["plaintext"])
    if "plaintext_b64" in answer:
        try:
            return base64.b64decode(str(answer["plaintext_b64"])).decode("utf-8")
        except Exception:
            return None
    if "key" in answer:
        try:
            cipher = base64.b64decode(secret["ciphertext_b64"])
            plain = xor_repeat(cipher, str(answer["key"]).encode("utf-8"))
            return plain.decode("utf-8")
        except Exception:
            return None
    return None


def solver_source_path(cmd: list[str], cwd: Path) -> Path | None:
    for token in cmd:
        if token.endswith(".py"):
            path = Path(token)
            return path if path.is_absolute() else cwd / path
    return None


def behavior_markers(cmd: list[str], cwd: Path) -> dict[str, bool]:
    path = solver_source_path(cmd, cwd)
    if not path or not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="ignore").lower()
    patterns = {
        "hamming_or_ioc_keysize": r"hamming|bit_count|index.?of.?coincidence|\bioc\b|normalized",
        "keysize_search": r"key.?size|keysize|range\(2,|range\(3,",
        "transpose_columns": r"transpose|column|columns|\[i::key|%\s*key",
        "single_byte_subroutine": r"single.?byte|range\(256\)|for .* in range\(256\)",
        "beam_or_candidate_set": r"beam|candidate|heapq|nlargest|top_|itertools\.product",
        "public_example_calibration": r"public_examples|threshold|sweep|calibrat|example",
    }
    return {name: bool(re.search(pattern, text)) for name, pattern in patterns.items()}


def judge(args: argparse.Namespace) -> None:
    challenge_path = Path(args.challenge).resolve()
    challenge = read_json(challenge_path)
    registry_path = find_registry(challenge_path, args.private_registry)
    registry = read_json(registry_path)
    challenge_id = challenge["challenge_id"]
    secrets_path = registry_path.parent / registry[challenge_id]
    secrets = read_json(secrets_path)
    cmd = shlex.split(args.solver_cmd)
    with tempfile.TemporaryDirectory(prefix="rkxor_judge_") as tmp:
        output_path = Path(tmp) / "answers.json"
        start = time.time()
        timed_out = False
        try:
            proc = subprocess.run(
                cmd + [str(challenge_path), str(output_path)],
                cwd=challenge_path.parent,
                text=True,
                capture_output=True,
                timeout=args.timeout,
            )
            returncode = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            returncode = None
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
        elapsed = time.time() - start
        raw_answers = read_json(output_path) if output_path.exists() else {}
    answers = normalize_answers(raw_answers)
    case_results = []
    solved = 0
    key_matches = 0
    for secret in secrets["hidden_cases"]:
        answer = answers.get(secret["id"], {})
        plaintext = plaintext_from_answer(answer, secret)
        plaintext_ok = plaintext == secret["plaintext"]
        key_ok = str(answer.get("key", "")) == secret["key"]
        solved += int(plaintext_ok)
        key_matches += int(key_ok)
        case_results.append({"id": secret["id"], "plaintext_ok": plaintext_ok, "key_ok": key_ok})
    total = len(secrets["hidden_cases"])
    score = solved / total if total else 0.0
    markers = behavior_markers(cmd, challenge_path.parent)
    result = {
        "created_at": time.time(),
        "challenge_id": challenge_id,
        "solver_cmd": args.solver_cmd,
        "returncode": returncode,
        "timed_out": timed_out,
        "elapsed_sec": round(elapsed, 3),
        "cases_total": total,
        "solved": solved,
        "key_matches": key_matches,
        "score": score,
        "pass": score >= float(challenge.get("pass_threshold", 0.85)),
        "behavior_markers": markers,
        "behavior_marker_count": sum(1 for value in markers.values() if value),
        "case_results": case_results,
        "stdout_tail": str(stdout)[-2000:],
        "stderr_tail": str(stderr)[-2000:],
    }
    result_path = Path(args.result) if args.result else challenge_path.parent / "last_result.json"
    attempt_log = Path(args.attempt_log) if args.attempt_log else challenge_path.parent / "attempts.jsonl"
    write_json(result_path, result)
    attempt_log.parent.mkdir(parents=True, exist_ok=True)
    with attempt_log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(json.dumps({k: result[k] for k in ("score", "pass", "solved", "cases_total", "behavior_marker_count")}, ensure_ascii=False))


def load_attempts(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(args: argparse.Namespace) -> None:
    root = Path(args.run_dir).resolve()
    manifest = read_json(root / "run_manifest.json")
    rows = []
    for pair in manifest["pairs"]:
        row = {"pair": pair["pair"]}
        for arm in ("baseline", "pls"):
            workspace = Path(pair["assignments"][arm]["workspace"])
            attempts = load_attempts(workspace / "attempts.jsonl")
            best = max(attempts, key=lambda x: x.get("score", 0.0), default={})
            first_pass_index = next((i for i, a in enumerate(attempts) if a.get("pass")), None)
            row[arm] = {
                "calls": len(attempts),
                "best_score": best.get("score"),
                "best_pass": best.get("pass", False),
                "failed_before_first_pass": first_pass_index if first_pass_index is not None else len(attempts),
                "marker_count": best.get("behavior_marker_count"),
            }
        rows.append(row)
    pls_scores = [r["pls"]["best_score"] for r in rows if r["pls"]["best_score"] is not None]
    base_scores = [r["baseline"]["best_score"] for r in rows if r["baseline"]["best_score"] is not None]
    paired = [r for r in rows if r["pls"]["best_score"] is not None and r["baseline"]["best_score"] is not None]
    wins = sum(1 for r in paired if r["pls"]["best_score"] > r["baseline"]["best_score"])
    print(f"run={manifest['run_id']} paired={len(paired)} pls_wins={wins}")
    if pls_scores and base_scores:
        print(f"median_best_score baseline={statistics.median(base_scores):.3f} pls={statistics.median(pls_scores):.3f}")
    for r in rows:
        b = r["baseline"]
        p = r["pls"]
        print(f"{r['pair']} baseline score={b['best_score']} calls={b['calls']} markers={b['marker_count']} | pls score={p['best_score']} calls={p['calls']} markers={p['marker_count']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--out", default="runtime/pls_value_validation")
    p_init.add_argument("--run-id")
    p_init.add_argument("--seed", type=int, default=20260520)
    p_init.add_argument("--pairs", type=int, default=12)
    p_init.add_argument("--public", type=int, default=3)
    p_init.add_argument("--hidden", type=int, default=24)
    p_init.set_defaults(func=init_run)
    p_judge = sub.add_parser("judge")
    p_judge.add_argument("--challenge", required=True)
    p_judge.add_argument("--solver-cmd", required=True)
    p_judge.add_argument("--private-registry")
    p_judge.add_argument("--timeout", type=float, default=30.0)
    p_judge.add_argument("--result")
    p_judge.add_argument("--attempt-log")
    p_judge.set_defaults(func=judge)
    p_summary = sub.add_parser("summarize")
    p_summary.add_argument("--run-dir", required=True)
    p_summary.set_defaults(func=summarize)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
