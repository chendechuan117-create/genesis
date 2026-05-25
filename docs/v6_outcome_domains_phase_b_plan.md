# V6 Outcome Domains Phase B Plan

## 0. Status

This is an implementation plan, not an implementation.

Reason for stopping before patch:

```text
genesis/auto_mode.py already has unrelated uncommitted local diffs.
```

Do not patch `auto_mode.py` until those diffs are reviewed, staged, reverted, or otherwise isolated.

Observed unrelated diff themes:

```text
state_freshness reporting
round_topology flushing
llm_cache_stats persistence
provider router test rewrites
shell cwd metadata test
```

These are not Phase B `outcome_domains` changes.

Dedicated review:

```text
docs/auto_mode_observability_diff_review.md
```

Precheck validation:

```text
tests/test_auto_mode_signal_visibility.py
tests/test_shell_health_check.py
tests/test_provider_router_default_model_failover.py
```

Result:

```text
34 passed
```

## 1. Phase B objective

Phase B objective:

```text
Emit outcome_domains into future auto round JSON reports as a report-only additive field.
```

It must not change runtime behavior.

## 2. Source proposal

Source proposal:

```text
docs/v6_outcome_domains_runtime_proposal.md
```

Accepted governance outcome:

```text
Genesis should preserve separate outcome domains because Yogg produced substantial knowledge-domain evidence that would be misclassified or hidden by a physical-only outcome lens.
```

## 3. Hard invariants

Preserve:

```text
outcome_detected remains physical-only
consecutive_dry remains controlled only by outcome_detected/progress_profile
state_freshness behavior remains unchanged
planner behavior remains unchanged
C-Phase behavior remains unchanged
NodeVault writes remain unchanged
training remains unchanged
promotion/canary remains unchanged
```

## 4. Current code touchpoints

File:

```text
genesis/auto_mode.py
```

Observed report setup:

```text
run_auto()
_report_dir = Path("runtime/auto_reports")
_rounds_dir = _report_dir / _session_id
_write_round_json(data) writes round_{round:03d}.json
```

Initial `round_record` shape is created inside `run_auto()`.

Existing source fields:

```text
outcome_detected
kb_changed
kb_delta
pls_telemetry
phase_trace
events
status
progress_class
```

Existing finalization paths that update reports:

```text
completed
interrupted
timeout
exception
```

## 5. Minimal safe patch shape

Add a pure helper near existing report helpers:

```text
_build_outcome_domains_for_report(record_or_fields) -> list[dict]
```

The helper should be pure:

```text
no IO
no DB access
no NodeVault writes
no self_evolution access
no mutation of dry-state or planner state
```

Use only already-computed fields:

```text
outcome_detected
kb_changed
kb_delta
pls_telemetry
events
phase_trace
```

Then add:

```text
round_record["outcome_domains"] = _build_outcome_domains_for_report(round_record)
```

inside `_flush_round_record()` immediately before `_write_round_json(round_record)`.

Reason:

```text
All finalization paths already call _flush_round_record().
This avoids duplicating updates across completed/interrupted/timeout/exception paths.
```

## 6. Mapping rules for initial implementation

## 6.1 physical_file_outcome

Observed when:

```text
record.outcome_detected is True
```

State:

```text
observed if true
mappable_absent if false bool exists
missing_fields otherwise
```

## 6.2 knowledge_domain_evidence

Observed when any holds:

```text
kb_changed is True
len(kb_delta.new_nodes) > 0
len(kb_delta.updated_nodes) > 0
pls_telemetry.points_created > 0
```

## 6.3 line_activity_evidence

Observed when any holds:

```text
pls_telemetry.lines_created > 0
pls_telemetry.cross_round_lines > 0
pls_telemetry.line_errors > 0
record_line events exist
```

## 6.4 line_consumption_evidence

Initial Phase B should be conservative.

Allowed observed state only for weak evidence:

```text
record_line success new_point_id intersects phase_trace.current_state_preview.active_nodes
```

If present, mark:

```text
consumption_tier: weak_active_context
state: needs_verification
```

Do not mark resolved.

## 6.5 governance_review_outcome

Runtime auto reports should normally mark this absent unless a reviewed artifact is explicitly attached.

Initial Phase B should output:

```text
state: missing_fields or mappable_absent
observed: false
```

Do not infer governance review from raw evidence.

## 7. Required tests before patch acceptance

Add or update tests proving:

```text
outcome_detected remains physical-only
knowledge_domain_evidence does not change consecutive_dry
line_activity_evidence does not change consecutive_dry
outcome_domains appears in completed reports
outcome_domains appears in interrupted/timeout/exception reports if those paths are exercised
legacy consumers tolerate missing outcome_domains
canonicalizer agrees with runtime-emitted outcome_domains for equivalent sample records
weak_active_context maps to needs_verification, not resolved
```

Likely test file:

```text
tests/test_auto_mode_signal_visibility.py
```

Potential new focused file:

```text
tests/test_auto_mode_outcome_domains.py
```

## 8. Pre-patch checklist

Before touching `auto_mode.py`:

```text
1. Inspect current git diff for genesis/auto_mode.py.
2. Decide whether existing local diff belongs to this task.
3. If unrelated, isolate it before patching.
4. Run GitNexus impact on run_auto and any helper being changed.
5. Read NodeVault observations for auto_mode.py.
6. Add tests first or in same patch.
```

## 9. Rejection conditions

Reject implementation if it:

```text
changes outcome_detected semantics
uses outcome_domains to reset dry-state
changes progress_class classification
changes planner prompt/fallback behavior
changes C-Phase behavior
writes NodeVault
adds DB reads to the helper
marks weak line consumption as resolved
changes self_evolution outcome logic
```

## 10. Current decision

Current decision:

```text
stop_before_patch
```

Reason:

```text
The design is clear, but runtime file has unrelated uncommitted diffs and Phase B needs isolated implementation review.
```

Next valid action:

```text
Review or isolate existing auto_mode.py diffs, then start a separate Phase B implementation task.
```
