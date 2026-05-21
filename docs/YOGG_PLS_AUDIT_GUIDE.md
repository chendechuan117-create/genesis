# Yogg PLS Comprehensive Audit Guide

Last updated: 2026-05-13

This file is the follow-up guidance document for the Yogg Point-Line-Surface (PLS) audit. It records what was verified, what was fixed, what remains unresolved, and how future work should proceed without losing the current audit context.

The central conclusion is:

```text
potential_samples and pls_proposals now follow the candidate-before-fact lifecycle for new writes.
Default PLS read/count/write paths are active-only in current local code; hidden/virtual rows remain a historical data and explicit-integrity-mode concern.
The 2026-05-12 Yogg content drift was not caused by direct GP use of pls_query; it was a combined provider-error/planner-fallback/internal-knowledge-first/write-trust-gate failure.
PLS terrain should be treated as a candidate generator, not as a validation source for facts.
Validated knowledge must require hard external evidence anchors; reflection/internal topology alone must not be enough.
```

---

## 1. Safety rules for future PLS work

- **Default mode**: read-only audit first.
- **Live DB**: `/home/yoga/.genesis/workshop_v4.sqlite` on Yogg.
- **Remote Python**: `/home/yoga/Genesis/venv/bin/python`.
- **No destructive live DB writes** unless explicitly requested and preceded by a dry-run report.
- **No service restart** unless explicitly requested.
- **Never let operational telemetry become semantic terrain**. Counts such as `missing_dedupe`, `rows`, `seen`, `last_seen`, `dedupe`, or guardrail totals must not be injected into GP/auto-mode branch suggestions.
- **Never let PLS terrain validate itself**. `search_knowledge_nodes`, `trace_query`, `pls_query`, `pls_async_scout`, and branch proposals may suggest candidates, but cannot alone justify `validation_status=validated`.
- **Never allow fallback/error rounds to create validated concept nodes**. Provider errors, planner fallback, and dry-streak recovery should default new knowledge to candidate/partial/unverified unless external evidence is explicitly attached.
- **Default visibility should be active-only** unless the command is explicitly an integrity/maintenance audit:

```text
active_only := COALESCE(ablation_active, 0) = 0 AND COALESCE(is_virtual, 0) = 0
```

---

## 2. PLS component map

PLS is not only `potential_samples`. Future audits must cover all layers below.

### Points

- Table: `knowledge_nodes`
- Important columns:
  - `node_id`
  - `type`
  - `ablation_active`
  - `is_virtual`
  - `created_at`
- Key issue: hidden/virtual points are present at meaningful scale as historical debt. Default PLS paths now exclude them unless an explicit integrity/maintenance mode opts in.

### Lines

- Table: `reasoning_lines`
- Important columns:
  - `line_id`
  - `new_point_id`
  - `basis_point_id`
  - `same_round`
  - `trace_id`
  - `round_seq`
  - `source`
- Current status: `create_reasoning_line()` rejects missing endpoints, self-lines, and hidden/virtual endpoints by default. Explicit maintenance/audit callers may opt in with `allow_hidden` / `allow_virtual`.

### Surface

- Main file: `genesis/v4/surface.py`
- Main class: `SurfaceExpander`
- Main methods:
  - `expand_surface()`
  - `_fill_phase()`
  - `_collect_frontier()`
  - `_push_phase()`
  - `_build_potential_samples()`
  - `_get_ablation_ids()`
- Current behavior:
  - Surface expansion uses active-only incoming counts, active-only neighbor maps, and `get_excluded_ids()` to filter hidden/virtual nodes downstream.
  - This protects the default GP surface; historical inactive endpoint debt still requires dry-run maintenance before cleanup.

### Topology edges

- Table: `node_edges`
- Important columns:
  - `source_id`
  - `target_id`
  - `relation`
  - `weight`
- Current status: `add_edge()` / `create_node_edge()` normalize relations and reject missing, self, and hidden/virtual endpoints by default. Explicit maintenance/audit callers may opt in with `allow_hidden` / `allow_virtual`.

### Potential samples

- Table: `potential_samples`
- Main methods in `genesis/v4/manager.py`:
  - `record_potential_samples()`
  - `resolve_potential_sample()`
  - `get_open_potential_samples()`
  - `crystallize_potential_samples_for_node()`
  - `preview_potential_sample_maintenance()`
