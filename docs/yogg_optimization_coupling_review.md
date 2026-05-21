# Yogg Optimization Coupling Review

> Date: 2026-05-20
> Scope: Review-only design note. No runtime/code changes were made while producing this note.

## Purpose

This note records a reviewed position on possible Yogg optimization directions, with special attention to coupling boundaries and whether existing couplings are intentional design or accidental/historical debt.

The main correction from the initial review is that some earlier recommendations were too strong or partially outdated. In particular, the basic evidence gate is already implemented in `NodeVault.create_node()` and covered by tests. The near-term optimization target should not be “add another controller”, but rather reduce accidental prompt/history coupling while preserving intentional weak couplings.

## Current Judgment

Yogg should be optimized by clarifying coupling boundaries, not by immediately replacing its control loop.

The most promising near-term direction is a low-permission ChapterState/current-state rendering layer:

```text
collector -> SourceLane[] -> builder -> ChapterState -> renderer -> prompt
```

This layer should help the sampled LLM understand the current chapter, stale actions, deprecated directions, active question, and evidence boundaries. It should not query or mutate NodeVault, decide tool calls, replace PLS, or become a new scheduler.

## Coupling Map

### Intentional Couplings

#### Yogg runner -> auto_mode

`yogg_auto.py` is intentionally coupled to `run_auto()` for process lifecycle, logging, crash guard, memory guard, and systemd restart behavior.

This is a healthy coupling because it is operational, not semantic. The runner should not understand PLS or decide cognition.

#### auto_mode -> PLS terrain / branch proposals

`auto_mode.py` intentionally injects PLS terrain/scout/proposal summaries into `signals`.

The design intent is that PLS provides attention candidates, not facts or commands. This is useful, but high-risk if wording turns “potential” into “task instruction”.

Correct boundary:

```text
PLS gives affordance / hunch / maybe.
PLS must not give mandate / checklist / proof.
```

#### NodeVault.create_node -> evidence gate

The evidence gate is intentionally centralized in `NodeVault.create_node()`.

Verified current behavior:

- `genesis/v4/manager.py` normalizes `evidence_refs`.
- `validation_status=validated` is downgraded to `partial` when no hard evidence is present.
- `validation_gate=missing_hard_evidence` is added on downgrade.
- `tests/test_point_line_surface_p0.py` covers both no-evidence downgrade and evidence-backed validation.

This is a good coupling because trust policy should converge at the single write gateway.

#### V6 shadow -> V4Loop

V6 signature shadow is intentionally weakly coupled to `V4Loop`.

Current behavior is record-only:

```text
mode = shadow_only
no routing
no filtering
no prompt injection
```

This is the correct current posture. V6 should remain shadow/calibration first. Hard gating before calibration risks creating a new bias source.

#### TopicTracker / fallback -> prompt

`TopicTracker`, dry warnings, fallback focus, and template saturation detection are intentional safety/control layers.

They exist to prevent repeated verification, mode collapse, and self-referential loops. They should not be deleted casually. However, they should remain guardrails/fuses rather than the primary navigation engine.

### Semi-Intentional Couplings Requiring Care

#### PLS terrain -> signals -> prompt

This coupling is useful but fragile.

Risk:

```text
candidate terrain becomes semantic terrain
semantic terrain becomes task directive
```

Optimization should focus on wording and rendering: keep PLS content as weak affordance, not imperative instruction.

#### VOID -> fallback focus

VOID tasks are intentionally used as knowledge gaps. Current lifecycle is not zero: `open`, `resolved`, and `stale` exist, and `create_node()` can resolve matching VOID tasks.

Remaining gap:

- no robust dedupe key
- no occurrence count
- no last_seen tracking
- no observed/ignored states
- weak substring-style resolution
- no dry-run maintenance preview comparable to `potential_samples`

So the target is not “add VOID lifecycle from scratch”, but “complete and audit VOID lifecycle”.

#### consecutive_dry -> carry_warnings / switching pressure

Dry logic exists for real reasons, especially on long-running Yogg. But sandbox diff is not a perfect measure of conceptual progress.

The correct direction is to avoid using dry count as the dominant navigation signal. It should warn or fuse, not decide the whole cognitive path.

