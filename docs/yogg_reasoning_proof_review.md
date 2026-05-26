# Yogg Reasoning Proof Review

## 0. Purpose

This document defines how to review Yogg's semantic outputs as proof chains.

It is not a patch plan.
It is not another outcome-domain audit layer.
It is not a runtime proposal.

The review question is:

```text
Did Yogg prove its claim through a traceable reasoning chain?
```

Not:

```text
Did Yogg's final answer sound plausible?
Can we patch the local code path it mentioned?
How many nodes or reports did Yogg produce?
```

The intended analogy is a mathematical assignment review:

```text
A final answer can be correct for the wrong reason.
A final answer can be useful but overgeneralized.
A partial proof can be more valuable than a correct-looking slogan.
```

Therefore, Yogg outputs should be reviewed by their definitions, evidence bindings, inference steps, and generalization boundaries.

## 1. Relationship to existing audit documents

Related documents:

```text
docs/yogg_signal_promotion_candidates.md
docs/yogg_signal_promotion_review.md
docs/v6_outcome_domain_contract.md
docs/yogg_governance_review_outcome_draft.md
docs/yogg_value_audit_handoff.md
```

Those documents answer governance and promotion questions:

```text
Which signals can enter review?
Which outcome domains should be preserved?
Which aggregate can become a governance_review_outcome?
```

This document answers a prior epistemic question:

```text
Was the reasoning that produced the signal good?
```

A signal can be promotion-worthy while its reasoning still needs review.
A reasoning chain can be high quality even if no runtime action follows.

## 1.1 Operational gate

Yogg's output may be used as a source of review candidates, but not as direct authorization.

The fixed operating model is:

```text
Yogg = theorem proposer
Reviewer = proof checker
Codebase/runtime evidence = independent oracle
Patch queue = only for scoped, externally reopenable claims
```

This means the review flow is:

```text
Yogg claim
→ normalize the claim
→ reconstruct the proof chain
→ bind each nontrivial step to independently reopenable evidence
→ classify the claim
→ decide the permitted artifact
```

Classification:

```text
accepted_theorem
accepted_with_scope_correction
partial_skeleton
rhetoric_only
rejected_or_falsified
```

Patch eligibility:

```text
accepted_theorem + low blast radius + scoped engineering translation
accepted_with_scope_correction + low blast radius + scoped engineering translation
```

Non-eligible claims:

```text
partial_skeleton
rhetoric_only
rejected_or_falsified
```

Non-eligible claims can still produce:

```text
proof_review_only
report_only_observability
documentation_boundary
future_candidate
```

They cannot produce:

```text
runtime behavior change
ranking change
governance promotion
training sample
NodeVault mutation
service restart
```

The engineering translation must be narrower than the metaphor.

Examples:

```text
"ghost transmission" -> source/snapshot label, not memory rewrite
"gradient amnesia" -> retention metadata/counts, not removal of OOM compaction
"self-certifying measurement" -> proof review/report-only audit, not ranking change
```

## 2. Non-actions

This review must not directly:

```text
modify NodeVault
change confidence or epistemic_status
change outcome_detected
reset dry-state
change C-Phase behavior
restart services
patch runtime
promote or canary a change
train models
create another automatic audit layer
```

A proof review may produce only one of these artifacts:

```text
accepted_reasoning_chain
held_for_missing_premise
rejected_overgeneralization
split_required
candidate_for_governance_review
candidate_for_runtime_schema_proposal
candidate_for_training_sample_later
```

If a claim enters implementation after this review, the implementation must be recorded separately as:

```text
runtime_action_authorized: true|false
authorization_basis:
blast_radius:
allowed_change_surface:
forbidden_change_surface:
tests_required:
rollback_boundary:
```

Default:

```text
runtime_action_authorized: false
```

## 3. Core review object

Each Yogg claim should be rewritten into this shape before judging it:

```text
claim_id:
source_refs:
raw_claim:
normalized_claim:
definitions:
evidence_bindings:
inference_steps:
missing_premises:
falsifiers:
valid_conclusion:
invalid_overreach:
artifact_class:
review_decision:
```

The reviewer should not start from the recommended fix.
The reviewer should start from the proof.

## 4. Proof levels

Yogg outputs should be classified by proof level.

| Level | Name | Review meaning |
|---|---|---|
| L0 | phrase | A useful phrase or metaphor, but no proof chain yet |
| L1 | observation | A concrete fact about code, DB, report, service, or command output |
| L2 | lemma | A local inference from one or more observations |
| L3 | theorem | A structural claim supported by multiple linked lemmas |
| L4 | corollary | A design implication that follows if the theorem is accepted |
| L5 | doctrine | A general reusable principle, requiring cross-system evidence and counterexample review |

The most common mistake is to treat an L4 corollary as if it were the proof.

Example:

