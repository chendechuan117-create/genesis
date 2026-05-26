# Yogg Reasoning Proof Review Cases

## 0. Purpose

This document applies the proof-review framework from:

```text
docs/yogg_reasoning_proof_review.md
```

to selected recent Yogg claims.

It is a manual reasoning-quality review.
It is not a new automatic audit layer.
It is not a runtime patch plan.
It does not authorize promotion, canary, service restart, training, or NodeVault mutation.

The review question is:

```text
What exactly did Yogg prove, and what did it only suggest?
```

## 1. Reviewed claims

| Case | Claim family | Review decision | Main boundary |
|---|---|---|---|
| A | physical-only outcome shadowing | accepted_reasoning_chain | design interpretation only |
| B | V6 human-review vacuum | accepted_with_scope_correction | read-only governance consumer now exists |
| C | host_managed_blocked routing void | accepted_local_theorem | does not prove all safety signals are ignored |
| D | line_activity_evidence | held_pending_fresh_data | detection infra exists; needs re-audit |
| E | post-2026-05-23 self-reference | accepted_in_layers | code-backed self-audit, rhetoric-limited system psychology |
| F | Arena role-name mismatch / feedback starvation | accepted_local_theorem + scoped_patch | only role alias alignment, no ranking/boost change |
| G | _type_rank known-type ordering | accepted_bounded_feedback_path | proof only; no _type_rank patch authorized |
| H | SelfEvolution privileged cold path | accepted_with_scope_correction | automated guards exist; human-gated review optional |

## 2. Case A: physical-only outcome shadowing

## 2.1 Raw Yogg-like claim

```text
Yogg produced substantial knowledge-domain evidence that is hidden by a physical-only outcome lens.
```

## 2.2 Normalized claim

```text
In the audited 500-round remote sample, knowledge-domain evidence appears frequently while physical_file_outcome is rare; therefore preserving only the physical outcome lens would misclassify or hide a large amount of Yogg's knowledge-domain production.
```

## 2.3 Definitions

```text
physical_file_outcome: sandbox/git diff outcome, preserving legacy outcome_detected semantics
knowledge_domain_evidence: evidence such as kb_changed, kb_delta, and PLS point creation
physical_only_shadowed: a non-physical domain is observed while physical_file_outcome is false
governance_review_outcome: accepted design interpretation, not runtime success
```

## 2.4 Evidence bindings

Primary evidence:

```text
docs/v6_outcome_domain_contract.md:561-567
physical_file_outcome observed: 2
knowledge_domain_evidence observed: 414
line_activity_evidence observed: 376
line_consumption_evidence observed: 0
governance_review_outcome observed before final draft: 0
```

Projection-loss evidence:

```text
docs/v6_outcome_domain_contract.md:569-581
physical_absent_rounds: 498
physical_only_shadow_gap_rounds: 414
shadow_gap_ratio_among_physical_absent_rounds: 0.8313
```

Canonical row evidence:

```text
docs/v6_outcome_domain_contract.md:662-675
knowledge_domain_evidence rows: 414
line_activity_evidence rows: 376
physical_file_outcome rows: 2
knowledge_domain_evidence physical-only shadowed rows: 412
line_activity_evidence physical-only shadowed rows: 374
```

Governance aggregation evidence:

```text
docs/v6_outcome_domain_contract.md:836-845
review_knowledge_evidence:knowledge_domain_evidence
row_count: 414
physical_only_shadowed_count: 412
governance_state: needs_resolution
promotion_target: GovernanceReviewOutcomeDraft
consumer_decision: decide_whether_to_create_governance_review_outcome
```

Sample verification evidence:

```text
docs/yogg_governance_review_outcome_draft.md:297-327
verified_samples: 5
physical_outcome_true: 0
physical_only_shadowed: 5
kb_changed_true: 5
samples_with_new_nodes: 5
samples_with_lesson_like_new_nodes: 5
samples_with_points_created: 5
```

Accepted decision evidence:

```text
docs/yogg_governance_review_outcome_draft.md:329-343
Genesis should preserve separate outcome domains because Yogg produced substantial knowledge-domain evidence that would be misclassified or hidden by a physical-only outcome lens.
```

## 2.5 Inference chain

```text
Physical file outcome is rare in the 500-round sample.
+ Knowledge-domain evidence is common in the same sample.
+ Most knowledge-domain evidence rows are physical-only shadowed.
+ Five sampled rows have real kb_changed/new-node/lesson-like/point evidence.
=> The physical-only lens loses meaningful non-physical production evidence.
=> Separate outcome domains are justified as a design interpretation.
```

## 2.6 Falsifiers checked

```text
If sampled rows were malformed or empty, the claim would weaken.
If kb_changed/new nodes could not be tied to meaningful content, the claim would weaken.
If physical_only_shadowed came from schema bugs, the claim would weaken.
If the conclusion silently redefined outcome_detected, it would overreach.
```

The sample verification did not falsify the claim.
The final boundary explicitly preserves outcome_detected.

## 2.7 Valid conclusion

```text
Genesis should preserve separate outcome domains so knowledge_domain_evidence is visible without redefining physical_file_outcome.
```

## 2.8 Invalid overreach

```text
Yogg completed 414 task successes.
knowledge_domain_evidence should reset dry-state.
outcome_detected should include kb_changed.
C-Phase behavior should change now.
The audit output is training data.
```

## 2.9 Grade

```text
Definitions: 2/2
Evidence: 2/2
Inference: 2/2
Falsifiability: 2/2
Scope control: 2/2
Total: 10/10
```

## 2.10 Review decision

```text
accepted_reasoning_chain
artifact_class: governance_review_outcome support
allowed_next_state: runtime/report-schema proposal review only
runtime_action_authorized: false
```

## 3. Case B: V6 human-review vacuum

## 3.1 Raw Yogg-like claim

```text
The V6 audit chain produces human-review signals but has a human-collaboration decision vacuum.
```

