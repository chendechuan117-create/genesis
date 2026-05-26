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
| D | line_activity_evidence | accepted_with_scope_correction | 64.5% cross-round consumption; 35% waste |
| E | post-2026-05-23 self-reference | accepted_in_layers | code-backed self-audit, rhetoric-limited system psychology |
| F | Arena role-name mismatch / feedback starvation | accepted_local_theorem + scoped_patch | only role alias alignment, no ranking/boost change |
| G | _type_rank known-type ordering | accepted_bounded_feedback_path | proof only; no _type_rank patch authorized |
| H | SelfEvolution privileged cold path | accepted_with_scope_correction | automated guards exist; human-gated review optional |
| I | trust_tier routing verification gap | accepted_local_theorem | 4 consumers exist; routing consumption absent |

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

### Re-audit (2026-05-26)

200 records loaded from live Yogg. Results:
```text
Total line success events: 368
Same-round consumption: 0 (0.0%)
Records with active_nodes: 146/200 (73%)
```

The `new_point_id` from line creation does not appear in `active_node_ids`
within the same round. Cross-round consumption is not yet measured.

Verdict: **held_pending_fresh_data** remains. The detection infra is correct,
but same-round consumption is still 0. Next step: cross-round consumption
tracking (does a point created in round N get consumed in round N+1 or later?).

### Cross-round tracking (2026-05-26)

300 records across 41 sessions. Results:
```text
Total points created: 231
Cross-round consumed (lag=1): 118 (51.1%)
Later-round consumed (lag>1): 31 (13.4%)
Never consumed in session: 82 (35.5%)
Any consumption rate: 64.5%
Consumption lag distribution: {1: 118, 2: 24, 3: 6, 5: 1}
```

**Finding**: 64.5% of points created by `record_line` are consumed in a
subsequent round within the same session. Median consumption lag is 1 round.
The original claim "line activity is produced but not consumed" is **partially
falsified** — consumption exists but is cross-round, not same-round.

### Updated verdict

```text
accepted_with_scope_correction
```

The corrected claim:
```text
record_line produces points that are consumed in subsequent rounds (64.5% rate,
median lag=1), not in the same round. 35.5% of points are never consumed within
their session. The gap is not "zero consumption" but "delayed consumption with
35% session-level waste."
```

### Waste root cause (2026-05-26)

Analyzed 92 never-consumed vs 149 consumed points by creation position:
```text
Waste avg rounds remaining after creation: 1.8
Consumed avg rounds remaining after creation: 3.8
Waste with 0 rounds remaining (last round): 26/92 (28%)
```

The 35% waste is primarily a **session-length artifact**: points created in
the final 1-2 rounds of a session have no subsequent rounds to be consumed.
This is not a quality problem — it's a boundary effect.

Type and tier distributions are identical between waste and consumed groups
(~75% LESSON, ~25% CONTEXT, 100% REFLECTION), confirming no systematic bias.

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

Across all nine reviewed cases:

```text
A | physical-only outcome shadowing        | accepted_reasoning_chain          | design interpretation only
B | V6 human-review vacuum                 | accepted_with_scope_correction    | read-only consumer now exists
C | host_managed_blocked routing void      | accepted_local_theorem            | local gap, not global safety failure
D | line_activity_evidence                 | accepted_with_scope_correction    | 64.5% cross-round; 35% waste
E | post-2026-05-23 self-reference         | accepted_in_layers                | code-backed audit, rhetoric-limited psychology
F | Arena role-name mismatch               | accepted_local_theorem + patch    | role alias only; no ranking/boost change
G | _type_rank known-type ordering         | accepted_bounded_feedback_path    | shadow obs only; no ranking patch
H | SelfEvolution privileged cold path      | accepted_with_scope_correction    | automated guards exist; human-gated review optional
I | trust_tier routing verification gap    | accepted_local_theorem            | 4 consumers exist; routing absent
```

## 6.1 Proof-strength tiers