- Current status:
  - New writes are mostly under lifecycle guardrails.
  - Historical rows still carry large debt.
  - `record_point` defaults to `CONTEXT`; `LESSON` is reserved for stronger crystallized knowledge.

### Proposals

- Table: `pls_proposals`
- Main file: `genesis/tools/pls_async_scout.py`
- Main paths:
  - `build_pls_terrain_brief()`
  - `build_pls_branch_proposals()`
  - `stage_pls_branch_proposals()`
- Current status:
  - Live Yogg had `pls_proposals = 0` during audit.
  - Async scout is mainly read-only unless staging is invoked.
  - Proposal payloads default to `CONTEXT` and remain staging candidates until validated/merged.

### VOID tasks

- Table: `void_tasks`
- Key issue: backlog exists, with no strong lifecycle closure equivalent to potential samples.

### Ablation

- Table: `ablation_baselines`
- Current status: active baseline integrity is mostly good; hidden/virtual endpoint rows remain historical topology debt, but default PLS basis counting and ordinary write contracts now exclude them.

---

## 3. Current live audit snapshot

Observed during 2026-05-11 Yogg audit. Values may drift as Yogg continues running.

### Table counts

```json
{
  "knowledge_nodes": 4891,
  "reasoning_lines": 6390,
  "node_edges": 8777,
  "point_creation_context": 2871,
  "potential_samples": 26471,
  "pls_proposals": 0,
  "void_tasks": 799,
  "ablation_baselines": 618
}
```

### Node visibility

```json
{
  "ablation_active=0": 4274,
  "ablation_active=2": 617,
  "is_virtual=0": 4307,
  "is_virtual=1": 584
}
```

### Potential lifecycle summary

```json
{
  "total_rows": 26471,
  "missing_dedupe": 26360,
  "active_open": 26005,
  "actionable_open": 2494,
  "non_actionable_open": 23511,
  "bad_occurrence_count": 0
}
```

Interpretation:

- New writes after guardrail were clean: `missing_dedupe = 0` for recent rows.
- Historical debt is huge: most `open` potential rows are non-actionable structural/exit terrain signals.
- This is legacy data debt, not necessarily ongoing new-zombie generation.

### Potential invariant checks

```json
{
  "invalid_status": [],
  "observed_resolved_leaks": 0,
  "closed_without_resolved_at": 0,
  "crystallized_non_actionable": 257,
  "active_duplicate_dedupe_groups": 0
}
```

Interpretation:

- The main status semantics are now sane.
- Historical `crystallized_non_actionable = 257` remains a data correctness debt.

### Topology integrity snapshot

```json
{
  "reasoning_lines_missing_new_points": 8,
  "reasoning_lines_missing_basis_points": 4,
  "reasoning_lines_self_loops": 0,
  "reasoning_lines_null_trace_round": 20,
  "reasoning_lines_hidden_or_virtual_endpoints": 4189,
  "node_edges_missing_sources": 529,
  "node_edges_missing_targets": 4,
  "node_edges_self_loops": 5,
  "node_edges_hidden_or_virtual_endpoints": 4695
}
```

Interpretation:

- Orphan lines/edges are mostly historical debt.
- Hidden/virtual endpoint usage is both historical and still possible in current code.

### Visibility leakage in current metrics

A critical finding:

```json
{
  "basis_query_top_hidden_count": [
    {
      "hidden_rows_in_top12": 12,
      "total_top12": 12
    }
  ]
}
```

Meaning:

```text
pls_query basis top 12 were all ablation_active=2 hidden nodes.
```

This makes current basis metrics misleading unless active-only filtering is added.

### Recent hidden endpoint writes after potential guardrail work

```json
{
  "hidden_lines": 6,
  "hidden_edges": 9
}
```

Meaning:

```text
Current code can still create new PLS lines/edges involving hidden/virtual endpoints.
```

### VOID state

```json
{
  "open_total": 796,
  "resolved_missing_node": 0,
  "duplicate_open_query_groups": 0
}
```

Interpretation:

- `void_tasks` has a real open backlog.
- It is not merely duplicate query spam.
- It needs a lifecycle closure design.

### Reasoning line schema drift

Live schema showed:

```text
reasoning_lines.line_id TEXT PRIMARY KEY
```

But most rows have:

```json
{
  "line_id_null_total": 6400,
  "line_id_nonnull_total": 4
}
```

Interpretation:

- `line_id` is not reliable on live Yogg.
- Code mostly queries by endpoint, so this is not an immediate runtime break.
- It becomes dangerous for future exact maintenance, merge, delete, or audit operations.