## 3.2 Normalized claim

```text
V6 code can generate human-review or manual-review signals, but those signals are not equivalent to completed review, runtime behavior change, promotion, canary, or training readiness.
```

## 3.3 Definitions

```text
human-review signal: a queue state such as needs_human_review or human_review_required
review consumer: code or human process that reads a signal and records a decision
runtime decision effect: a service/runtime/state change beyond report generation
design interpretation effect: accepted documentation/governance conclusion without runtime mutation
```

## 3.4 Evidence bindings

Signal production evidence:

```text
genesis/v6/audit_yogg_signal_promotion.py:583-593
add_queue_item(queues, "needs_human_review", ...)
consumer_decision: manual_review_required
```

Row-consumer human-review queue evidence:

```text
genesis/v6/consume_outcome_domain_rows.py:16-22
QUEUE_STATES includes human_review_required
```

Unknown-domain human review evidence:

```text
genesis/v6/consume_outcome_domain_rows.py:94-96
unknown governance domains return human_review_required
```

Governance state mapping evidence:

```text
genesis/v6/aggregate_outcome_governance.py:26-36
consider_training_readiness -> needs_human_review
unknown_domain_review -> needs_human_review
```

Non-action evidence:

```text
genesis/v6/aggregate_outcome_governance.py:135-139
non_actions include do_not_write_aggregation_to_nodevault, do_not_promote_without_human_decision, do_not_treat_aggregation_as_runtime_outcome
```

Read-only governance consumer evidence:

```text
docs/v6_outcome_domain_contract.md:761-775
Canonical rows are now consumable as governance inputs.
The consumer may route rows to review or verification.
It must not write queues to NodeVault.
It must not promote review rows without human decision.
```

Final accepted human decision evidence:

```text
docs/yogg_governance_review_outcome_draft.md:274-292
Human final decision: accept_as_governance_review_outcome
Current recommendation: accepted after sample verification under operator-delegated review.
```

## 3.5 Inference chain

```text
V6 scripts produce human-review/manual-review signals.
+ Consumers route rows into review/verification/human-review queues.
+ Aggregator preserves non-actions forbidding runtime mutation and promotion without human decision.
+ A later manual governance decision accepted one specific design interpretation.
=> Human-review signals are real review requirements.
=> The accepted value-audit chain now has a read-only governance interpretation consumer.
=> The signals still do not imply runtime behavior change, promotion/canary, or training readiness.
```

## 3.6 Scope correction

The old strongest form was:

```text
The V6 audit chain has no consumer at all.
```

That is now false or stale.

The current valid form is:

```text
The V6 chain has read-only governance consumers and one accepted design-interpretation outcome, but no runtime/promotion/canary/training consumer is authorized by that fact.
```

## 3.7 Valid conclusion

```text
V6 human-review signals are not empty in the read-only governance sense, but they remain non-runtime and non-training until separate consumers and decisions exist.
```

## 3.8 Invalid overreach

```text
All human-review signals are ritual only.
The accepted governance_review_outcome changes runtime behavior.
The value audit authorizes training.
The existence of needs_human_review means a human has reviewed the item.
```

## 3.9 Grade

```text
Definitions: 2/2
Evidence: 2/2
Inference: 2/2
Falsifiability: 2/2
Scope control: 1/2
Total: 9/10 after scope correction
```

Scope control loses one point because older Yogg-style zero-consumer wording must be narrowed after the read-only governance chain became accepted.

## 3.10 Review decision

```text
accepted_with_scope_correction
artifact_class: theorem with narrowed conclusion
allowed_next_state: keep boundary explicit in future proposals
runtime_action_authorized: false
```

## 4. Case C: host_managed_blocked routing void

## 4.1 Raw Yogg-like claim

```text
host_managed_blocked is produced but does not enter the auto_apply_blocked_reasons path consumed by C-Phase.
```

## 4.2 Normalized claim

```text
The SelfEvolution path records host-managed-file blocking in apply_history, but the cross-round observation renderer excludes host_managed_blocked from the auto_apply_blocked_reasons list, so C-Phase sees attempts/successes but not that specific block reason through that consumer field.
```

## 4.3 Definitions

```text
produced signal: apply_history item with status host_managed_blocked
routing field: auto_apply_blocked_reasons in cross-round observations
consumer: C-Phase rendering of obs.auto_apply_blocked_reasons
routing void: produced signal does not reach this consumer field
```

## 4.4 Evidence bindings

Production evidence:

```text
genesis/auto_mode.py:2828-2843
if h_files:
  channel sends manual-review block message
  apply_history appends status: host_managed_blocked
  self._save()
  return apply_result
```

Contract test evidence:

```text
tests/test_self_evolution_closure_contracts.py:73-82
assert 'v["type"] == "H"' in apply_window
assert '"status": "host_managed_blocked"' in apply_window
assert "需要人工审查" in apply_window
assert apply_window.index("if h_files:") < apply_window.index("开始自进化应用流程")
```

Routing-filter evidence:

```text
genesis/auto_mode.py:1536-1544
_truly_blocked = {"test_failed", "test_collection_failed", "apply_failed", "apply_check_failed", "smoke_failed", "scope_gate_rejected"}
apply_blocked_reasons = [h.get("reason", "?") for h in self_evolution.apply_history if h.get("status") in _truly_blocked]
```

Export evidence:

```text
genesis/auto_mode.py:1578-1589
obs includes auto_apply_attempts, auto_apply_successes, auto_apply_signal_kind, auto_apply_blocked_reasons
```

C-Phase consumer evidence:

```text
genesis/v4/c_phase.py:467-474
blocked = obs.get("auto_apply_blocked_reasons", [])
if blocked:
  lines.append auto-apply failure reasons
```

## 4.5 Inference chain