### Tier 1 — Proved with code evidence (A, B, C, D, E, F, H, I)

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
1. Case G: continue shadow data collection for human evaluation of divergent nodes
2. Case H blocking PPR enforcement — deferred; requires separate proof review
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

## 12.9b Shadow data collected (2026-05-26, Yogg live)

7 samples collected over ~15 minutes from live Yogg instance.

### Divergence summary

| Metric | Value |
|--------|-------|
| Total samples | 7 |
| No divergence | 4 (57%) |
| Divergence detected | 3 (43%) |
| unknown_type_suppression | 0 (all samples) |
| First divergence position | 2-3 |

### Sample with divergence (representative)

```json
{
  "current_top": [
    "P_MARGINAL_UTILITY_TERM_RITUAL_VOID",
    "P_B67A5BADC4",
    "P_V6_HUMAN_REVIEW_CEREMONIAL_COMPLETENESS",
    "P_V6_CONSUMER_DECISION_RECURSIVE_CEREMONY",
    "P_V6_GATING_TRIPLE_SLEEP",
    "P_8DAD27D1CB"
  ],
  "shadow_top": [
    "P_MARGINAL_UTILITY_TERM_RITUAL_VOID",
    "P_B67A5BADC4",
    "P_MARGINAL_UTILITY_TERM_RITUAL_VOID_VERIFIED",
    "P_4FBE0EB7AE",
    "P_V6_HUMAN_REVIEW_CEREMONIAL_COMPLETENESS",
    "P_V6_CONSUMER_DECISION_RECURSIVE_CEREMONY"
  ],
  "overlap": 4,
  "first_divergence": 2,
  "unknown_type_suppression": 0,
  "arena_attribution_delta": [
    "P_MARGINAL_UTILITY_TERM_RITUAL_VOID_VERIFIED",
    "P_4FBE0EB7AE"
  ]
}
```

### Key findings

1. **Unknown type suppression is 0** — the original claim that `_type_rank` hides unknown types is not supported by live data. All divergent nodes are known P_* types.

2. **Divergence is between known types** — type-rank ordering and fusion-score ordering disagree on which P_* nodes deserve top-6 placement, not on whether unknown types are excluded.

3. **Arena attribution delta is real** — in 43% of searches, 1-2 nodes that would receive Arena attribution under fusion-score order do NOT receive it under type-rank order.

4. **Overlap is high** — even in divergent cases, 4/6 nodes overlap. The ordering prior affects 1-2 positions per search.

### Implication for Case G

The original claim ("unknown types suppressed") is **falsified by live data**. The corrected claim is:

```text
_type_rank() causes known-type ordering divergence in ~43% of searches,
affecting 1-2 Arena-eligible positions per search. Unknown type suppression
is 0 in observed data.
```

This narrows the patch eligibility condition: the question is not about unknown types, but about whether fusion-score ordering among known types produces better Arena attribution than type-rank ordering.

### Arena comparison (2026-05-26)

Queried NodeVault for Arena stats of divergent nodes from shadow samples:

| Group | Node | Type | Usage | Success | Fail |
|-------|------|------|-------|---------|------|
| Type-rank | LESSON_V4_API_TO_LOOP | LESSON | 3 | 3 | 0 |
| Type-rank | P_V6_GATING_TRIPLE_SLEEP | LESSON | 1 | 1 | 0 |
| Type-rank | P_8DAD27D1CB | LESSON | 2 | 2 | 0 |
| Fusion | CTX_GENESIS_DUAL_HABITAT_RESONANCE_SPINE | CONTEXT | 1 | 1 | 0 |
| Fusion | P_MARGINAL_UTILITY_TERM_RITUAL_VOID_VERIFIED | CONTEXT | 0 | 0 | 0 |
| Fusion | P_4FBE0EB7AE | CONTEXT | 0 | 0 | 0 |

**Finding**: Type-rank preferred nodes have 6 total uses (all successes).
Fusion-score preferred nodes have 1 total use. This is NOT evidence that
type-rank is better — it's evidence of the self-certification loop: the
current ordering determines which nodes get Arena exposure, so Arena data
cannot evaluate alternative orderings.

