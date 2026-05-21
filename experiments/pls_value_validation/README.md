# PLS Value Validation Experiment

This is a minimal counterfactual harness for testing whether PLS improves external task ability on private repeating-key XOR challenges.

The harness intentionally separates three things:

- **External result**: hidden judge score and pass/fail.
- **Behavior change**: strategy markers visible in the produced solver.
- **Less wasted path**: judge calls before first pass and best score within budget.

It does not treat PLS node count, logs, or self-reports as success evidence.

## Create a private run

```bash
python3 experiments/pls_value_validation/rkxor_experiment.py init \
  --out runtime/pls_value_validation \
  --run-id pilot_001 \
  --seed 20260520 \
  --pairs 12 \
  --public 3 \
  --hidden 24
```

The command creates:

```text
runtime/pls_value_validation/pilot_001/
  run_manifest.json
  public/pair_000/baseline/challenge.json
  public/pair_000/baseline/INSTRUCTIONS.md
  public/pair_000/pls/challenge.json
  public/pair_000/pls/INSTRUCTIONS.md
  private/registry.json
  private/pair_000/bundle_a/secrets.json
```

Only `public/*/{baseline,pls}` should be given to the solving agent. The `private` directory is for the judge only.

## Run a solver against the judge

Inside any arm workspace, create `solver.py` with this contract:

```text
python3 solver.py challenge.json answers.json
```

Then run:

```bash
python3 /home/chendechusn/Genesis/Genesis/experiments/pls_value_validation/rkxor_experiment.py judge \
  --challenge challenge.json \
  --solver-cmd "python3 solver.py"
```

The judge appends each attempt to `attempts.jsonl` and writes `last_result.json`.

## Summarize a run

```bash
python3 experiments/pls_value_validation/rkxor_experiment.py summarize \
  --run-dir runtime/pls_value_validation/pilot_001
```

## Run one Genesis arm

Baseline removes PLS/NodeVault tools and strips prompt-facing memory surfaces. PLS keeps read-side PLS memory, but freezes writeback by default so the pilot measures current memory activation rather than trial-time node production.

```bash
venv/bin/python experiments/pls_value_validation/run_genesis_arm.py \
  --arm baseline \
  --workspace runtime/pls_value_validation/pilot_001/public/pair_000/baseline \
  --max-iterations 80 \
  --llm-provider deepseek
```

```bash
venv/bin/python experiments/pls_value_validation/run_genesis_arm.py \
  --arm pls \
  --workspace runtime/pls_value_validation/pilot_001/public/pair_000/pls \
  --max-iterations 80 \
  --llm-provider deepseek
```

Use `--llm-provider deepseek` when the default xcode failover route returns subscription errors. The runner also supports `--llm-provider custom --llm-api-key ... --llm-base-url ... --llm-model ...`.

Each arm writes:

```text
solver.py
attempts.jsonl
last_result.json
baseline_genesis_result.json / pls_genesis_result.json
baseline_events.jsonl / pls_events.jsonl
```

## Arm rules

### Baseline

Fresh context. Do not use PLS, NodeVault, old RKXOR artifacts, prior solver files, benchmark JSON, or prior reports.

### PLS

PLS conceptual memory is allowed. Old RKXOR solver files, benchmark JSON, sandbox artifacts, and private secrets are not allowed.

## Primary acceptance signal

A PLS win requires external judge improvement, not more memory activity:

```text
PLS best hidden score > baseline best hidden score on most paired trials
PLS median best score - baseline median best score >= 0.15
PLS pass rate - baseline pass rate >= 0.25
```

## Secondary signals

The harness records:

- **failed_before_first_pass**: judge calls before the first passing attempt.
- **calls**: total judge attempts.
- **behavior_marker_count**: static markers in the submitted solver.
- **marker names**: Hamming/IoC keysize estimation, keysize search, transposition, single-byte subroutine, candidate beam, public-example calibration.

These are not sufficient alone. They support the causal claim only when the hidden judge also improves.