---

## 4. What has already been fixed

### 4.1 potential_samples lifecycle guardrails

Implemented in `genesis/v4/manager.py` and `genesis/tools/pls_query_tool.py`:

- Stable dedupe keys for new potential rows.
- `occurrence_count` and `last_seen_*` update on duplicates.
- `observed` terrain signals are not treated as open actionable work.
- `get_open_potential_samples()` excludes `observed`.
- `crystallize_potential_samples_for_node()` only crystallizes actionable open/actionable rows.
- `preview_potential_sample_maintenance()` gives dry-run maintenance visibility.
- `pls_query potential` shows lifecycle guardrail summary.

Associated tests:

- `tests/test_point_line_surface_p0.py`

### 4.2 async scout telemetry leak fixed

Fixed in `genesis/tools/pls_async_scout.py`:

- `_strip_numeric_terrain()` now strips operational metadata before scout summaries and branch proposals.
- Guardrail/distribution fields filtered include:
  - `total=`
  - `rows=`
  - `seen=`
  - `missing_dedupe=`
  - `active_open=`
  - `actionable_open=`
  - `non_actionable_open=`
  - `last_seen=`
  - `dedupe:`

Regression test:

- `tests/test_pls_async_proposals.py::test_potential_guardrail_metrics_are_not_branch_seeds`

Remote Yogg validation:

```text
py_compile passed
tests/test_pls_async_proposals.py: 9 passed
live build_pls_terrain_brief/build_pls_branch_proposals: no metadata leak
```

Remote backups:

```text
/home/yoga/Genesis/.cascade_backups/pls_scout_guardrail_filter_20260511_074418
/home/yoga/Genesis/.cascade_backups/pls_scout_guardrail_filter2_20260511_074833
```

### 4.3 proposal/point default lifecycle alignment

Verified in current local code:

- `record_point` defaults `point_type` to `CONTEXT`.
- async branch proposal payloads default `point_type` to `CONTEXT`.
- `NodeVault._normalize_pls_proposal_payload()` defaults invalid/missing proposal `point_type` to `CONTEXT`.
- proposal preview keeps the planned point write as `CONTEXT` unless explicitly validated otherwise.

Regression tests:

- `tests/test_point_line_surface_p0.py`
- `tests/test_pls_async_proposals.py`

### 4.4 default active-only visibility/write contracts

Verified in current local code:

- `create_reasoning_line()` rejects hidden/virtual endpoints by default.
- `add_edge()` and `create_node_edge()` reject hidden/virtual endpoints by default.
- `get_incoming_line_count()`, `get_incoming_line_counts_batch()`, `get_incoming_count_percentile()`, `get_basis_set_for_node()`, and `get_neighbor_map()` are active-only by default.
- `PLSQueryTool` supports explicit `include_hidden` / `include_virtual` integrity views, but defaults to active-only.
- `pls_query` is registered but blocked from default GP tool exposure by `GP_BLOCKED_TOOLS`.
- `search_knowledge_nodes` and preloaded PLS context expose qualitative labels such as `基础`, `探索`, and `有实战`, not raw incoming/fusion/win-rate metrics.
- `/auto` signal output no longer exposes raw Arena W/L counts for failing knowledge; it keeps the deterministic SQL ranking internally and renders qualitative instability labels.

Regression tests:

- `tests/test_point_line_surface_p0.py::test_pls_active_only_counts_and_neighbors_exclude_hidden_virtual`
- `tests/test_point_line_surface_p0.py::test_pls_query_basis_defaults_to_active_only`
- `tests/test_point_line_surface_p0.py::test_pls_write_contract_rejects_inactive_endpoints_by_default`
- `tests/test_point_line_surface_p0.py::test_spiral_pioneer_raw_edge_path_rejects_inactive_endpoints`
- `tests/test_auto_mode_signal_visibility.py`

---

## 5. Highest remaining risks

### P0: validated concept writes without hard evidence anchors

2026-05-12 evidence chain:

```text
provider/API 500/503 errors caused many rounds to fail before external tools could run.
planner_unavailable/fallback increased sharply in markdown reports.
normal completed rounds still wrote points, but almost always entered through search_knowledge_nodes or trace_query first.
PLS terrain and internal topology acted as candidate-routing amplifiers.
record_point/create_node accepted concept-plane signatures that could resolve to validation_status=validated.
```

What is verified:

- GP did not directly use `pls_query` as a normal tool path during the critical period.
- PLS terrain was injected through auto-mode signals and async scout paths.
- `search_knowledge_nodes` / `trace_query` / PLS terrain are useful topology context, but are not external evidence.
- `create_node()` sets `last_verified_at` at creation time when the normalized signature is already `validation_status=validated`.
- Runtime logs keep only summarized args/previews, so not every original `record_point` signature can be reconstructed.

Risk:

```text
reflection/internal-topology-derived concept nodes can become indistinguishable from externally validated knowledge.
```

Required policy:

```text
PLS-derived evidence level = candidate/partial/unverified by default.
validated requires at least one hard external evidence anchor.
fallback/error/dry-streak rounds cannot create validated concept-plane nodes unless evidence_refs are explicit.
```

Hard evidence anchors should include at least one concrete external observation:

- file path plus excerpt
- command plus output excerpt
- DB query plus result excerpt
- trace ID plus relevant span/result excerpt
- runtime observation with timestamp and source

### Current status: default visibility/write contract is covered

Current state:

- `SurfaceExpander` filters hidden/virtual nodes downstream.
- `create_reasoning_line()` and `add_edge()` reject hidden/virtual endpoints by default.
- `get_neighbor_map()` defaults to active-only neighbors.
- incoming-line metrics default to active-only endpoint joins.
- `pls_query basis` defaults to active-only ranking.
- explicit integrity modes may still include hidden/virtual rows via `include_hidden` / `include_virtual`.

The earlier P0/P1 issue has been addressed in current local code and tests. The remaining concern is historical debt plus any raw SQL bypass that does not route through the guarded APIs.

Current API pattern:

```text
Default PLS visibility must be active-only.
Explicit integrity modes may include hidden/virtual rows.
```

Already applied to:

- `get_incoming_line_count()`
- `get_incoming_line_counts_batch()`
- `get_incoming_count_percentile()`
- `get_basis_set_for_node()`
- `get_neighbor_map()`
- `PLSQueryTool._basis()`
- `PLSQueryTool._overview()`
- `PLSQueryTool._node()` / metrics-like displays
- `pls_async_scout` section collection through default `PLSQueryTool` calls and numeric stripping

### P1: Raw SQL bypass and historical topology maintenance dry-run

Historical audit snapshot still contains inactive endpoint rows:

```json
{
  "reasoning_lines_hidden_or_virtual_endpoints": 4189,
  "node_edges_hidden_or_virtual_endpoints": 4695
}
```

Future work should search for direct SQL writes to `reasoning_lines` / `node_edges` that bypass `NodeVault` guards, and should add dry-run topology debt reports before any cleanup.

### P1: Historical topology maintenance dry-run

Needed dry-run report before any writes:

- orphan `reasoning_lines`
- orphan `node_edges`
- hidden/virtual endpoint `reasoning_lines`
- hidden/virtual endpoint `node_edges`
- noncanonical relation values
- self-loop edges
- null `line_id` rows
- top basis ranking before/after active-only filtering

Do not clean directly until the report is reviewed.

### P1: potential_samples historical maintenance

Needed dry-run classes:

- rows with missing dedupe key
- active open non-actionable rows that should become `observed`
- non-actionable rows currently `crystallized`
- actionable open rows that now have matching created nodes
- duplicate old rows that can be collapsed by future dedupe key

Do not update live DB directly until preview output is reviewed.

### P1/P2: VOID lifecycle

`void_tasks` needs a lifecycle similar to `potential_samples`:

- dedupe signature
- occurrence count
- last_seen timestamp
- state transitions:
  - `open`
  - `observed`
  - `resolved`
  - `ignored`
  - `stale`
- resolution binding to node IDs
- dry-run stale/open preview

### P2: reasoning_lines schema migration

Because `line_id` is unreliable, future exact line maintenance should not depend on it.

Safe migration design:

1. Create `reasoning_lines_v2` with reliable ID.
2. Copy all rows using generated IDs where missing.
3. Preserve endpoint/source/trace/round/timestamp.
4. Rebuild indexes.
5. Validate row counts and endpoint distributions.
6. Swap tables only after backup and explicit approval.

This is not a quick fix.

---

## 6. Recommended implementation order

### Phase 0: validated evidence gate

Goal:

```text
Validated knowledge cannot be created from reflection/internal topology alone.
```

Modify write/trust paths before any historical cleanup:

- `record_point` schema and validation
- `RecordPointTool.execute()`
- `NodeVault.create_node()`
- auto-mode fallback/dry-streak write policy

Required behavior:

```text
validation_status=validated requires evidence_refs or equivalent hard evidence metadata.
verification_source=reflection cannot create validated concept-plane nodes by itself.
PLS terrain/search/trace topology context can create candidate/partial/unverified nodes only.
provider-error/planner-fallback rounds cannot produce validated concept nodes unless explicit hard evidence is attached.
```

Suggested structured field:

```json
{
  "evidence_refs": [
    {
      "type": "file|command|db_query|trace|runtime_observation",
      "ref": "path, command, query, trace_id, or observation source",
      "excerpt": "minimal observed text",
      "observed_at": "timestamp"
    }
  ]
}
```

Acceptance criteria:

```text
reflection + concept_plane + validated is rejected or downgraded.
search_knowledge_nodes/trace_query-only writes are candidate/partial/unverified.
validated nodes have at least one hard evidence anchor.
fallback/error rounds default to unverified/partial unless evidence_refs are present.
```

### Phase 1: active-only read semantics

Goal:

```text
PLS query/scout metrics no longer treat hidden/virtual nodes as visible basis.
```

Modify read/count paths first:

- `get_incoming_line_count()`
- `get_incoming_line_counts_batch()`
- `get_incoming_count_percentile()`
- `PLSQueryTool._basis()`
- `PLSQueryTool._overview()`

Acceptance criteria:

```text
pls_query basis top N hidden count = 0 by default
active-only top basis differs from integrity/all-mode top basis
surface tests still pass
async scout does not produce hidden basis_branch seed by default
```

### Phase 2: explicit integrity modes

Goal:

```text
Operators can still audit hidden/virtual topology debt.
```

Add optional views/modes:

- `visibility_debt`
- `basis_all`
- or explicit `include_hidden=true` if tool interface supports it

Acceptance criteria:

```text
Integrity mode reports hidden/virtual endpoint counts without polluting default GP terrain.
```

### Phase 3: write contract guardrails

Goal:

```text
Ordinary new PLS lines/edges cannot point to hidden/virtual endpoints by accident.
```

Modify:

- `_validate_node_edge()` or `add_edge()`
- `create_reasoning_line()`

Acceptance criteria:

Temporary DB probe should become:

```json
{
  "line_hidden_allowed": false,
  "edge_hidden_allowed": false,
  "edge_virtual_allowed": false
}
```

If audit sources are allowed, they must be explicit and excluded from default metrics.

### Phase 4: dry-run maintenance reports

Goal:

```text
Historical debt is quantified before any cleanup.
```

Reports:

- potential maintenance preview
- topology visibility debt preview
- void lifecycle preview
- schema drift preview

### Phase 5: reviewed live maintenance

Only after explicit approval:

- status updates for potential history
- orphan edge/line cleanup
- relation normalization
- VOID stale/resolved transitions
- optional reasoning_lines schema migration

---

## 7. Read-only SQL audit snippets

Use these as starting points. Keep outputs capped.

### 2026-05-12 trust-gate risk classification

This is read-only. It classifies historical nodes for review; it does not prove that a node is wrong.

```sql
WITH scoped AS (
    SELECT node_id,
           title,
           datetime(created_at, '+8 hours') local_created_at,
           verification_source,
           json_extract(metadata_signature, '$.validation_status') validation_status,
           json_extract(metadata_signature, '$.target_kind') target_kind,
           json_extract(metadata_signature, '$.task_kind') task_kind,
           json_extract(metadata_signature, '$.framework') framework,
           json_extract(metadata_signature, '$.runtime') runtime,
           json_extract(metadata_signature, '$.language') language
    FROM knowledge_nodes
    WHERE datetime(created_at, '+8 hours') >= '2026-05-12 00:00:00'
      AND datetime(created_at, '+8 hours') < '2026-05-13 00:00:00'
      AND node_id NOT LIKE 'MEM_CONV%'
      AND COALESCE(is_virtual, 0) = 0
      AND COALESCE(ablation_active, 0) = 0
),
classified AS (
    SELECT *,
           CASE
             WHEN validation_status = 'validated'
              AND target_kind = 'concept_plane'
              AND COALESCE(verification_source, '') IN (
                  '', 'reflection', 'knowledge_synthesis',
                  'knowledge_neighbor_synthesis', 'knowledge_reuse'
              )
             THEN 'B_concept_validated_without_hard_anchor'
             WHEN validation_status = 'validated'
              AND COALESCE(verification_source, '') IN (
                  'command_output', 'code_reading', 'code_verified',
                  'database_query', 'database_audit', 'runtime_test',
                  'manual_check', 'read_file+knowledge_query'
              )
             THEN 'A_validated_with_external_or_mixed_anchor_review'
             WHEN target_kind = 'concept_plane'
             THEN 'C_concept_candidate_review'
             ELSE 'D_other'
           END evidence_class
    FROM scoped
)
SELECT evidence_class,
       COUNT(*) nodes,
       SUM(CASE WHEN validation_status = 'validated' THEN 1 ELSE 0 END) validated_nodes,
       COUNT(DISTINCT verification_source) verification_source_kinds
FROM classified
GROUP BY evidence_class
ORDER BY evidence_class;
```