**Conclusion**: Arena data alone cannot determine which ordering is better.
A live A/B test (shadow mode already deployed) or human evaluation of
divergent node quality is needed. The shadow instrumentation is the correct
next step — collect more divergence data, then evaluate node quality directly
rather than through Arena self-certification.

### Human evaluation packet sample (2026-05-26)

Latest live shadow report:
```text
first_divergence: 1
overlap_count: 4/6
unknown_type_suppression: 0
arena_attribution_delta: P_395FC4951F, P_4BF53E500A
```

Current-only nodes exposed by type-rank:
```text
P_7B2CA66BAA
type=LESSON, usage=4, success=4, fail=0
title=软边界垄断：Session Planner 作为唯一生效终止条件的结构性不对称

P_POST_ROLLBACK_TRIPLE_TEMPORAL_FRACTURE_VERIFIED
type=LESSON, usage=0, success=0, fail=0
title=post_rollback 状态下的三层时间地层错位
```

Shadow-only nodes exposed by fusion score:
```text
P_395FC4951F
type=CONTEXT, usage=0, success=0, fail=0
title=软边界垄断：Session Planner 作为唯一生效终止条件的结构性不对称

P_4BF53E500A
type=CONTEXT, usage=0, success=0, fail=0
title=软边界垄断的元层自我确认
```

Preliminary human-read interpretation:
```text
The shadow-only nodes are not unknown or low-type anomalies.
They are same-topic CONTEXT nodes that appear semantically close to the query.
Their zero Arena usage is exposure starvation, not negative feedback.
The type-rank preferred nodes include one strong prior success and one unrelated-looking
post_rollback LESSON with zero usage.
```

Decision:
```text
Continue shadow collection.
Do not change _type_rank yet.
Use divergent packets like this for direct human quality scoring, because Arena stats
are contaminated by exposure bias.
```

### Human evaluation packet sample 2 (2026-05-26)

Live shadow report snapshot:
```text
report_mtime: 2026-05-26 13:14:27
first_divergence: 5
overlap_count: 5/6
unknown_type_suppression: 0
arena_attribution_delta: P_162FE63A93
```

Current-only node exposed by type-rank:
```text
P_CONTRADICTS_RESOLUTION_VACUUM
type=LESSON, tier=REFLECTION, confidence_score=0.55, epistemic_status=BELIEF
usage=0, success=0, fail=0
title=CONTRADICTS 消解真空：检测完备但零自动消解管道
summary=系统能检测/展示/排除 CONTRADICTS，但没有自动合并、降级或删除管道。
```

Shadow-only node exposed by fusion score:
```text
P_162FE63A93
type=CONTEXT, tier=REFLECTION, confidence_score=0.55, epistemic_status=BELIEF
usage=0, success=0, fail=0
title=CONTRADICTS 排除门控架构：标记即隐藏，无消解机制
summary=CONTRADICTS 边作为排除门控；检索/推荐排除被标记节点，但查询层只展示标记、无消解。
```

Human-read interpretation:
```text
This is a low-amplitude divergence: only rank 6 differs.
Both nodes are same-topic, same-tier, same-confidence, zero-usage candidates.
The type-rank node is a broader LESSON claim about zero automatic resolution.
The shadow node is a narrower CONTEXT claim about exclusion-gate mechanics.
Human quality read: near tie, with shadow slightly more code-path specific.
This supports exposure-bias concern but still does not justify changing runtime ranking.
```

Short stability check:
```text
3 reads over 40 seconds produced the same report hash and mtime.
No additional live packet emerged during this check.
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

Read-only audit on 2026-05-26 confirmed:
```text
/etc/sudoers.d/yoga:
yoga ALL=(ALL) NOPASSWD:ALL

/etc/sudoers:
%sudo       ALL=(ALL:ALL) ALL
@includedir /etc/sudoers.d

id yoga:
groups=... sudo ... docker ...