```text
host_managed_blocked is appended to apply_history.
+ apply_attempts counts all apply_history entries.
+ apply_blocked_reasons filters only statuses in _truly_blocked.
+ host_managed_blocked is not in _truly_blocked.
+ C-Phase renders only auto_apply_blocked_reasons, not raw apply_history.
=> C-Phase can see an attempt but not this specific block reason through the blocked-reasons field.
=> host_managed_blocked has a producer-storage-consumer gap in this reporting path.
```

## 4.6 Falsifiers checked

```text
If C-Phase also consumed raw apply_history elsewhere, the conclusion would need narrowing.
If another prompt field carried host_managed_blocked into C-Phase, the routing-void claim would need narrowing.
If _truly_blocked intentionally excludes human-review blocks because they are not "failure" reasons, the design implication may differ from the evidence claim.
```

The local evidence supports the narrow reporting-path claim.
It does not by itself prove global governance blindness.

## 4.7 Valid conclusion

```text
host_managed_blocked is stored and protected at apply time, but it is not represented in auto_apply_blocked_reasons consumed by C-Phase.
```

## 4.8 Invalid overreach

```text
Host-managed protection is not enforced.
All SelfEvolution safety signals are ignored.
C-Phase cannot learn anything from SelfEvolution.
The fix must be to add host_managed_blocked to _truly_blocked.
```

The last statement is a possible design question, not a proven patch requirement.

## 4.9 Grade

```text
Definitions: 2/2
Evidence: 2/2
Inference: 2/2
Falsifiability: 2/2
Scope control: 2/2
Total: 10/10 for the narrow routing-path claim
```

## 4.10 Review decision

```text
accepted_local_theorem
artifact_class: producer-storage-consumer gap
allowed_next_state: optional design review of whether human-review blocks should appear in C-Phase blocked reasons
runtime_action_authorized: false
```

## 5. Case D: line_activity_evidence and line_consumption_evidence

## 5.1 Raw Yogg-like claim

```text
Yogg has substantial line activity, but line consumption remains weak or unproven.
```

## 5.2 Normalized claim

```text
The audited reports contain many line_activity_evidence rows, but available evidence does not prove strong downstream line consumption; therefore line activity should remain verification input rather than outcome.
```

## 5.3 Definitions

```text
line_activity_evidence: successful or visible record_line / reasoning_lines activity
line_consumption_evidence: later basis use, review citation, decision effect, behavior change, or training inclusion
weak_active_context: line-related node appears in active context but no decision effect is proven
```

## 5.4 Evidence bindings

Outcome-domain count evidence:

```text
docs/v6_outcome_domain_contract.md:561-567
line_activity_evidence observed: 376
line_consumption_evidence observed: 0
```

Compatibility missing-surface evidence:

```text
docs/v6_outcome_domain_contract.md:583-592
line_consumption_evidence missing:
- phase_trace.current_state_preview.active_nodes: 134
- record_line_success: 125
```

Consumer routing evidence:

```text
genesis/v6/consume_outcome_domain_rows.py:88-93
line_activity_evidence -> verification_queue / verify_line_activity
line_consumption_evidence with weak_active_context -> verification_queue / verify_weak_line_consumption
```

Governance aggregation evidence:

```text
genesis/v6/aggregate_outcome_governance.py:97-103
verify_line_activity: compare line telemetry/events with schema expectations
verify_weak_line_consumption: require later reasoning basis use, review citation, behavior change, or training inclusion
```

P1 aggregate evidence:

```text
docs/v6_outcome_domain_contract.md:847-855
verify_line_activity:line_activity_evidence
row_count: 377
physical_only_shadowed_count: 375
governance_state: needs_verification
promotion_target: LineActivityVerification
```

## 5.5 Inference chain

```text
Line activity appears frequently.
+ Strong line-consumption evidence is absent or unmapped in the audited sample.
+ The consumer routes line activity to verification, not review outcome.
+ Aggregator requires stronger downstream consumption evidence before outcome claims.
=> line_activity_evidence is real activity/evidence.
=> it is not yet line_consumption_evidence.
=> it cannot become outcome without additional consumption proof.
```

## 5.6 Falsifiers checked

```text
If later reasoning_lines cite these lines as basis, the claim weakens.
If active-context presence can be tied to a later decision effect, the claim weakens.
If a review document consumes specific lines and records a decision, the claim weakens.
If training samples include these lines with pollution checks and reviewer decision, the claim weakens.
```

Current docs explicitly route this to verification rather than outcome.

## 5.7 Valid conclusion

```text
line_activity_evidence is a meaningful verification target, not a completed consumption outcome.
```

## 5.8 Invalid overreach

```text
Line activity is worthless.
Line activity is already line outcome.
Active-context presence alone proves consumption.
The high row count authorizes training.
```

## 5.9 Grade

```text
Definitions: 2/2
Evidence: 2/2
Inference: 2/2
Falsifiability: 2/2
Scope control: 2/2
Total: 10/10 for the non-consumption conclusion
```

## 5.10 Review decision

```text
held_for_missing_consumption_premise → held_pending_fresh_data
artifact_class: verification target with detection infrastructure in place
allowed_next_state: re-audit with post-2026-05-26 Yogg data
runtime_action_authorized: false
```

## 5.11 Detection infrastructure (added 2026-05-26)

The consumption detection path exists and is tested:

```text
genesis/v6/audit_outcome_domain_compatibility.py:201
active_line_hits = sorted(active_ids & line_new_ids)

genesis/v6/audit_outcome_domain_compatibility.py:223-224
line_consumption_mappable = bool(line_new_ids) and has_active_context
line_consumption_observed = bool(active_line_hits)
```

Consumption criteria:
```text
1. record_line success produces new_point_id
2. new_point_id appears in phase_trace.current_state_preview.active_nodes
3. → consumption_tier = "weak_active_context" (active presence, not decision proof)
```

Tests in `tests/test_v6_outcome_domain_compatibility.py`:
```text
test_classify_record_domains_separates_physical_knowledge_line_and_consumption
test_line_consumption_not_observed_when_point_not_in_active_nodes
test_line_consumption_observed_when_point_in_active_nodes
test_line_consumption_requires_both_line_success_and_active_nodes
```