### 2026-05-12 sample nodes needing external re-anchor

```sql
WITH scoped AS (
    SELECT node_id,
           title,
           datetime(created_at, '+8 hours') local_created_at,
           verification_source,
           json_extract(metadata_signature, '$.validation_status') validation_status,
           json_extract(metadata_signature, '$.target_kind') target_kind,
           json_extract(metadata_signature, '$.task_kind') task_kind
    FROM knowledge_nodes
    WHERE datetime(created_at, '+8 hours') >= '2026-05-12 00:00:00'
      AND datetime(created_at, '+8 hours') < '2026-05-13 00:00:00'
      AND node_id NOT LIKE 'MEM_CONV%'
      AND COALESCE(is_virtual, 0) = 0
      AND COALESCE(ablation_active, 0) = 0
)
SELECT node_id,
       local_created_at,
       title,
       verification_source,
       validation_status,
       target_kind,
       task_kind
FROM scoped
WHERE validation_status = 'validated'
  AND target_kind = 'concept_plane'
  AND COALESCE(verification_source, '') IN (
      '', 'reflection', 'knowledge_synthesis',
      'knowledge_neighbor_synthesis', 'knowledge_reuse'
  )
ORDER BY local_created_at
LIMIT 50;
```

### Table counts

```sql
SELECT 'knowledge_nodes' table_name, COUNT(*) rows FROM knowledge_nodes
UNION ALL SELECT 'reasoning_lines', COUNT(*) FROM reasoning_lines
UNION ALL SELECT 'node_edges', COUNT(*) FROM node_edges
UNION ALL SELECT 'point_creation_context', COUNT(*) FROM point_creation_context
UNION ALL SELECT 'potential_samples', COUNT(*) FROM potential_samples
UNION ALL SELECT 'pls_proposals', COUNT(*) FROM pls_proposals
UNION ALL SELECT 'void_tasks', COUNT(*) FROM void_tasks
UNION ALL SELECT 'ablation_baselines', COUNT(*) FROM ablation_baselines;
```

### Potential lifecycle summary

```sql
SELECT COUNT(*) total_rows,
       SUM(CASE WHEN dedupe_key IS NULL OR dedupe_key = '' THEN 1 ELSE 0 END) missing_dedupe,
       SUM(CASE WHEN COALESCE(status, 'open') IN ('open', 'actionable') THEN 1 ELSE 0 END) active_open,
       SUM(CASE WHEN COALESCE(status, 'open') IN ('open', 'actionable')
                 AND COALESCE(triage_category, 'structural') = 'actionable'
                THEN 1 ELSE 0 END) actionable_open,
       SUM(CASE WHEN COALESCE(status, 'open') IN ('open', 'actionable')
                 AND COALESCE(triage_category, 'structural') <> 'actionable'
                THEN 1 ELSE 0 END) non_actionable_open
FROM potential_samples;
```

### Hidden/virtual endpoint line debt

```sql
SELECT COUNT(*) rows
FROM reasoning_lines rl
JOIN knowledge_nodes new_node ON new_node.node_id = rl.new_point_id
JOIN knowledge_nodes basis_node ON basis_node.node_id = rl.basis_point_id
WHERE COALESCE(new_node.ablation_active, 0) > 0
   OR COALESCE(basis_node.ablation_active, 0) > 0
   OR COALESCE(new_node.is_virtual, 0) = 1
   OR COALESCE(basis_node.is_virtual, 0) = 1;
```

### Hidden/virtual endpoint edge debt