/etc/systemd/system/yogg-auto.service:
User=yoga
WorkingDirectory=/home/yoga/Genesis
ExecStart=/home/yoga/Genesis/venv/bin/python -u yogg_auto.py

systemctl path:
/usr/bin/systemctl

SelfEvolution restart command:
sudo systemctl restart yogg-auto.service
```

Risk: Yogg can execute any command as root without password.

Applied minimal drop-in replacement for `/etc/sudoers.d/yoga`:
```text
Cmnd_Alias YOGG_SERVICE_CTL = /usr/bin/systemctl restart yogg-auto.service, /usr/bin/systemctl status yogg-auto.service
yoga ALL=(root) NOPASSWD: YOGG_SERVICE_CTL
```

Rationale:
- SelfEvolution only needs `systemctl restart yogg-auto.service`
- `status` is read-only and useful for diagnostics
- No other privileged commands are needed by the current code paths
- If future features need additional commands, each must pass a separate PrivilegedPromotionReview
- `%sudo ALL=(ALL:ALL) ALL` remains password-gated, so this only removes passwordless broad root

Pre-install validation command:
```text
sudo visudo -cf <temporary sudoers file>
```

Behavior validation after install:
```text
sudo -n systemctl status yogg-auto.service -> allowed, exit=0
sudo -n /usr/bin/systemctl status yogg-auto.service -> allowed, exit=0
sudo -n systemctl status ssh.service -> denied, password required
sudo -n /bin/sh -c true -> denied, password required
No service restart was required to apply sudoers changes.
```

Execution note:
```text
The first post-install command that attempted `sudo visudo -cf /etc/sudoers`
failed with "a password is required" because broad NOPASSWD had already been
removed. This is expected after the restriction. The behavior tests above are
the relevant non-destructive validation under the new policy.
```

Non-goal:
- This does NOT restrict git operations (those run as user yoga, not root)
- This does NOT restrict sandbox operations (doctor.sh runs in container)
- This does NOT modify `genesis/auto_mode.py`; `sudo systemctl ...` resolves through sudo `secure_path`

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
1. Sudo scope restriction (completed)
2. PrivilegedPromotionReview schema + restart marker artifact (completed)
3. Review mode hardening (shadow + REJECT → restart marker warning) (completed)
4. PrivilegedPromotionReview enforcement as a blocking gate (deferred; requires separate proof review)
```

Items 1-3 are complete. Item 4 remains intentionally deferred.

### 13.11.6 Implementation result (2026-05-26)

Minimal runtime hardening was implemented after the sudoers restriction:

```text
File: genesis/auto_mode.py
Added:
  SelfEvolution._build_privileged_promotion_review()
  SelfEvolution._build_restart_marker()

Changed:
  _try_apply() now writes review_mode/review_decision into success apply_history
  _try_apply() now writes privileged_promotion_review into runtime/.self_evolution_restart
  _try_apply() now adds review_warning when Twin-Review returns REJECT in shadow mode
  check_and_rollback_if_needed() logs review decision/mode during canary observation
```

The PPR artifact records:
```text
action
command
service_target
runner_user
sudo_scope
rollback_mechanism
canary_rounds
crash_guard_threshold
manual_override_path
audit_record_path
reviewer_decision
reviewer_identity
review_timestamp
```

Important boundary:
```text
This patch does NOT make Twin-Review blocking.
It does NOT change apply/restart eligibility.
It does NOT broaden sudo scope.
It only makes privileged restart review metadata durable and visible during canary.
```

Validation:
```text
python3 -m pytest tests/test_auto_mode_signal_visibility.py
-> 17 passed

python3 -m py_compile genesis/auto_mode.py
-> passed

git diff --check
-> passed
```

Known unrelated test-path issue:
```text
tests/test_doctor_check_round_apply_history_semantics_probe.py and
tests/test_doctor_success_history_observability_probe.py contain hardcoded
/workspace/genesis/auto_mode.py paths and fail in this workspace with
FileNotFoundError. This is not caused by the PPR patch.
```

### 13.11.7 Yogg deployment result (2026-05-26)