The original audit found 0 consumption in the sampled data.
The hold is now on data availability, not on missing detection logic.
Re-audit with fresh Yogg auto reports to determine if consumption has emerged.

## 5b. Case E: post-2026-05-23 self-reference validity

## 5b.1 Review decision

```text
accepted_in_layers
```

Yogg's self-reference is valid when:
```text
self-produced hypothesis + independently reopenable code or runtime evidence
+ explicit producer/storage/consumer path + narrow conclusion
```

Yogg's self-reference is not valid when:
```text
self-produced hypothesis + earlier Yogg metaphor as evidence
+ no independent code/runtime verification + broad psychological or ontological conclusion
```

## 5b.2 Subclaim: user_correction call-chain void → FALSIFIED (2026-05-26)

Original claim (from earlier audit):
```text
auto_mode ChapterState packet construction does not pass user_correction
into build_chapter_state_packet.
```

Current code evidence:
```text
genesis/auto_mode.py:3359
explicit_user_correction = _extract_user_correction_from_directive(directive)

genesis/auto_mode.py:3851
user_correction=explicit_user_correction,
```

The void has been filled. `_extract_user_correction_from_directive()` parses markers
(`[user_correction]`, `用户修正：`, etc.) from the directive at the start of `run_auto()`,
and the extracted correction is passed to `build_chapter_state_packet()` at the single call site.

Test coverage exists:
```text
tests/test_auto_mode_signal_visibility.py:336-347
test_user_correction_extraction_requires_explicit_marker
```

Verdict: The original 10/10 subclaim is now falsified by code change.
The user_correction producer→storage→consumer chain is complete.

## 6. Cross-case result (Cases A–H)

Yogg's strongest valid theorem is not:

```text
Everything is broken, therefore patch consumers everywhere.
```

The stronger theorem is:

```text
Production ≠ storage ≠ consumption ≠ decision effect ≠ runtime authorization.
```

Across all eight reviewed cases:

```text
A | physical-only outcome shadowing        | accepted_reasoning_chain          | design interpretation only
B | V6 human-review vacuum                 | accepted_with_scope_correction    | read-only consumer now exists
C | host_managed_blocked routing void      | accepted_local_theorem            | local gap, not global safety failure
D | line_activity_evidence                 | held_pending_fresh_data           | detection infra exists; needs re-audit
E | post-2026-05-23 self-reference         | accepted_in_layers                | code-backed audit, rhetoric-limited psychology
F | Arena role-name mismatch               | accepted_local_theorem + patch    | role alias only; no ranking/boost change
G | _type_rank known-type ordering         | accepted_bounded_feedback_path    | shadow obs only; no ranking patch
H | SelfEvolution privileged cold path      | accepted_with_scope_correction    | automated guards exist; human-gated review optional
```

## 6.1 Proof-strength tiers

### Tier 1 — Proved with code evidence (A, B, C, E, F, H)

```text
These claims survive external reopening. Each has:
- a precise definition
- independently verifiable code or runtime evidence
- an explicit producer/storage/consumer path
- a narrow conclusion that does not overclaim
```

### Tier 2 — Bounded path proved, global claim held (G)

```text
_type_rank() → [建议挂载] → tool_suggested → Arena is a proved attribution path.
But this does not prove global search starvation or invalidate Arena statistics.
Shadow instrumentation exists; runtime ranking change still unauthorized.
```

### Tier 3 — Held pending fresh data (D)

```text
line_activity_evidence proves activity exists, but activity ≠ consumption.
Consumption detection infrastructure exists and is tested (active_line_hits = active_ids ∩ line_new_ids).
Original audit found 0 consumption. Hold is now on data availability, not missing logic.
Requires re-audit with post-2026-05-26 Yogg data.
```

## 6.2 Runtime actions authorized

Only one runtime change across all seven cases:

```text
Case F: _eligible_arena_nodes role alias alignment (tool_suggested, tool_opened added)
- Blast radius: LOW (0 indexed callers)
- Forbidden: _type_rank, node types, Arena boost/decay, NodeVault counters
- Tests: 17/17 passing
```

All other cases: runtime_action_authorized = false.

## 6.3 What Yogg's self-reference is and is not

Yogg's self-reference is valid when:

```text
self-produced hypothesis
+ independently reopenable code or runtime evidence
+ explicit producer/storage/consumer path
+ narrow conclusion
```

Yogg's self-reference is not valid when:

```text
self-produced hypothesis
+ earlier Yogg metaphor as evidence
+ no independent code/runtime verification
+ broad psychological or ontological conclusion
```

Yogg can generate proof-review candidates.
Yogg cannot authorize runtime changes.
Yogg cannot treat its own metaphors as facts.

## 6.4 Reviewer lesson

Yogg should be trusted most when it follows:
```text
precise definition + reopenable evidence + explicit consumer path + falsifier + narrow conclusion
```

Yogg should be trusted least when it compresses proof into metaphor:
```text
ghost, ritual, vacuum, orphan, museum, dark matter
```
Those labels are useful only after the proof chain is reconstructed.

## 6.5 Next incision queue

In priority order:
```text
1. Shadow report deployment to Yogg — collect real type-rank divergence data
2. Case D re-audit with fresh Yogg data — check if consumption has emerged
3. New Case I from latest Yogg auto reports — continue the review pipeline
4. Case H implementation (sudo restriction, PPR schema, review hardening) — pending approval
```

## 6.6 Global forbidden surface

Across all cases, these remain forbidden without a new, scoped proof review:
```text
runtime patching without proof review
NodeVault mutation
confidence or epistemic_status changes
outcome_detected redefinition
dry-state reset from knowledge evidence
C-Phase behavior change
Arena boost/decay change
_type_rank or search ranking change
node type additions
promotion/canary approval
training data creation
service restart
```