```text
"Add outcome_domains" is not the theorem.
"A physical-only outcome lens hides knowledge-domain evidence" is closer to the theorem.
```

## 5. Required proof components

## 5.1 Definitions

A strong Yogg proof defines its terms before using them.

Good definitions have stable boundaries:

```text
activity_signal: produced or visible behavior trace
physical_file_outcome: sandbox/git diff outcome
knowledge_domain_evidence: NodeVault or PLS knowledge change evidence
line_activity_evidence: record_line or reasoning_lines activity
line_consumption_evidence: later retrieval, review, or basis use of a line
governance_review_outcome: accepted review decision that changes design interpretation
```

Weak definitions are slogans:

```text
valuable
real
alive
dead
ghost
ritual
semantic progress
```

Slogans can be useful labels, but only after they can be translated into operational definitions.

## 5.2 Evidence bindings

Every nontrivial claim needs evidence bindings.

Acceptable evidence refs:

```text
file path + line range
round report path + field path
SQLite table + query result
specific NodeVault node_id + full_content excerpt
systemd service file field
captured command output
cross-round sample id
```

Insufficient evidence refs:

```text
node title only
round count only
confidence score only
progress_class only
metaphor only
single final summary sentence
```

A reviewer should ask:

```text
Can this evidence be reopened and checked without trusting the conclusion text?
```

## 5.3 Inference steps

A strong proof states each step.

Preferred shape:

```text
Observation A
+ Observation B
=> Lemma C
+ Observation D
=> Theorem E
=> Corollary F
```

Weak shape:

```text
Observation A
=> broad architectural conclusion
=> patch recommendation
```

The review should mark missing intermediate steps explicitly.

## 5.4 Falsifiers

Every strong Yogg theorem should name what would falsify it.

Examples:

```text
A claimed zero-consumer signal is falsified by a real consumer that changes decision state.
A claimed physical-only shadow gap is weakened if sampled rows lack meaningful knowledge content.
A claimed human-review vacuum is weakened if a human review interface reads and resolves the queue.
A claimed line-consumption gap is weakened if reasoning_lines are later used as basis or selected into active context with decision effect.
```

A claim with no possible falsifier is not ready to become a theorem.

## 5.5 Overreach boundary

A good review separates valid conclusion from invalid overreach.

Example:

```text
Valid:
The audited sample shows many knowledge-domain evidence rows are physical-only shadowed.

Invalid overreach:
Yogg completed hundreds of task successes.
```

Example:

```text
Valid:
needs_human_review is produced and no runtime/human consumer was found in the inspected path.

Invalid overreach:
Human review is impossible in Genesis as a whole.
```

## 6. Standard proof templates

## 6.1 Producer-storage-consumer-decision chain

This is Yogg's strongest recurring proof form.

```text
producer:
storage:
visibility:
consumer:
decision_effect:
breakpoint:
conclusion:
```

Interpretation:

```text
A signal is not an outcome merely because it is produced.
A signal becomes stronger when it reaches a consumer.
A consumed signal becomes outcome-like only when it changes decision or behavior.
```

Review questions:

```text
Who produces the signal?
Where is it stored?
Who can read it?
Who actually reads it?
What decision changes because of it?
Where is that decision observable?
```

## 6.2 Domain-separation proof

Use when Yogg claims that one lens hides another type of evidence.

```text
source domain:
target domain:
projection lens:
shadowed evidence:
sample count:
representative samples:
conclusion:
```

Review questions:

```text
Are the domains defined independently?
Is the projection loss measured?
Are examples sampled and opened?
Does the conclusion preserve old semantics instead of redefining them silently?
```

## 6.3 Governance-vacuum proof

Use when Yogg claims that a governance signal is ritualistic.

```text
governance signal produced:
queue or state written:
claimed human/system consumer:
actual consumer found:
action forbidden by constraints:
decision effect:
conclusion:
```

Review questions:

```text
Is the signal only displayed, or is it routed?
Is there an interface for a reviewer?
Is a decision recorded?
Does any downstream state depend on the decision?
```

## 6.4 Topology-consumption proof

Use when Yogg reasons about PLS points, lines, surfaces, or orphan/ghost/dark-matter nodes.

```text
node or line exists:
edge or reasoning_line exists:
retrieval visibility:
usage or basis evidence:
active-context evidence:
decision effect:
conclusion:
```

Review questions:

```text
Is the object physically present?
Is it topologically connected?
Is it retrievable?
Is it consumed as basis?
Does later reasoning or governance depend on it?
```

## 7. Worked example: host_managed_blocked routing void

Source node:

```text
P_HOST_MANAGED_BLOCKED_ROUTING_VOID_VERIFIED
```

## 7.1 Normalized claim

```text
host_managed_blocked is produced as a high-consequence SelfEvolution signal, but it does not enter governance decision flow because the consumer whitelist excludes it.
```