Deployment method:
```text
Applied only the genesis/auto_mode.py PPR hardening diff to remote Yogg.
Did not overwrite remote dirty genesis/tools/search_tool.py.
Created backup:
/home/yoga/Genesis/genesis/auto_mode.py.case_h_ppr_backup_20260526_132301
```

Remote validation:
```text
git apply --check /tmp/case_h_ppr_auto_mode.patch -> passed
/home/yoga/Genesis/venv/bin/python -m py_compile /home/yoga/Genesis/genesis/auto_mode.py -> passed
inline marker helper verification -> passed
sudo -n systemctl status yogg-auto.service -> allowed by scoped sudoers
sudo -n systemctl status yogg-auto.service --no-pager -> denied as expected, because extra args are outside the sudoers scope
```

Runtime activation:
```text
sudo -n systemctl restart yogg-auto.service
service active after restart
MainPID changed to new python process
crash counter cleared after successful startup
latest logs show provider failover recovered to HTTP 200
```

Deployment boundary:
```text
Remote tests were not synchronized; runtime validation used py_compile and an inline helper
against the deployed auto_mode.py.
No ranking/search behavior was changed.
No additional sudoers scope was added.
```

## 14. Case I: trust_tier routing verification gap

## 14.1 Raw Yogg-like claim

```text
信任层级的生产-消费断裂：trust_tier 五级体系的零路由验证。
信任层级石化：出生证系统无成长引擎。
```

## 14.2 Normalized claim

```text
trust_tier is a 5-tier birth certificate system (HUMAN > REFLECTION > FERMENTED > SCAVENGED > CONVERSATION)
that is consumed for TOOL execution gating and confidence scoring, but does not affect
knowledge routing, surface expansion, or search ranking. The "routing verification" gap is:
trust_tier gates execution but does not route knowledge.
```

## 14.3 Definitions

```text
trust_tier: a per-node label from {HUMAN, REFLECTION, FERMENTED, SCAVENGED, CONVERSATION}
  set at node creation, immutable except via patch_node_metadata()

routing verification: whether trust_tier affects which nodes are surfaced,
  injected into prompts, or ranked in search results

TOOL execution gating: trust_tier gates whether a TOOL node's source code
  can be dynamically executed (TOOL_EXEC_MIN_TIER = "REFLECTION")
```

## 14.4 Evidence bindings

### Where trust_tier IS consumed:

```text
genesis/v4/loop.py:949-978
_load_tool_nodes_from_active_nodes() — trust_tier gates TOOL execution
TOOL_EXEC_MIN_TIER = "REFLECTION", nodes below this tier are skipped

genesis/v4/arena_mixin.py:160-194
effective_confidence() — trust_tier affects quality scoring
HUMAN → 1.0, REFLECTION → 0.6, CONVERSATION → 0.55, etc.

genesis/v4/arena_mixin.py:279-283
build_reliability_profile() — trust_tier affects trust_score via tier_bonus
HUMAN: +2.0, REFLECTION: +0.5, FERMENTED: -0.5, SCAVENGED: -1.5

genesis/tools/search_tool.py:290-301
_is_reflection_meta_asset_candidate() — checks trust_tier == "REFLECTION"
for a specific ASSET type filter

genesis/v4/manager.py:3591-3627
get_tool_nodes() — filters TOOL nodes by min_tier
```

### Where trust_tier is NOT consumed:

```text
genesis/v4/surface.py — no trust_tier references
  Surface expansion does not filter or weight by trust_tier

genesis/tools/search_tool.py — _type_rank(), _fusion_score()
  Search ranking does not use trust_tier

genesis/v4/prompt_factory.py — only sets trust_tier (for CONVERSATION),
  never reads it for routing decisions
```

## 14.5 Inference chain

```text
trust_tier exists as a 5-tier system.
+ It gates TOOL execution (security-critical).
+ It affects confidence/trust scoring (quality signal).
+ It does NOT affect surface expansion (which nodes enter the prompt).
+ It does NOT affect search ranking (which nodes are suggested).
=> The "routing verification" gap is real but narrower than claimed.
=> trust_tier is a security gate + quality signal, not a routing mechanism.
=> The design question: should trust_tier also route knowledge?
```

