# ChapterStateBuilder Integration Contract

## Purpose

`ChapterStateBuilder` exists to compile current project history into a typed chapter state for a fresh LLM.

It is not a memory retriever, task planner, benchmark optimizer, or replacement for PLS surface search.

The contract is:

```text
SourceLane[] -> ChapterState -> renderer -> LLM context packet
```

The builder must preserve the current conceptual chapter, especially:

- Current canon
- Evidence behind the canon
- Deprecated directions
- User value boundaries
- Stale concrete action items
- Active next question
- Source references for auditability

## Non-goals

`ChapterStateBuilder` must not:

- Read arbitrary global history by itself
- Query NodeVault directly in the first integration step
- Mutate NodeVault or write C-phase conclusions
- Decide task execution
- Replace `search_knowledge_nodes` or PLS surface expansion
- Inject raw history dumps into the prompt
- Optimize PLS for external benchmark pass rate
- Treat stale action items as current instructions

## Data model

### SourceLane

A `SourceLane` is an explicit input lane selected by an upstream collector.

Minimum fields:

```text
id: stable lane identifier
kind: canon_doc | user_correction | experiment_result | stale_action_candidate | deprecated_direction | chronological_history
text: lane content
trust: 0.0-1.0 trust score
recency: current_session | current_docs | stale_or_adversarial | historical
source_path: file path, runtime artifact path, node id, or conversation marker
```

Important rule:

> The builder consumes lanes. It does not discover lanes.

This keeps source selection separate from state compilation.

### ChapterState

Minimum fields:

```text
canon: list[str]
evidence: list[str]
deprecated: list[str]
boundaries: list[str]
stale_actions: list[str]
active_question: str
source_refs: list[{source: str, claim: str}]
```

Field meanings:

- **canon**: Current accepted identity and direction.
- **evidence**: Why the canon is current.
- **deprecated**: Directions rejected by newer evidence or user correction.
- **boundaries**: What the next assistant must not do.
- **stale_actions**: Concrete old action items that look executable but are not current direction.
- **active_question**: The natural next topic of this conceptual chapter.
- **source_refs**: Audit trail connecting claims to source lanes.

## Responsibilities

### Upstream source collector

Responsible for selecting `SourceLane[]`.

Possible later sources:

- Recent user corrections
- Active design docs
- Validated code observations
- Recent experiment summaries
- CONTRADICTS/deprecated edges
- Recent high-trust lessons
- Explicit stale action candidates

The collector may read NodeVault, docs, runtime artifacts, or conversation summaries.

The builder should not do that directly.

### ChapterStateBuilder

Responsible for compiling lanes into `ChapterState`.

It may:

- Prefer high-trust current lanes over stale lanes
- Preserve stale actions under `stale_actions`
- Promote user corrections into boundaries
- Attach `source_refs`
- Emit a compact typed state

It must not:

- Execute tasks
- Decide tool calls
- Mutate persistent memory
- Hide contradictory evidence by deletion
- Collapse stale action items into active plans

### Renderer

Responsible for turning `ChapterState` into a prompt packet.

The renderer should:

- Preserve section labels
- Keep stale actions visibly stale
- Keep deprecated directions visibly deprecated
- Include source refs only when budget allows
- Avoid dumping full raw lane text unless explicitly requested

Renderer output shape:

```text
CURRENT PLS CHAPTER STATE

CANON
- ...

EVIDENCE
- ...

DEPRECATED
- ...

BOUNDARIES
- ...

STALE ACTIONS
- ...

ACTIVE QUESTION
- ...

SOURCE REFS
- source_id: claim
```

## Coupling boundaries

Initial integration must be one-way:

```text
collector -> SourceLane[] -> builder -> ChapterState -> renderer -> prompt
```

Forbidden initial couplings:

- `ChapterStateBuilder -> NodeVault.create_node`
- `ChapterStateBuilder -> C-phase extraction`
- `ChapterStateBuilder -> provider/router`
- `ChapterStateBuilder -> tool registry`
- `ChapterStateBuilder -> auto_mode task selection`
- `ChapterStateBuilder -> PLS surface mutation`

Allowed later coupling, behind explicit interfaces:

- Source collector may query NodeVault read-only
- Renderer may be called by prompt assembly
- Builder output may be logged as runtime artifact
- C-phase may later review builder output, but not in the first integration

## Prompt budget rule

`ChapterState` must be compact.

Suggested first budget:

```text
canon: <= 5 bullets
evidence: <= 5 bullets
deprecated: <= 5 bullets
boundaries: <= 5 bullets
stale_actions: <= 5 bullets
active_question: 1 sentence
source_refs: <= 8 refs, optional under tight budget
```

If budget is tight, drop `source_refs` first, not `boundaries` or `deprecated`.

## Anti-decoy invariant

If a lane contains concrete old action items that conflict with newer user correction or canon, the builder must put them in `stale_actions` or `deprecated`, not in `active_question`.

Example stale actions from the current experiment:

- Continue Cryptopals after RKXOR
- Build `disciplined_pls`
- Tune negative surface prompts until PLS beats baseline
- Treat hidden judge improvement as primary proof of PLS value
- Use old RKXOR artifacts to help the next solver

The current chapter must preserve that these are tempting boxes, not the pearl.

## Acceptance test

A candidate integration passes the minimum test if:

1. It builds a `ChapterState` from explicit `SourceLane[]`.
2. Rendering the state plus strong stale-action decoys still leads a fresh LLM to choose the current `active_question`.
3. The fresh LLM identifies stale crypto/benchmark actions as misleading.
4. No production state is mutated.
5. Source references are auditable.

Current local evidence:

- `pilot_open_next_strong_20260520_1331`: raw docs/history were hijacked by strong crypto decoys; manual chapter state resisted.
- `pilot_structured_state_20260520_1347`: structured JSON `ChapterState` rendered back to a packet and scored 10/10.
- `pilot_source_lane_builder_20260520_1401`: deterministic source-lane builder preserved the builder validation topic and rejected stale crypto actions.

## Next safe step

Before production integration, split the experiment into isolated modules or keep this contract as the only bridge:

```text
chapter_state_model.py
source_lanes.py
builder.py
renderer.py
run_chapter_state_recovery.py
```

Do not import these from Genesis runtime until the collector, builder, renderer, and budget contracts are separately tested.