## 7.2 Definitions

```text
produced signal: apply_history entry with status host_managed_blocked
governance consumer: cross-round observations consumed by C-Phase or auto governance logic
routing gate: whitelist of statuses extracted into apply_blocked_reasons
```

## 7.3 Evidence bindings

Claimed evidence shape:

```text
auto_mode.py produces host_managed_blocked in apply_history
_truly_blocked whitelist excludes host_managed_blocked
apply_blocked_reasons is derived only from whitelisted statuses
C-Phase consumes auto_apply_blocked_reasons, not raw apply_history
```

The proof is strong if the cited line ranges remain valid and the database or state sample confirms real host-managed entries.

## 7.4 Inference chain

```text
host_managed_blocked is written
+ apply_blocked_reasons excludes it
+ C-Phase consumes apply_blocked_reasons
=> the signal is stored but not decision-consumed
=> this is a producer-storage-consumer break
```

## 7.5 Valid conclusion

```text
The signal is activity/evidence at the runtime storage level, but not a governance outcome.
```

## 7.6 Invalid overreach

```text
All SelfEvolution safety signals are ignored.
```

That broader claim would require checking every safety status and every consumer path.

## 7.7 Review decision

```text
accepted_reasoning_chain
artifact_class: theorem candidate
```

## 8. Worked example: P_* role-filter isolation

Source node:

```text
P_GP_EXPLORATION_ROLE_FILTER_ISOLATION_VERIFIED
```

## 8.1 Normalized claim

```text
P_* concept nodes are not merely suffering from a naming problem; they are structurally excluded from Arena feedback because eligible consumer roles do not include GP-produced nodes by default.
```

## 8.2 Definitions

```text
P_* node: GP concept-exploration point
consumer role: role that allows a node to enter Arena feedback or active consumption
usage evidence: usage_count, basis use, opened/search roles, or active context selection
```

## 8.3 Evidence bindings

Claimed evidence shape:

```text
eligible_roles = {search_suggested, opened, basis_used}
GP-produced P_* nodes do not automatically receive these roles
1505 P_* nodes observed
1504 P_* nodes have usage_count=0
total usage_count is very low
```

## 8.4 Inference chain

```text
P_* nodes are produced
+ eligible consumer roles exclude their production role
+ usage distribution is near zero
=> production path and consumption path do not overlap
=> the issue is role-filter isolation, not merely naming
```

## 8.5 Valid conclusion

```text
P_* production does not imply P_* consumption.
```

## 8.6 Invalid overreach

```text
All P_* nodes are worthless.
```

A zero-usage node can still be a candidate if it enters a later review or basis chain.

## 8.7 Review decision

```text
accepted_reasoning_chain
artifact_class: theorem candidate
```

## 9. Worked example: V6 human-review vacuum

Source nodes:

```text
P_V6_HUMAN_COLLABORATION_DECISION_VACUUM
P_V6_HUMAN_COLLABORATION_DECISION_VACUUM_VERIFIED
P_V6_HUMAN_COLLABORATION_DECISION_VACUUM_VERIFIED_DEEP
P_GOVERNANCE_HUMAN_REVIEW_PHANTOM_COMMITMENT
```

## 9.1 Normalized claim

```text
The V6 governance audit chain can produce human-review signals, but those signals do not by themselves prove that human review has occurred or that runtime behavior changed.
```

## 9.2 Definitions

```text
human-review signal: needs_human_review or human_review_required
human-review consumer: an interface or process that lets a human accept, reject, or resolve the item
runtime decision effect: any state change beyond report generation
read-only governance artifact: a report or draft that changes interpretation but not runtime behavior
```

## 9.3 Evidence bindings

Claimed evidence shape:

```text
audit_yogg_signal_promotion.py produces needs_human_review
consume_outcome_domain_rows.py can return human_review_required
aggregate_outcome_governance.py can emit READY_FOR_*_HUMAN_REVIEW
dry_run=True is present
non-actions forbid NodeVault writes, runtime changes, and training
no runtime consumer or human-review callback was found in the inspected path
```

## 9.4 Inference chain

```text
human-review signals are produced
+ outputs are read-only/dry-run
+ no resolver consumer is present
=> the signal is a review requirement, not completed review
=> human collaboration exists as a declared need, not yet as runtime governance action
```

## 9.5 Important correction

The later value audit completed a read-only elevation chain ending in an accepted governance_review_outcome.

Therefore the valid current form is narrower:

```text
The old zero-consumer claim is no longer true for the read-only governance interpretation chain.
It remains true for runtime behavior, service control, promotion/canary, and training unless separate consumers are added.
```

## 9.6 Valid conclusion

```text
The audit can change design interpretation, but it does not change runtime behavior.
```

## 9.7 Invalid overreach

```text
The V6 audit chain has no consumer at all.
```

