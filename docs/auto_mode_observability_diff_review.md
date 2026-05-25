# Auto Mode Observability Diff Review

## 0. Purpose

This document reviews the existing uncommitted `genesis/auto_mode.py` diff that was discovered before implementing Phase B `outcome_domains` emission.

It exists to prevent mixing unrelated runtime observability changes with the outcome-domain Phase B task.

## 1. Review status

Decision:

```text
keep_as_separate_observability_change_candidate
```

Do not combine with:

```text
Phase B report-only outcome_domains emission
```

Reason:

```text
The current auto_mode.py diff is not an outcome_domains change.
It modifies auto report observability and repeat-state diagnostics.
```

## 2. Files reviewed

```text
genesis/auto_mode.py
tests/test_auto_mode_signal_visibility.py
tests/test_provider_router_default_model_failover.py
tests/test_shell_health_check.py
```

Diff size:

```text
genesis/auto_mode.py: 222 additions, 5 deletions
tests/test_auto_mode_signal_visibility.py: 20 additions
tests/test_provider_router_default_model_failover.py: 54 additions, 53 deletions
tests/test_shell_health_check.py: 18 additions
```

## 3. Main diff themes

## 3.1 Round topology report field

New helper:

```text
_build_round_topology(round_events, duration_s=None)
```

Purpose:

```text
Summarize point/line/search/GP-call topology inside each auto round report.
```

Observed fields include:

```text
classification
anchor_timing
post_anchor_shape
anchored
points_created
lines_successful
anchored_points
knowledge_searches
gp_llm_calls
timeout_risk_shape
```

Interpretation:

```text
This is report observability.
It should not change runtime behavior.
```

## 3.2 State freshness report field

New helper:

```text
_build_state_freshness(round_log, issue, kb_changed=False, outcome_detected=False)
```

Purpose:

```text
Detect repeated same issue without KB or physical outcome evidence.
```

Output:

```text
issue_repeat_count
state_stale
reason
```

Important semantic constraint:

```text
state_freshness is diagnostic.
It must not reset or redefine consecutive_dry.
```

## 3.3 Chapter-state integration

The diff adds state freshness to chapter-state evidence/deprecated/stale-action packets.

Purpose:

```text
Make repeated issue drift visible to planner-facing report text.
```

Risk:

```text
This may influence future prompts if the chapter-state packet is injected into prompt construction.
```

Required review question:

```text
Is this intended as report-only observability, or as a prompt control signal?
```

If it is prompt control, it should be reviewed separately from passive report observability.

## 3.4 LLM cache stats persistence

The diff expands `llm_call_end` event data and accumulates:

```text
llm_cache_stats[bucket].calls
llm_cache_stats[bucket].input_tokens
llm_cache_stats[bucket].cache_hit_tokens
llm_cache_stats[bucket].cache_hit_rate
```

Interpretation:

```text
This aligns with prior auto report cache bucket observability.
```

## 3.5 Round topology flush cadence

The diff changes `_flush_round_record()` so `round_topology` is refreshed:

```text
when status != running
or no events yet
or every 20 new events
```

Purpose:

```text
Avoid recomputing topology on every callback while keeping final reports accurate.
```

Risk:

```text
Low runtime behavior risk, but report JSON size and callback write frequency should remain monitored.
```

## 4. Validation performed

Compile:

```text
python -m py_compile genesis/auto_mode.py tests/test_auto_mode_signal_visibility.py tests/test_provider_router_default_model_failover.py tests/test_shell_health_check.py
```

Tests:

```text
python -m pytest tests/test_auto_mode_signal_visibility.py tests/test_provider_router_default_model_failover.py tests/test_shell_health_check.py -q
```

Result:

```text
34 passed
```

Whitespace:

```text
git diff --check -- genesis/auto_mode.py tests/test_auto_mode_signal_visibility.py tests/test_provider_router_default_model_failover.py tests/test_shell_health_check.py
```

Result:

```text
passed
```

## 5. Risk assessment

Risk level:

```text
medium
```

Reason:

```text
genesis/auto_mode.py is high-risk Yogg runtime code.
The diff is mostly observability, but chapter-state integration may affect prompt content.
```

Known constraints:

```text
Do not whole-file sync this to production Yogg without reviewing all hunks.
Do not mix this with outcome_domains Phase B.
Do not treat state_freshness as outcome semantics.
Do not let kb_changed redefine outcome_detected.
```

## 6. Recommendation

Recommended action:

```text
Keep this diff as a separate observability change candidate.
Review and commit it independently before starting outcome_domains Phase B.
```

Not recommended:

```text
Do not implement outcome_domains on top of this uncommitted diff.
Do not deploy this diff to Yogg by copying the whole file.
```

If proceeding with this diff, review these questions first:

```text
1. Should state_freshness affect prompt/chapter-state, or stay report-only?
2. Is 20-event topology refresh the right compromise for report accuracy vs IO?
3. Are provider router test rewrites part of the same commit, or should they be split?
4. Is shell cwd metadata test unrelated and better committed separately?
```

## 7. Relationship to outcome_domains Phase B

Phase B should wait until this diff is isolated.

Reason:

```text
outcome_domains Phase B should be a minimal additive report field patch.
It should not be entangled with state_freshness, topology, provider routing, or shell metadata changes.
```

Next valid order:

```text
1. Review/split/commit or revert this observability diff.
2. Return to docs/v6_outcome_domains_phase_b_plan.md.
3. Implement outcome_domains in a clean runtime diff.
```