```sql
SELECT COUNT(*) rows
FROM node_edges e
JOIN knowledge_nodes src ON src.node_id = e.source_id
JOIN knowledge_nodes dst ON dst.node_id = e.target_id
WHERE COALESCE(src.ablation_active, 0) > 0
   OR COALESCE(dst.ablation_active, 0) > 0
   OR COALESCE(src.is_virtual, 0) = 1
   OR COALESCE(dst.is_virtual, 0) = 1;
```

### Current basis query pollution check

```sql
SELECT SUM(CASE WHEN hidden > 0 THEN 1 ELSE 0 END) hidden_rows_in_top12,
       COUNT(*) total_top12
FROM (
    SELECT k.node_id,
           COALESCE(k.ablation_active, 0) hidden,
           COUNT(*) incoming
    FROM knowledge_nodes k
    JOIN reasoning_lines rl
      ON rl.basis_point_id = k.node_id
     AND COALESCE(rl.same_round, 0) = 0
    WHERE k.node_id NOT LIKE 'MEM_CONV_%'
      AND COALESCE(k.is_virtual, 0) = 0
    GROUP BY k.node_id
    ORDER BY incoming DESC
    LIMIT 12
);
```

### Active-only top basis comparison

```sql
SELECT k.node_id, k.type, k.title, COUNT(*) incoming
FROM knowledge_nodes k
JOIN reasoning_lines rl
  ON rl.basis_point_id = k.node_id
 AND COALESCE(rl.same_round, 0) = 0
JOIN knowledge_nodes new_node
  ON new_node.node_id = rl.new_point_id
WHERE k.node_id NOT LIKE 'MEM_CONV_%'
  AND COALESCE(k.is_virtual, 0) = 0
  AND COALESCE(k.ablation_active, 0) = 0
  AND COALESCE(new_node.is_virtual, 0) = 0
  AND COALESCE(new_node.ablation_active, 0) = 0
GROUP BY k.node_id
ORDER BY incoming DESC
LIMIT 12;
```

### reasoning_lines schema drift

```sql
PRAGMA table_info(reasoning_lines);
SELECT COUNT(*) null_line_id_rows FROM reasoning_lines WHERE line_id IS NULL;
SELECT COUNT(*) nonnull_line_id_rows FROM reasoning_lines WHERE line_id IS NOT NULL;
```

---

## 8. Runtime probes to keep

### Async scout metadata leak probe

Expected:

```json
{
  "terrain_has_metadata_leak": false,
  "branches_has_metadata_leak": false
}
```

Leak terms to check:

```text
missing_dedupe=
active_open=
non_actionable_open=
total=
rows=
seen=
last_seen=
dedupe:
```

### Hidden/virtual write contract probe

Current expected result before future fix:

```json
{
  "line_hidden_allowed": true,
  "edge_hidden_allowed": true,
  "edge_virtual_allowed": true
}
```

Desired result after future fix:

```json
{
  "line_hidden_allowed": false,
  "edge_hidden_allowed": false,
  "edge_virtual_allowed": false
}
```

### Surface downstream filtering probe

Current behavior:

- `get_neighbor_map()` may return hidden/virtual neighbors.
- `SurfaceExpander` excludes them later via `excluded_ids`.

Future desired behavior:

- Default `get_neighbor_map()` should not return hidden/virtual neighbors unless explicitly requested.
- Surface should still keep downstream exclusion as defense-in-depth.

---

## 9. Tests to run after future PLS changes

Minimum local/remote test set:

```bash
python -m py_compile genesis/v4/manager.py genesis/v4/surface.py genesis/tools/pls_query_tool.py genesis/tools/pls_async_scout.py
python -m pytest tests/test_point_line_surface_p0.py -q
python -m pytest tests/test_pls_async_proposals.py -q
```

When changing visibility/count semantics, add tests for:

- hidden node not counted as default basis
- virtual node not counted as default basis
- hidden/virtual line endpoint excluded from incoming counts
- integrity mode can still report hidden/virtual debt
- async scout does not select hidden basis by default
- write contract rejects hidden/virtual endpoints unless explicitly permitted

---

## 10. Do-not-miss checklist

Before saying PLS is fully covered, confirm all boxes below.

### Evidence trust gate