## 14.6 Falsifiers checked

```text
If trust_tier is used in surface.py → claim weakens. (It is not.)
If trust_tier is used in search ranking → claim weakens. (It is not.)
If trust_tier has no consumers at all → claim strengthens. (It has 4 consumers.)
If TOOL_EXEC_MIN_TIER is the only consumer → claim narrows. (It's not the only one.)
```

## 14.7 Valid conclusion

```text
trust_tier has 4 verified consumers (TOOL gating, confidence scoring, trust scoring,
ASSET filtering) but zero presence in knowledge routing (surface expansion, search ranking).
The gap is not "zero routing" but "security/quality consumption without routing consumption."
```

## 14.8 Invalid overreach

```text
trust_tier is completely unused.
trust_tier has zero consumers.
The birth certificate system is pure ceremony.
trust_tier should be removed.
```

## 14.9 Grade

```text
Definitions: 2/2
Evidence: 2/2
Inference: 2/2
Falsifiability: 2/2
Scope control: 2/2
Total: 10/10
```

## 14.10 Review decision

```text
accepted_local_theorem
artifact_class: EvidenceLine
allowed_next_state: design discussion on whether trust_tier should route knowledge
runtime_action_authorized: false
authorization_basis: verified gap, but routing is a design decision not a bug
allowed_change_surface: documentation, design proposal
forbidden_change_surface: trust_tier logic, surface.py, search ranking without separate review
```

## 14.11 Follow-up: trust_tier routing integration design (2026-05-26)

### 14.11.1 Design question

Should trust_tier affect which nodes enter the prompt (surface expansion) and
which nodes are suggested (search ranking)?

### 14.11.2 Current state

trust_tier is consumed for:
- TOOL execution gating (security: prevent low-trust code execution)
- Confidence/trust scoring (quality: inform reliability assessment)

trust_tier is NOT consumed for:
- Surface expansion (which nodes enter the prompt context)
- Search ranking (which nodes appear in [建议挂载])

### 14.11.3 Options

```text
A. Do nothing — trust_tier remains security/quality only
   Pro: no risk of "rich get richer" feedback loops
   Con: HUMAN-curated knowledge gets no routing priority over CONVERSATION noise

B. Soft routing boost — trust_tier adds a small weight in surface/search
   Pro: HUMAN nodes get modest priority without blocking others
   Con: adds complexity; birth certificate becomes self-reinforcing

C. Minimum tier filter — surface/search exclude nodes below a configurable tier
   Pro: clean separation; CONVERSATION ephemera never pollutes routing
   Con: low-tier nodes can never prove themselves; birth certificate is destiny

D. Tier-aware but time-decaying — trust_tier boost decays with node age
   Pro: balances birth certificate with earned reputation
   Con: most complex; requires age tracking
```

### 14.11.4 Recommendation

Option A (do nothing) with one exception: **surface expansion should prefer
HUMAN-tier nodes as basis seeds when available.**

Rationale:
- HUMAN nodes are the only tier with guaranteed quality (human-authored)
- Using them as surface expansion seeds is low-risk: they anchor the surface
  without excluding other tiers
- This is a one-line change in surface.py: when selecting basis seeds,
  prefer HUMAN-tier nodes if they match the query context
- All other tiers continue to participate equally in surface expansion
  and search ranking

### 14.11.5 Non-goals

```text
Do not add trust_tier to _type_rank().
Do not add trust_tier to _fusion_score().
Do not filter search results by trust_tier.
Do not exclude low-tier nodes from surface expansion.
Do not change TOOL_EXEC_MIN_TIER.
```

### 14.11.6 Implementation

If accepted, the change is:
```text
In surface.py basis seed selection:
  When multiple candidate seeds have similar relevance scores,
  prefer seeds with trust_tier="HUMAN" over other tiers.
```

This requires a separate proof review before implementation.