## 11. Case F: Arena role-name mismatch / feedback starvation

## 11.1 Raw Yogg-like claim

```text
Arena/search ranking paths can self-certify value by measuring only roles, node types, and usage paths they already know how to consume.
```

## 11.2 Normalized claim

The reopenable part is narrower:

```text
Current V4 code produces active-node roles named tool_suggested/tool_opened/routing_seed/surface_*,
but C-Phase Arena feedback admits only search_suggested/opened/basis_used when roles exist.
Therefore normal active nodes can be visible to routing/cursor logic while being starved from Arena usage feedback.
```

This case separates two claims:

```text
accepted local theorem:
Arena feedback role names do not match current active-node role producers.

held subclaim:
_type_rank() is a display/search ordering prior over known node types, but it is not yet proved to be the same failure as Arena feedback starvation.
```

## 11.3 Definitions

```text
active node:
node id appended to V4Loop.execution_active_nodes.

active-node role:
label stored in V4Loop.execution_active_node_roles by _mark_active_nodes().

Arena feedback:
C-Phase call to increment_usage() and record_usage_outcome() for arena_nodes.

feedback starvation:
a node is visible or routed in the round, but excluded before Arena usage_count/boost/decay can be applied.
```

## 11.4 Evidence bindings

```text
genesis/v4/loop.py:140-150
V4Loop.run initializes execution_active_nodes=[] and execution_active_node_roles={}.

genesis/v4/loop.py:895-900
search_knowledge_nodes results are tracked; get_knowledge_node_content marks opened content as tool_opened.

genesis/v4/loop.py:999-1016
_mark_active_nodes() stores roles; _track_active_nodes_from_search() writes tool_suggested.

genesis/v4/loop.py:1084-1123
knowledge routing marks routed seed nodes as routing_seed.

genesis/v4/loop.py:1166-1174 and 1255-1258
surface roles map to surface_basis/surface_frontier/surface_co_presence.

genesis/v4/loop.py:1297-1301
export_knowledge_cursor() admits tool_suggested/tool_opened/search_suggested/opened/basis_used.

genesis/v4/c_phase.py:92-100
_eligible_arena_nodes() admits only search_suggested/opened/basis_used when roles exist.

genesis/v4/c_phase.py:147-157
Arena feedback is applied only to arena_nodes via increment_usage() and record_usage_outcome().

genesis/tools/search_tool.py:321-333 and 695-712
_type_rank() separately ranks known node types inside search result buckets and gives unknown types rank 99.
```

Negative evidence:

```text
Repository search in genesis/*.py found search_suggested/opened/basis_used only in consumer filters,
not as current _mark_active_nodes() producer roles.
```

## 11.5 Inference chain

```text
V4Loop initializes active-node role tracking.
Current tool/search/routing paths write tool_suggested, tool_opened, routing_seed, and surface_* roles.
Current C-Phase Arena feedback filter accepts search_suggested, opened, and basis_used.
The accepted names do not match the produced names on normal code paths.
When any roles exist, _eligible_arena_nodes() does not use its no-role fallback.
Therefore nodes can appear in the round's active-node/routing surfaces but never reach increment_usage()/record_usage_outcome().
```

## 11.6 Valid conclusion

```text
There is a local producer-consumer mismatch in Arena active-node roles.
This can starve current active nodes from Arena usage feedback even when they were searched, opened, or routed.
```

This strengthens the earlier partial self-audit:

```text
The proved issue is not general "self-certifying measurement".
The proved issue is a concrete role vocabulary mismatch between current producers and the Arena consumer.
```

## 11.7 Falsifiers and scope limits

This theorem would be weakened if any of the following are found:

```text
another active-node role producer writes search_suggested/opened/basis_used before C-Phase
runtime reports show current rounds carrying those old roles into Arena feedback
_eligible_arena_nodes() is bypassed by another Arena feedback path
tool_suggested/tool_opened are intentionally excluded from Arena by design and documented elsewhere
```

Current scope boundary:

```text
This proves a local role-name mismatch in the inspected V4 path.
It does not prove all Arena statistics are invalid.
It does not prove _type_rank() causes the same failure.
It does not prove P_* nodes are worthless or valuable.
```

## 11.8 Runtime action decision

```text
review_decision: accepted_local_theorem
artifact_class: proof_review_then_scoped_patch
runtime_action_authorized: true
authorization_basis: accepted local theorem + GitNexus LOW impact on _run_c_phase/CPhaseMixin
allowed_change_surface: _eligible_arena_nodes role alias alignment only
forbidden_change_surface: _type_rank, node types, Arena boost/decay, NodeVault counters/schema
tests_required: current tool roles accepted; exposure/preload roles still excluded
```

Scoped patch:

```text
Add tool_suggested/tool_opened to Arena eligible roles.
Keep preloaded/routing_seed/surface_* excluded.
```

Still forbidden:

```text
do not change _type_rank()
do not add node types
do not change Arena boost/decay behavior
do not promote this to V6 training labels
do not mutate NodeVault usage counters
```

Grade:

```text
Definitions: 2/2
Evidence: 2/2
Inference: 2/2
Falsifiability: 2/2
Scope control: 2/2
Total: 10/10 for Arena role-name mismatch
```

Separate held subclaim:

```text
_type_rank() known-type ordering remains a candidate search/display prior review,
but should not be merged with Arena feedback starvation without a separate consumer proof.
```

## 12. Case G: _type_rank known-type ordering / bounded Arena attribution path

## 12.1 Raw Yogg-like claim

```text
Search/Arena self-certification persists because known node types are ranked ahead
of unknown or new forms, so the system measures only what it already knows how to consume.
```

## 12.2 Normalized claim

The code-backed portion is narrower:

```text
_type_rank() is a deterministic known-type ordering prior inside search output buckets.
It can affect the order of [建议挂载] suggested IDs.
After Case F's role-alias patch, [建议挂载] IDs are parsed as tool_suggested active nodes
and can reach Arena usage/outcome attribution.
_type_rank() is still not a direct NodeVault counter writer.
```