- [ ] `validated` writes require explicit hard evidence anchors.
- [ ] `verification_source=reflection` cannot create validated concept-plane nodes by itself.
- [ ] PLS terrain, `search_knowledge_nodes`, and `trace_query` can only support candidate/partial/unverified writes without external anchors.
- [ ] Provider-error, planner-fallback, and dry-streak recovery rounds cannot create validated concept-plane nodes without `evidence_refs`.
- [ ] Historical 2026-05-12 validated concept nodes have a read-only risk classification report before any metadata migration.

### Potential lifecycle

- [ ] Recent rows have dedupe keys.
- [ ] `observed` is not treated as open actionable work.
- [ ] `get_open_potential_samples()` excludes `observed`.
- [ ] `crystallize_potential_samples_for_node()` only closes actionable rows.
- [ ] Historical non-actionable open rows have a dry-run maintenance plan.
- [ ] Historical non-actionable crystallized rows have a dry-run maintenance plan.

### Visibility contract

- [ ] Default basis counts exclude hidden nodes.
- [ ] Default basis counts exclude virtual nodes.
- [ ] Default incoming counts exclude lines whose new or basis endpoint is hidden/virtual.
- [ ] `get_neighbor_map()` default behavior does not leak hidden/virtual nodes, or every consumer defensively filters.
- [ ] `pls_query basis` top results are active-only by default.
- [ ] `pls_async_scout` does not use hidden basis as branch seeds by default.

### Write contract

- [ ] `create_reasoning_line()` rejects hidden/virtual endpoints by default, or requires explicit audit source.
- [ ] `add_edge()` rejects hidden/virtual endpoints by default, or requires explicit audit source.
- [ ] Relation normalization remains intact.
- [ ] Missing endpoint and self-loop rejection still pass.

### Topology integrity

- [ ] Orphan line count known.
- [ ] Orphan edge count known.
- [ ] Self-loop edge count known.
- [ ] Noncanonical relation count known.
- [ ] Hidden/virtual endpoint line/edge debt known.
- [ ] Dry-run cleanup report reviewed before writes.

### VOID closure

- [ ] `void_tasks` open backlog summarized.
- [ ] Duplicate/open query groups checked.
- [ ] State transition policy exists.
- [ ] Dry-run stale/resolved candidates available.

### Proposal closure

- [ ] `pls_proposals` staging status known.
- [ ] Async proposal worker still dry-run/staging only unless explicitly committed.
- [ ] Proposal payload validation still rejects missing basis/schema/content.

### Scout/auto-mode hygiene

- [ ] Numeric/operational fields do not enter `build_pls_terrain_brief()`.
- [ ] Numeric/operational fields do not enter `build_pls_branch_proposals()`.
- [ ] Potential guardrail lines are visible in `pls_query potential` but invisible to GP semantic terrain.

### Schema drift

- [ ] `reasoning_lines.line_id` schema checked.
- [ ] Future maintenance does not rely on null/invalid `line_id`.
- [ ] Any schema migration has backup, copy validation, index validation, and explicit approval.

---

## 11. Practical next step recommendation

Do not start with live cleanup.

The former P0/P1 code change has been implemented locally:

```text
Default active-only visibility semantics for PLS read/count/query/scout/write paths.
```

Verified locally:

```text
active-only count/query/write tests pass.
async proposal lifecycle tests pass.
auto-mode raw W/L metric output is hidden behind qualitative labels.
```

Next step should be implementing the validated evidence gate, then running read-only dry-run classification for historical 2026-05-12 nodes before any metadata migration or live cleanup.

---

## 12. Short executive summary

What is covered:

```text
potential_samples new lifecycle guardrails
async scout telemetry leak prevention
proposal staging tests
proposal/point default CONTEXT lifecycle alignment
default active-only PLS read/count/query/write semantics
GP-visible search/preload qualitative PLS labels
auto-mode Arena W/L signal rendering as qualitative instability
read-only query visibility into potential lifecycle
2026-05-12 drift mechanism audit at policy level
```

What is not covered:

```text
historical hidden/virtual endpoint topology debt cleanup
validated evidence gate implementation
historical 2026-05-12 concept-node risk classification report
direct raw SQL bypass audit for reasoning_lines/node_edges writers
historical topology debt cleanup
VOID lifecycle closure
reasoning_lines schema drift
```

Priority order:

```text
1. implement validated evidence gate for new writes
2. run read-only 2026-05-12 concept-node risk classification
3. dry-run topology and potential maintenance reports
4. raw SQL bypass audit for reasoning_lines/node_edges writers
5. VOID lifecycle closure
6. reasoning_lines schema migration plan
7. reviewed live maintenance only after explicit approval
```