That was true only before the read-only governance chain was accepted.

## 9.8 Review decision

```text
accepted_with_scope_correction
artifact_class: theorem with narrowed conclusion
```

## 10. Worked example: physical-only outcome shadowing

Source chain:

```text
Yogg output
→ signal promotion queue
→ outcome-domain contract
→ canonical rows
→ governance aggregator
→ sample verification
→ accepted governance_review_outcome
```

## 10.1 Normalized claim

```text
Genesis should preserve separate outcome domains because Yogg produced substantial knowledge-domain evidence that would be misclassified or hidden by a physical-only outcome lens.
```

## 10.2 Definitions

```text
physical_file_outcome: physical sandbox/git diff outcome
knowledge_domain_evidence: knowledge-producing report evidence such as kb_changed, kb_delta, and PLS point creation
physical_only_shadowed: knowledge-domain evidence exists while physical_file_outcome is false
governance_review_outcome: accepted design interpretation outcome, not runtime success
```

## 10.3 Evidence bindings

Remote 500-round sample:

```text
physical_file_outcome observed: 2
knowledge_domain_evidence observed: 414
line_activity_evidence observed: 376
P0 aggregate row_count: 414
physical_only_shadowed_count: 412
verified_samples: 5
physical_outcome_true: 0
kb_changed_true: 5
samples_with_lesson_like_new_nodes: 5
samples_with_points_created: 5
```

## 10.4 Inference chain

```text
physical outcome is rare in the audited sample
+ knowledge-domain evidence is common
+ most knowledge-domain evidence is physical-only shadowed
+ sampled rows contain real lesson-like node and point evidence
=> physical-only outcome lens loses important evidence
=> outcome semantics need separate domains
```

## 10.5 Valid conclusion

```text
Preserve physical_file_outcome as physical-only and represent knowledge_domain_evidence separately.
```

## 10.6 Invalid overreach

```text
knowledge_domain_evidence equals task success
line_activity_evidence equals line consumption
outcome_detected should be redefined
C-Phase should reset dry-state from kb_changed
```

## 10.7 Review decision

```text
accepted_reasoning_chain
artifact_class: governance_review_outcome support
```

## 11. Reasoning quality rubric

Score each proof chain on five axes.

| Axis | 0 | 1 | 2 |
|---|---|---|---|
| Definitions | undefined slogans | partial terms | operational definitions |
| Evidence | title or summary only | one reopenable source | multiple reopenable bindings |
| Inference | jumpy | mostly ordered | explicit step chain |
| Falsifiability | none | implicit | named falsifiers |
| Scope control | overgeneralized | some caveats | valid conclusion separated from overreach |

Interpretation:

```text
0-3: phrase or weak observation
4-6: candidate lemma, needs evidence
7-8: theorem candidate
9-10: strong theorem or governance-review support
```

A high score does not imply runtime action.
It only means the reasoning chain is good.

## 12. Review workflow

Use this workflow for future Yogg output reviews.

## 12.1 Select one claim

Do not review a cluster title as one object.
Split it into atomic claims.

Bad:

```text
Yogg says governance is ritualistic.
```

Good:

```text
needs_human_review is produced by script A, but no resolver consumer changes state B.
```

## 12.2 Reconstruct the proof

Write the chain in this order:

```text
definitions
evidence
inference
conclusion
```

Do not start with proposed fixes.

## 12.3 Locate the first weak link

Common weak links:

```text
term not defined
evidence not reopenable
consumer path assumed but not checked
sample count used without sample inspection
metaphor used as proof
old zero-consumer claim not updated after a new consumer appears
design implication treated as runtime authorization
```

## 12.4 Decide artifact type

Possible outputs:

```text
Observation
Lemma
Theorem
Corollary
GovernanceSignal
RuntimeProposalCandidate
TrainingCandidateLater
RejectedSlogan
```

## 12.5 Preserve stop boundaries

A proof review can justify a next question.
It cannot automatically justify a patch.

## 13. How this should change review behavior

When reading Yogg output, the reviewer should avoid these shortcuts:

```text
find problem → patch problem
find field → add consumer
find conclusion → accept conclusion
find metaphor → summarize metaphor
find numbers → declare quality
```

Instead, use:

```text
claim → definitions → evidence bindings → inference steps → falsifiers → scope boundary → artifact class
```

The central question is:

```text
What exactly did Yogg prove, and what did it merely suggest?
```

## 14. Current accepted meta-lesson

Yogg's strongest recent reasoning is not a set of isolated bug reports.

It is a repeated structural proof pattern:

```text
production without consumption is not outcome
consumption without decision effect is not outcome
review without accepted decision is not governance outcome
activity without evidence binding is not proof
proof without scope control becomes overreach
```

The reviewer should preserve that distinction before deciding whether any code or schema should change.
