# Yogg Value Audit Commit Stack

## 0. Purpose

This document groups the current working tree into review/commit units.

It exists because the working tree contains multiple unrelated change lines and should not be committed or deployed as one mixed bundle.

## 1. Recommended order

Recommended order:

```text
A. Yogg value audit read-only chain
B. Auto-mode observability diff
C. Provider/router and shell health test fixes
D. Other governance/infrastructure changes
E. Outcome_domains Phase B implementation only after A/B are isolated
```

Do not implement Phase B on top of the current mixed worktree.

## 2. Stack A: Yogg value audit read-only chain

Status:

```text
ready_for_review_or_commit
```

Nature:

```text
read-only docs/scripts/tests
no runtime patch
no NodeVault writes
no training
```

Files:

```text
docs/yogg_signal_promotion_candidates.md
docs/yogg_signal_promotion_review.md
docs/v6_outcome_domain_contract.md
docs/yogg_governance_review_outcome_draft.md
docs/yogg_value_audit_summary.md
docs/yogg_value_audit_handoff.md
docs/v6_outcome_domains_runtime_proposal.md
docs/v6_outcome_domains_phase_b_plan.md
docs/auto_mode_observability_diff_review.md

genesis/v6/audit_yogg_signal_promotion.py
genesis/v6/audit_outcome_domain_compatibility.py
genesis/v6/canonicalize_outcome_domains.py
genesis/v6/consume_outcome_domain_rows.py
genesis/v6/aggregate_outcome_governance.py

tests/test_v6_yogg_signal_promotion.py
tests/test_v6_outcome_domain_compatibility.py
tests/test_v6_outcome_domain_canonicalizer.py
tests/test_v6_outcome_domain_row_consumer.py
tests/test_v6_outcome_governance_aggregator.py
```

Related prior V6/self-model artifacts that may be reviewed with or before Stack A:

```text
docs/genesis_self_model_leverage_audit.md
docs/yogg_21_23_deep_dive.md
docs/yogg_weekly_report_20260516_0523.md
docs/knowledge_governance_layer.md

genesis/v6/audit_sao_distillability.py
tests/test_v6_sao_distillability.py
```

Validation:

```bash
python -m pytest tests/test_v6_outcome_governance_aggregator.py tests/test_v6_outcome_domain_row_consumer.py tests/test_v6_outcome_domain_canonicalizer.py tests/test_v6_outcome_domain_compatibility.py tests/test_v6_yogg_signal_promotion.py tests/test_v6_sao_distillability.py -q
```

Known result:

```text
21 passed
```

Stack A-only validation:

```text
15 passed
```

Manual staging command:

```bash
git add \
  docs/yogg_signal_promotion_candidates.md \
  docs/yogg_signal_promotion_review.md \
  docs/v6_outcome_domain_contract.md \
  docs/yogg_governance_review_outcome_draft.md \
  docs/yogg_value_audit_summary.md \
  docs/yogg_value_audit_handoff.md \
  docs/v6_outcome_domains_runtime_proposal.md \
  docs/v6_outcome_domains_phase_b_plan.md \
  docs/auto_mode_observability_diff_review.md \
  docs/yogg_value_audit_commit_stack.md \
  genesis/v6/audit_yogg_signal_promotion.py \
  genesis/v6/audit_outcome_domain_compatibility.py \
  genesis/v6/canonicalize_outcome_domains.py \
  genesis/v6/consume_outcome_domain_rows.py \
  genesis/v6/aggregate_outcome_governance.py \
  tests/test_v6_yogg_signal_promotion.py \
  tests/test_v6_outcome_domain_compatibility.py \
  tests/test_v6_outcome_domain_canonicalizer.py \
  tests/test_v6_outcome_domain_row_consumer.py \
  tests/test_v6_outcome_governance_aggregator.py
```

Suggested commit message:

```text
Add read-only Yogg value audit governance chain
```

## 2.1 Stack A0: prior V6/self-model audit artifacts

Status:

```text
ready_for_separate_review_or_include_before_stack_a
```

Files:

```text
docs/genesis_self_model_leverage_audit.md
docs/yogg_21_23_deep_dive.md
docs/yogg_weekly_report_20260516_0523.md
docs/knowledge_governance_layer.md
genesis/v6/audit_sao_distillability.py
tests/test_v6_sao_distillability.py
```

Recommendation:

```text
Either commit Stack A0 immediately before Stack A, or include it in Stack A if the review scope is the full V6/Yogg audit chain.
```

Stack A0 validation:

```text
6 passed
```

Manual staging command:

```bash
git add \
  docs/genesis_self_model_leverage_audit.md \
  docs/yogg_21_23_deep_dive.md \
  docs/yogg_weekly_report_20260516_0523.md \
  docs/knowledge_governance_layer.md \
  genesis/v6/audit_sao_distillability.py \
  tests/test_v6_sao_distillability.py
```

Suggested commit message:

```text
Add V6 self-model and S-A-O distillability audit
```

## 3. Stack B: Auto-mode observability diff

Status:

```text
separate_review_required
```

Nature:

```text
runtime observability changes in high-risk auto_mode.py
```

Files:

```text
genesis/auto_mode.py
tests/test_auto_mode_signal_visibility.py
```

Themes:

```text
state_freshness reporting
round_topology report field
llm_cache_stats persistence
chapter-state repeated issue freshness integration
20-event round_topology flush cadence
```

Dedicated review:

```text
docs/auto_mode_observability_diff_review.md
```

Validation:

```bash
python -m py_compile genesis/auto_mode.py tests/test_auto_mode_signal_visibility.py
python -m pytest tests/test_auto_mode_signal_visibility.py -q
```

Stack B-only validation:

```text
11 passed
```

Manual staging command:

```bash
git add \
  genesis/auto_mode.py \
  tests/test_auto_mode_signal_visibility.py \
  docs/auto_mode_observability_diff_review.md
```

Broader validation already run with related tests:

```text
34 passed
```

Recommendation:

```text
Review Stack B separately before commit.
Do not deploy by whole-file sync to Yogg without hunk review.
Do not combine with outcome_domains Phase B.
```

Open review questions:

```text
1. Should state_freshness affect chapter-state/prompt control, or stay report-only?
2. Is 20-event topology refresh appropriate for runtime IO?
3. Should llm_cache_stats be committed with topology/freshness, or split?
```

Suggested commit message if accepted:

```text
Add auto-mode report observability for topology and state freshness
```

## 4. Stack C: Provider/router and shell health fixes

Status:

```text
separate_review_required_split_into_c1_c2
```

Reason:

```text
The original Stack C contains two independent themes and should not be committed as one mixed change:
C1. provider policy/failover
C2. shell cwd metadata
```

## 4.1 Stack C1: Provider policy/failover

Status:

```text
separate_review_required
```

Files:

```text
genesis/core/config.py
genesis/core/provider.py
genesis/core/provider_manager.py
genesis/providers/cloud_providers.py
tests/test_provider_router_default_model_failover.py
```

Nature:

```text
NewShrimp provider policy/failover
Aliyun deepseek-v4-flash fallback configuration
OpenAI-compatible NewShrimp stream/cache handling
provider recovery cooldown behavior
```

Review constraints:

```text
Preserve Yogg provider policy:
- prefer NewShrimp K2.6 pool when healthy
- fallback to Aliyun DS4F when NewShrimp pool is unavailable
- do not accidentally restore xcode/direct deepseek as the preferred Yogg path
```

Validation:

```bash
python -m py_compile genesis/core/config.py genesis/core/provider.py genesis/core/provider_manager.py genesis/providers/cloud_providers.py tests/test_provider_router_default_model_failover.py
python -m pytest tests/test_provider_router_default_model_failover.py -q
```

Stack C1-only validation:

```text
4 passed
```

Manual staging command:

```bash
git add \
  genesis/core/config.py \
  genesis/core/provider.py \
  genesis/core/provider_manager.py \
  genesis/providers/cloud_providers.py \
  tests/test_provider_router_default_model_failover.py
```

Suggested commit message if accepted:

```text
Refine provider failover policy for NewShrimp and Aliyun
```

## 4.2 Stack C2: Shell cwd metadata

Status:

```text
separate_review_required
```

Files:

```text
genesis/tools/shell_tool.py
tests/test_shell_health_check.py
```

Nature:

```text
shell cwd metadata behavior
```

Validation:

```bash
python -m py_compile genesis/tools/shell_tool.py tests/test_shell_health_check.py
python -m pytest tests/test_shell_health_check.py -q
```

Stack C2-only validation:

```text
19 passed
```

Manual staging command:

```bash
git add \
  genesis/tools/shell_tool.py \
  tests/test_shell_health_check.py
```

Suggested commit message if accepted:

```text
Expose shell cwd execution metadata
```

## 4.3 Stack C combined validation

Validation:

```bash
python -m py_compile genesis/core/config.py genesis/core/provider.py genesis/core/provider_manager.py genesis/providers/cloud_providers.py genesis/tools/shell_tool.py tests/test_provider_router_default_model_failover.py tests/test_shell_health_check.py
python -m pytest tests/test_provider_router_default_model_failover.py tests/test_shell_health_check.py -q
```

Known result:

```text
23 passed
```

Recommendation:

```text
Review and commit C1 and C2 separately from Yogg value audit.
Do not stage Stack C with Stack A0, Stack A, or Stack B.
```