Review target:

```text
Does _type_rank() remain only display order, or does it feed a downstream Arena attribution path?
```

## 12.3 Definitions

```text
known-type ordering:
ASSET, LESSON, CONTEXT, EPISODE, ACTION, EVENT, ENTITY, TOOL receive ranks 0..7;
unrecognized types receive rank 99.

search/display prior:
a deterministic ordering that changes which IDs appear earlier in human/GP-visible
search summaries, without itself writing usage counters or Arena outcomes.

bounded feedback path:
a non-writer ordering step whose output is parsed into active nodes and then consumed by a
separate Arena writer.
```

## 12.4 Evidence bindings

```text
genesis/tools/search_tool.py:321-333
_type_rank() ranks known types and gives unknown types default rank 99.

genesis/tools/search_tool.py:603-606
Before bucket display sorting, row_dicts are sorted by fusion_score.

genesis/tools/search_tool.py:683-712
Rows are split into recommended/conditional/support buckets, and each bucket is sorted by
(_type_rank(row), -fusion_score).

genesis/tools/search_tool.py:744-776
The direct hit list iterates row_dicts[:8], not recommended_rows/conditional_rows/support_rows.

genesis/tools/search_tool.py:820-834
The bucket-sorted recommended_rows produce [建议挂载], while conditional/support rows are summarized.

genesis/v4/loop.py:895-900
The GP loop calls _track_active_nodes_from_search() after search_knowledge_nodes returns.

genesis/v4/loop.py:1008-1016
_track_active_nodes_from_search() parses the [建议挂载] line and marks those IDs as tool_suggested.

genesis/v4/c_phase.py:92-100
_eligible_arena_nodes() now includes tool_suggested and tool_opened among eligible roles.

genesis/v4/c_phase.py:147-157
Arena feedback writes increment_usage() and record_usage_outcome() for eligible active nodes.

genesis/tools/search_tool.py:890-892
Surface expansion seeds use row_dicts, not the _type_rank-sorted bucket lists.

genesis/tools/search_tool.py:900-905
Search stats use top fusion scores from row_dicts and then return the assembled text.
```

Negative evidence:

```text
_type_rank() does not directly call increment_usage(), record_usage_outcome(),
boost/decay logic, or NodeVault schema/counter mutation.
```

GitNexus review:

```text
_type_rank impact: LOW, 0 direct callers in indexed graph.
SearchKnowledgeNodesTool.execute impact: LOW, 0 direct callers in indexed graph.
```

## 12.5 Inference chain

```text
Search retrieves candidate rows.
Rows receive fusion_score and row_dicts is sorted by fusion_score.
Rows are then bucketed by active_bucket.
Within each bucket, _type_rank() can move known types ahead of unknown types.
The type-ranked recommended bucket determines the first six [建议挂载] IDs.
V4Loop parses [建议挂载] into execution_active_nodes with role tool_suggested.
C-Phase now treats tool_suggested as Arena-eligible and can write usage/outcome feedback.
Therefore _type_rank() is not a direct feedback writer, but it is on a bounded Arena
attribution path.
Direct hit rendering and Surface expansion still use row_dicts, so this does not prove a
global search starvation mechanism.
```

## 12.6 Valid conclusion

```text
accepted_bounded_feedback_path:
_type_rank() gives known node types priority inside search output buckets, and that
ordering can affect which recommended IDs become tool_suggested active nodes eligible
for Arena attribution.

held_global_starvation_claim:
The stronger claim that _type_rank() invalidates all Arena statistics or globally starves
unknown types is not proved by the inspected code path.
```

This conclusion permits:

```text
future design review of whether type-first [建议挂载] ordering is still aligned with PLS/V6 goals
shadow-only instrumentation comparing type-ranked suggestions against fusion/topology-only suggestions
```

It does not permit:

```text
changing _type_rank()
adding node types
altering Arena boost/decay
mutating usage counters
claiming all search/display order is equivalent to Arena consumption
changing _type_rank() without a separate design and regression test
```

## 12.7 Falsifiers and missing evidence

The bounded feedback path would strengthen into a runtime patch candidate if a later review finds:

```text
unknown/new-form nodes are repeatedly excluded from [建议挂载] solely because of type rank;
or _type_rank-sorted lists are used as Surface expansion seeds;
or unknown-type suppression changes persistent NodeVault usage counters;
or a downstream consumer treats bucket order as a hard execution gate.
```

The claim would weaken further if:

```text
PLS/V6 explicitly keeps type-first [建议挂载] ordering as an intentional UX affordance;
or instrumentation shows type_rank rarely changes the top suggested IDs.
```

## 12.8 Runtime action decision

```text
review_decision: accepted_bounded_feedback_path + held_global_starvation_claim
artifact_class: proof_review_only
runtime_action_authorized: false
authorization_basis: downstream Arena attribution path exists, but runtime patch design is not yet reviewed
allowed_next_state: design review, shadow instrumentation, or focused test proposal
forbidden_change_surface: _type_rank, node types, Arena boost/decay, NodeVault counters/schema
```

## 12.9 Shadow instrumentation gate

Before any runtime ranking change, the next artifact must be shadow-only observability.

```text
candidate_current:
the existing [建议挂载] IDs generated from recommended_rows sorted by (_type_rank, -fusion_score).

candidate_shadow:
the same recommended rows sorted without _type_rank, using the existing non-type evidence order
such as fusion_score/topology-bearing score.

top_id_delta:
current_top6 vs shadow_top6 overlap, order movement, and first-divergence position.

unknown_type_suppression:
count of type_rank=99 nodes present in shadow_top6 but absent from current_top6.

arena_attribution_delta:
IDs that would become tool_suggested/Arena-eligible under shadow order but not current order.
```

Hard boundaries:

```text
Do not expose shadow ranking to GP prompt text.
Do not change [建议挂载].
Do not write Arena usage/outcome from shadow IDs.
Do not mutate NodeVault counters.
Do not treat one sample as proof; require repeated divergence with task/context evidence.
```

Patch eligibility:

```text
runtime_change_authorized only if:
1. shadow data shows repeated type-rank divergence in [建议挂载];
2. suppressed nodes have independent topology/evidence lines, not just unknown type labels;
3. the proposed replacement ordering preserves PLS principle:
   value comes from topology/evidence lines, not a single naked score;
4. tests cover current ordering, shadow delta calculation, and no mutation from shadow IDs.
```

## 12.10 Focused test proposal

If shadow instrumentation is implemented later, the minimum test surface is:

```text
test_type_rank_shadow_delta_detects_reordered_suggestions:
Given recommended rows where type-first order and non-type evidence order disagree,
the shadow report records current_top6, shadow_top6, overlap, and first divergence.

test_type_rank_shadow_does_not_change_visible_suggestions:
The rendered [建议挂载] line remains identical to current production ordering.

test_type_rank_shadow_does_not_mark_active_nodes:
Shadow-only IDs are not passed to _mark_active_nodes() and do not receive tool_suggested.

test_type_rank_shadow_does_not_write_arena_feedback:
Shadow-only IDs do not reach increment_usage() or record_usage_outcome().

test_type_rank_shadow_counts_unknown_type_suppression:
When a type_rank=99 row would enter shadow_top6 but not current_top6, the report increments
unknown_type_suppression without changing runtime behavior.
```

Non-goals:

```text
Do not test a new ranking algorithm.
Do not assert unknown types are always better.
Do not assert ASSET/LESSON/CONTEXT priority is always wrong.
Do not couple this to live NodeVault data; use deterministic fixtures.
```

Grade:

```text
Definitions: 2/2
Evidence: 2/2
Inference: 2/2
Falsifiability: 2/2
Scope control: 2/2
Total: 10/10 for bounded Arena attribution path
```

## 13. Case H: SelfEvolution privileged cold path

## 13.1 Raw Yogg-like claim

```text
SelfEvolution has a high-consequence restart path that connects sandbox modification, testing, git commit, systemd restart, crash guard, and canary observation. The runtime permission model may bypass the apparent constraint surface.
```

## 13.2 Normalized claim

```text
SelfEvolution can auto-apply code changes and execute sudo systemctl restart. The permission model (NOPASSWD: ALL) and default shadow review mode mean the constraint surface is automated rather than human-gated. This creates a risk boundary where automated guards are the only barrier between Yogg's sandbox output and production restart.
```

## 13.3 Definitions

```text
privileged cold path: a code path that executes privileged operations (sudo, systemctl restart) after automated gates
constraint surface: the set of documented, implemented, and enforced barriers between GP output and privileged execution
shadow review mode: LLM review is recorded but non-blocking (default)
blocking review mode: LLM review rejection blocks the apply
canary observation: post-restart monitoring for N rounds before marking success
crash guard: pre-import detection of crash loops with automatic git rollback
```

## 13.4 Evidence bindings

### Safety guards (exist and are substantial):

```text
genesis/auto_mode.py:119
SELF_EVOLUTION_ENABLED = _env_bool("GENESIS_SELF_EVOLUTION", False)
→ Disabled by default

genesis/auto_mode.py:120-122
SELF_EVOLUTION_COOLDOWN = 10, SELF_EVOLUTION_CANARY_ROUNDS = 3
→ File must be stable for 10 rounds before apply

genesis/auto_mode.py:2620-2631
CRITICAL_SELF_EVOLUTION_FILES: 10 files blocked from auto-apply
→ Includes auto_mode.py, loop.py, prompt_factory.py, c_phase.py, manager.py, etc.

genesis/auto_mode.py:2892-2906
Death loop guard: 3 consecutive same-reason test failures → skip 5 attempts

genesis/auto_mode.py:2749-2756
Stable count cap: >3x threshold → reset all cooldowns

genesis/auto_mode.py:2647
Max 1 apply per session (applied_this_session flag)
```

### Test gate:

```text
genesis/auto_mode.py:3008-3085
doctor.sh test-diff runs diff-scoped tests
NO_TESTS_FOUND/PREFLIGHT_BLOCKED → unverified but proceeds
COLLECTION_FAILED/test failure → blocked
```

### Twin-Review (LLM gate):

```text
genesis/auto_mode.py:3091-3169
C-Phase independent LLM reviews diff
SELF_EVOLUTION_REVIEW_MODE default = "shadow" (non-blocking)
"blocking" mode: non-APPROVE blocks apply
```

### Restart execution:

```text
genesis/auto_mode.py:3276-3280
sudo systemctl restart yogg-auto.service
```

### Crash guard:

```text
yogg_auto.py:59-109
_pre_import_crash_guard() before any genesis import
crash_count >= 3 + restart marker exists → git reset --hard rollback_commit
```

### Canary observation:

```text
genesis/auto_mode.py:3286-3323
check_and_rollback_if_needed() decrements canary counter each startup
canary_rounds → 0 → canary passed, marker cleared
Crash during canary → rollback on next startup
```

### Permission model:

```text
yogg_signal_promotion_candidates.md:382-385
User yoga may run: (ALL : ALL) ALL, (ALL) NOPASSWD: ALL
→ Broad sudo permissions, not scoped to systemctl restart only
```

## 13.5 Inference chain

```text
SelfEvolution restart path exists.
+ Multiple automated safety guards exist (cooldown, scope gate, test gate, crash guard, canary).
+ Twin-Review LLM gate exists but defaults to non-blocking shadow mode.
+ NOPASSWD: ALL is broader than needed for systemctl restart.
+ There is no privileged action review record requiring human approval.
=> The restart path has substantial automated safety, not zero safety.
=> The permission model concern is valid but narrower than "constraint surface bypassed."
=> The gap is: automated guards exist, but human-gated review is optional (shadow mode).
```