### Accidental or Historical-Debt Couplings

#### Raw SQL bypass around reasoning_lines / node_edges

Any direct SQL path that writes `reasoning_lines` or `node_edges` without NodeVault guards is accidental coupling and should be audited.

Correct future step is read-only bypass audit and dry-run report, not immediate live cleanup.

#### Hidden/virtual endpoint historical debt

Historical rows can still contain hidden or virtual endpoints. Current local code has stronger active-only filtering and write guards, but live Yogg may contain old debt.

This is data debt, not a reason to redesign the whole control loop.

#### reasoning_lines schema drift

Live historical observations reported unreliable/null `line_id`. Local schema now has `line_id INTEGER PRIMARY KEY AUTOINCREMENT`.

If maintenance needs exact line IDs, create a dry-run migration plan first. Do not make this a near-term runtime optimization.

#### Operational telemetry becoming semantic terrain

Counts such as rows, missing_dedupe, total, seen, last_seen, etc. should not become GP semantic prompts.

This has been partially addressed in `pls_async_scout`, but it remains a design invariant to preserve.

## Revised Optimization Priorities

### 1. Add a read-only ChapterState/current-state rendering layer

This is the most elegant near-term optimization because it addresses stale-history/action hijack without taking control away from PLS or auto_mode.

Required constraints:

- Builder consumes explicit `SourceLane[]` only.
- Builder does not discover sources.
- Builder does not query NodeVault.
- Builder does not write C-phase conclusions.
- Builder does not decide tool calls.
- Renderer emits a bounded prompt packet only.
- It must not replace PLS search/surface.

Suggested packet fields:

```text
active_question
current_chapter
stale_actions
deprecated_directions
evidence_boundaries
open_uncertainties
next_decision_boundary
```

### 2. Keep V6 in shadow/calibration mode

V6 direction remains valuable, but the next step should be evaluation, not gating.

Possible calibration questions:

- Does shadow prediction correlate with actual successful tool/action path?
- Does it predict signature dimensions better than frequency baseline on recent Yogg data?
- Does it detect self-referential tunnel risk?
- Can it propose soft priors without reducing exploration diversity?

Hard gating should remain deferred until shadow metrics are trustworthy.

### 3. Strengthen evidence quality, not the existence of the evidence gate

Basic evidence gate already exists.

Remaining improvement is anti-gaming / quality validation:

- `evidence_refs` should include concrete excerpt or observation, not only `type`.
- File evidence should include path and relevant excerpt.
- Command evidence should include command and output excerpt.
- Trace evidence should include trace id and relevant span/result excerpt.
- Weak or empty evidence should not preserve `validated`.

### 4. Add VOID dry-run maintenance and lifecycle completion

Do not directly mutate live DB first.

Read-only report should summarize:

- duplicate open VOID groups
- repeated occurrence candidates
- open VOID likely resolved by existing nodes
- stale VOID candidates
- VOID without meaningful query text
- status distribution over time

### 5. Audit historical topology debt only after higher-level state anchoring

Topology cleanup is useful but not the best first optimization.

Do it as dry-run reports:

- orphan reasoning lines
- orphan node edges
- hidden/virtual endpoint debt
- self-loop edges
- noncanonical relation values
- null/invalid line IDs
- raw SQL bypass writers

## What Not To Do Yet

- Do not replace auto_mode with V6 MLP gating.
- Do not make PLS terrain mandatory instructions.
- Do not delete TopicTracker/fallback logic without replacement guardrails.
- Do not run live topology cleanup before dry-run reports.
- Do not treat ChapterState as a scheduler or NodeVault writer.
- Do not confuse “evidence gate exists” with “evidence quality is solved”.

## Final Recommendation

The cleanest next evolution is a narrow, one-way ChapterState prompt-rendering layer plus continued V6 shadow evaluation.

This preserves intentional couplings:

```text
Yogg handles lifecycle.
auto_mode handles loop orchestration.
PLS provides weak attention affordances.
NodeVault centralizes trust/write policy.
V6 observes and learns silently.
ChapterState renders current state only.
```

And it avoids creating a new overpowered controller before the current coupling boundaries are stable.