## 5. Stack D: Other governance/infrastructure changes

Status:

```text
inventoried_split_before_commit
```

Reason:

```text
Stack D contains multiple independent governance/infrastructure themes.
Do not commit Stack D as one bundle.
```

## 5.1 Stack D1: Skill inventory tool

```text
factory.py
genesis/tools/skill_creator_tool.py
tests/test_skill_inventory_tool.py
```

Nature:

```text
read-only skill asset inventory
AST scan only
does not import or execute skill files
```

Validation:

```bash
python -m py_compile factory.py genesis/tools/skill_creator_tool.py tests/test_skill_inventory_tool.py
python -m pytest tests/test_skill_inventory_tool.py -q
```

Known result:

```text
3 passed
```

Manual staging command:

```bash
git add \
  factory.py \
  genesis/tools/skill_creator_tool.py \
  tests/test_skill_inventory_tool.py
```

Suggested commit message if accepted:

```text
Add read-only skill inventory tool
```

## 5.2 Stack D2: Multi-G blackboard convergence semantics

```text
genesis/v4/blackboard.py
tests/test_blackboard_convergence.py
```

Nature:

```text
distinguish shared-anchor agreement from low-diversity convergence
```

Validation:

```bash
python -m py_compile genesis/v4/blackboard.py tests/test_blackboard_convergence.py
python -m pytest tests/test_blackboard_convergence.py -q
```

Known result:

```text
2 passed
```

Manual staging command:

```bash
git add \
  genesis/v4/blackboard.py \
  tests/test_blackboard_convergence.py
```

Suggested commit message if accepted:

```text
Refine blackboard convergence detection
```

## 5.3 Stack D3: Trace pipeline dry-run safety

```text
genesis/v4/trace_pipeline/evidence_assessor.py
genesis/v4/trace_pipeline/node_cleanup.py
genesis/v4/manager.py
tests/test_trace_pipeline_evidence_assessor.py
tests/test_node_cleanup_dry_run.py
```

Nature:

```text
passive evidence assessor reports dry_run instead of mutating arena counters
node cleanup reports would_delete separately from hard_deleted
NodeVault.purge_forgotten_knowledge supports dry_run
```

Validation:

```bash
python -m py_compile genesis/v4/trace_pipeline/evidence_assessor.py genesis/v4/trace_pipeline/node_cleanup.py genesis/v4/manager.py tests/test_trace_pipeline_evidence_assessor.py tests/test_node_cleanup_dry_run.py
python -m pytest tests/test_trace_pipeline_evidence_assessor.py tests/test_node_cleanup_dry_run.py -q
```

Known result:

```text
4 passed
```

Manual staging command:

```bash
git add \
  genesis/v4/trace_pipeline/evidence_assessor.py \
  genesis/v4/trace_pipeline/node_cleanup.py \
  genesis/v4/manager.py \
  tests/test_trace_pipeline_evidence_assessor.py \
  tests/test_node_cleanup_dry_run.py
```

Review warning:

```text
genesis/v4/manager.py also contains Stack D4 governance report additions.
If staging D3 alone, use hunk staging for purge_forgotten_knowledge only.
```

Suggested commit message if accepted:

```text
Make trace evidence and cleanup paths report dry-run effects
```

## 5.4 Stack D4: NodeVault governance reports

```text
genesis/v4/manager.py
genesis/v4/background_daemon.py
tests/test_contradiction_audit_report.py
tests/test_env_fact_freshness_report.py
```

Nature:

```text
read-only contradiction edge audit report
read-only env fact freshness report
daemon surfaces dry-run governance audit summaries
```

Validation:

```bash
python -m py_compile genesis/v4/manager.py genesis/v4/background_daemon.py tests/test_contradiction_audit_report.py tests/test_env_fact_freshness_report.py
python -m pytest tests/test_contradiction_audit_report.py tests/test_env_fact_freshness_report.py -q
```

Known result:

```text
6 passed
```

Manual staging command:

```bash
git add \
  genesis/v4/manager.py \
  genesis/v4/background_daemon.py \
  tests/test_contradiction_audit_report.py \
  tests/test_env_fact_freshness_report.py
```

Review warning:

```text
genesis/v4/manager.py also contains Stack D3 dry-run additions.
If staging D4 alone, use hunk staging for governance report methods and daemon call sites only.
```

Suggested commit message if accepted:

```text
Add read-only NodeVault governance audit reports
```

## 5.5 Stack D5: Runtime cache/tracer observability and GP schema ordering

```text
genesis/core/tracer.py
genesis/v4/loop.py
genesis/v4/c_phase.py
```

Nature:

```text
cache hit observability by phase/bucket
llm_call_end cache_bucket reporting
deterministic GP tool schema ordering
small C-phase integration changes
```

Status:

```text
review_only_defer_commit_until_tested
```

Reason:

```text
This touches active runtime loop/tracing behavior and has no dedicated Stack D test yet.
It should not be hidden inside governance-report or dry-run commits.
```

Minimal validation already run:

```bash
python -m py_compile genesis/core/tracer.py genesis/v4/loop.py genesis/v4/c_phase.py
git diff --check -- genesis/core/tracer.py genesis/v4/loop.py genesis/v4/c_phase.py
```

Known result:

```text
passed
```

Missing dedicated tests:

```text
1. V4Loop._update_metrics separates gp_first, gp_warm, c, and lens cache buckets.
2. V4Loop._emit_llm_call_end emits cache_bucket and cache_hit_rate consistently.
3. Tracer.log_llm_call persists cache_hit_tokens after schema migration.
4. GP tool schemas are sorted deterministically by tool name without changing available tools.
```

Manual staging command only after dedicated tests exist:

```bash
git add \
  genesis/core/tracer.py \
  genesis/v4/loop.py \
  genesis/v4/c_phase.py
```

Suggested commit message if accepted later:

```text
Add runtime cache observability by phase and bucket
```

Whole Stack D checks already run:

```text
py_compile passed for all Stack D source/tests
git diff --check passed for all Stack D source/tests
```

Recommendation:

```text
Do not include Stack D in the Yogg value audit commit.
Review/stage D1, D2, D3, D4, and D5 separately.
Use hunk staging for genesis/v4/manager.py because D3 and D4 both touch it.
```

## 6. Stack E: Outcome_domains Phase B

Status:

```text
blocked_until_stacks_are_isolated
```

Source docs:

```text
docs/v6_outcome_domains_runtime_proposal.md
docs/v6_outcome_domains_phase_b_plan.md
```

Implementation target later:

```text
genesis/auto_mode.py
```

Current decision:

```text
Do not implement now.
```

Reason:

```text
auto_mode.py currently has Stack B runtime observability diffs.
Phase B must be a minimal additive report-only patch in a clean or isolated diff.
```

## 7. Working tree coverage audit

Status:

```text
complete
```

Audit result:

```text
git status file count: 51
covered by stack map: 51
orphan diff count: 0
```

Stack coverage counts:

```text
A0: 6
A: 20
B: 3
C1: 5
C2: 2
D1: 3
D2: 2
D3: 5
D4: 4
D5: 3
```

Intentional overlaps:

```text
docs/auto_mode_observability_diff_review.md => Stack A + Stack B
genesis/v4/manager.py => Stack D3 + Stack D4
```

Interpretation:

```text
The current working tree has no orphan files outside the documented stack plan.
The two overlaps are intentional and require human/hunk review before staging.
```

## 8. Aggregate validation

Status:

```text
passed
```

Scope:

```text
A0, A, B, C1, C2, D1, D2, D3, D4 related tests
D5 source included in py_compile only because D5 still lacks dedicated behavioral tests
```

Command:

```bash
python -m pytest tests/test_v6_sao_distillability.py tests/test_v6_outcome_governance_aggregator.py tests/test_v6_outcome_domain_row_consumer.py tests/test_v6_outcome_domain_canonicalizer.py tests/test_v6_outcome_domain_compatibility.py tests/test_v6_yogg_signal_promotion.py tests/test_auto_mode_signal_visibility.py tests/test_provider_router_default_model_failover.py tests/test_shell_health_check.py tests/test_skill_inventory_tool.py tests/test_blackboard_convergence.py tests/test_trace_pipeline_evidence_assessor.py tests/test_node_cleanup_dry_run.py tests/test_contradiction_audit_report.py tests/test_env_fact_freshness_report.py -q
```

Result:

```text
70 passed
```

Compile check:

```text
py_compile passed for all currently documented stack source/test Python files
```

Warnings:

```text
60 deprecation warnings from existing datetime.utcnow() usage in signature_engine.py and manager.py
```

Interpretation:

```text
The split-stack test suite is internally consistent.
D5 remains deferred until dedicated behavioral tests are added.
```

## 9. Suggested immediate action

Immediate action:

```text
Review/stage Stack A first.
```

Reason:

```text
Stack A is read-only, tested, and answers the Yogg value audit objective.
```

Then choose:

```text
Review Stack B separately, or isolate/revert it before Phase B.
```

## 10. Global non-actions

Do not:

```text
commit all current changes as one bundle
deploy mixed auto_mode.py to Yogg by whole-file sync
implement outcome_domains on top of Stack B
change outcome_detected semantics
reset dry-state from knowledge/line evidence
train from this audit chain
```