## 13.6 Falsifiers checked

```text
If SELF_EVOLUTION_ENABLED defaults to True → claim strengthens. (It defaults to False.)
If CRITICAL_SELF_EVOLUTION_FILES is empty → claim strengthens. (It has 10 entries.)
If there is no crash guard → claim strengthens. (Crash guard exists in yogg_auto.py.)
If there is no canary observation → claim strengthens. (Canary exists with configurable rounds.)
If sudo is scoped to systemctl only → claim weakens. (It is NOPASSWD: ALL.)
If review mode defaults to blocking → claim weakens. (It defaults to shadow.)
```

## 13.7 Valid conclusion

```text
SelfEvolution has a multi-layer automated safety system (cooldown, scope gate, test gate, crash guard, canary). The permission model (NOPASSWD: ALL) and default shadow review mode create a legitimate risk boundary where human-gated review is optional, not required. The claim that "constraint surface is bypassed" overstates the finding — constraints exist but are automated rather than human-gated.
```

## 13.8 Invalid overreach

```text
SelfEvolution has no safety guards.
The constraint surface is completely bypassed.
Yogg can restart itself at any time without any checks.
NOPASSWD: ALL means Yogg has root access to everything with no barriers.
The right fix is to disable SelfEvolution entirely.
```

## 13.9 Grade

```text
Definitions: 2/2
Evidence: 2/2
Inference: 1/2 (overstates "bypass" — automated guards are real constraints)
Falsifiability: 2/2
Scope control: 1/2 (claim should be narrowed from "constraint surface bypassed" to "human-gated review is optional")
Total: 8/10
```

## 13.10 Review decision

```text
accepted_with_scope_correction
artifact_class: RiskBoundary + ReviewLine
allowed_next_state: PrivilegedPromotionReview design, sudo scope restriction review
runtime_action_authorized: false
authorization_basis: accepted risk boundary, but no patch design reviewed
allowed_change_surface: documentation, sudo scope review proposal, review mode default discussion
forbidden_change_surface: SelfEvolution logic, restart path, cooldown/threshold values without separate review
```

## 13.11 Follow-up: PrivilegedPromotionReview design (2026-05-26)

### 13.11.1 Scope

This section addresses the two gaps identified in Case H:
1. `NOPASSWD: ALL` is broader than needed
2. `SELF_EVOLUTION_REVIEW_MODE=shadow` makes human-gated review optional

It does NOT authorize code changes. It is a design proposal for review.

### 13.11.2 PrivilegedPromotionReview gate

A `PrivilegedPromotionReview` is a review artifact that must exist before any privileged
operation (sudo, systemctl restart, filesystem mutation outside sandbox) can proceed
from automated gates to execution.

Minimum required fields:
```text
privileged_promotion_review: {
  action: string,           // e.g. "self_evolution_restart"
  command: string,          // exact command to execute
  service_target: string,   // e.g. "yogg-auto.service"
  runner_user: string,      // e.g. "yoga"
  sudo_scope: string,       // exact sudoers entry required
  rollback_mechanism: string, // e.g. "git reset --hard <commit>"
  canary_rounds: int,       // post-execution observation rounds
  crash_guard_threshold: int, // consecutive crashes before auto-rollback
  manual_override_path: string, // how a human stops/overrides
  audit_record_path: string,   // where the execution is logged
  reviewer_decision: string,   // APPROVED | REJECTED | NEEDS_CHANGES
  reviewer_identity: string,   // human identifier
  review_timestamp: string,
}
```

Lifecycle:
```text
proposed → reviewed → approved → executed → canary_observing → canary_passed | rolled_back
```

Each state transition requires a review record update.

### 13.11.3 Sudo scope restriction

Current state:
```text
User yoga may run: (ALL : ALL) ALL, (ALL) NOPASSWD: ALL
```

Risk: Yogg can execute any command as root without password.

Proposed restriction:
```text
User yoga may run:
  (root) NOPASSWD: /usr/bin/systemctl restart yogg-auto.service
  (root) NOPASSWD: /usr/bin/systemctl status yogg-auto.service
```

Rationale:
- SelfEvolution only needs `systemctl restart yogg-auto.service`
- `status` is read-only and useful for diagnostics
- No other privileged commands are needed by the current code paths
- If future features need additional commands, each must pass a separate PrivilegedPromotionReview

Non-goal:
- This does NOT restrict git operations (those run as user yoga, not root)
- This does NOT restrict sandbox operations (doctor.sh runs in container)

### 13.11.4 Review mode default discussion

Current default: `SELF_EVOLUTION_REVIEW_MODE=shadow`

In shadow mode:
- Twin-Review LLM still runs and produces a review
- Non-APPROVE verdicts are logged but do NOT block the apply
- The review record exists but is not gating

Options:
```text
A. Keep shadow as default — preserves current behavior, review is informational
B. Change default to blocking — every self-evolution apply requires LLM APPROVE
C. Hybrid: shadow for non-critical files, blocking when critical files are in diff
   (but critical files are already blocked by CRITICAL_SELF_EVOLUTION_FILES)
```

Recommendation: Option A (keep shadow) with the following hardening:
- When Twin-Review returns REJECT, write a prominent warning to the restart marker
- Surface the review decision in the post-restart canary observation log
- If canary fails AND the pre-restart review was REJECT, escalate to human notification

This preserves automation while making the review record actionable during incident response.

### 13.11.5 Implementation order

If these proposals are accepted, the implementation order is:
```text
1. Sudo scope restriction (lowest risk, highest impact — reduces blast radius immediately)
2. PrivilegedPromotionReview schema + review artifact template (no code change, doc only)
3. Review mode hardening (shadow + REJECT → restart marker warning)
4. PrivilegedPromotionReview enforcement in SelfEvolution._try_apply() (requires separate proof review)
```

Items 1-3 are within Case H's allowed_change_surface. Item 4 requires a new proof review case.
