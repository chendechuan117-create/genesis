# V6 Outcome-Domain Contract

Final value audit summary:

```text
docs/yogg_value_audit_summary.md
```

Runtime/report-schema proposal:

```text
docs/v6_outcome_domains_runtime_proposal.md
```

## 0. Purpose

This contract defines how Genesis V6 should interpret outcomes without collapsing different evidence surfaces into one success signal.

It is a design contract, not a runtime patch.

It exists because recent Yogg review showed this mismatch:

```text
knowledge_domain_evidence: high
line_activity_evidence: high
physical_file_outcome: rare
line_consumption_evidence: weak or absent
```

The contract prevents this mistake:

```text
activity_created == evidence_verified == outcome
```

## 1. Scope

This contract applies to:

```text
Yogg auto reports
V6 audit scripts
PLS Point/Line/Surface review
S-A-O distillability review
future dry-state and promotion design
```

It does not apply direct runtime behavior changes.

Non-actions:

```text
Do not change C-Phase behavior from this document alone.
Do not reset dry-state logic from this document alone.
Do not modify NodeVault.
Do not promote confidence or epistemic_status.
Do not restart services.
Do not train models directly from this contract.
```

## 2. Outcome vocabulary

Minimum terms:

```text
activity_signal: something was produced, written, counted, classified, or named.
evidence_signal: something has concrete source refs and a read-only verification path.
consumption_signal: evidence was selected or used by a later process.
outcome_signal: consumed evidence changed a decision, behavior, review state, promotion state, canary state, or training readiness.
```

Core rule:

```text
activity_signal != evidence_signal != consumption_signal != outcome_signal
```

## 3. Domain overview

V6 outcome reporting should separate at least these domains:

```text
physical_file_outcome
knowledge_domain_evidence
line_activity_evidence
line_consumption_evidence
governance_review_outcome
```

These domains are not interchangeable.

## 4. Domain contracts

## 4.1 physical_file_outcome

Definition:

```text
Tracked files changed in a way observable by sandbox/git diff or equivalent physical artifact checks.
```

Typical sources:

```text
outcome_detected
sandbox diff hash
tracked git diff
patch apply report
canary pre/post artifact diff
```

Primary consumer:

```text
auto_mode physical dry-state logic
patch/canary review
human code review
```

Decision it can change:

```text
Whether a round produced a physical artifact.
Whether patch review should proceed.
Whether physical dry-state counters should reset.
```

Observable consumption:

```text
dry counter changes
patch review entry
canary run input
PR or commit candidate
```

Allowed effects:

```text
May affect physical dry-state.
May enter patch/canary pipeline.
May support training only when paired with action and outcome labels.
```

Forbidden interpretation:

```text
Physical file outcome is not the only valid outcome domain for concept exploration.
Absence of physical file outcome does not imply absence of knowledge-domain evidence.
```

## 4.2 knowledge_domain_evidence

Definition:

```text
NodeVault or report-level knowledge structures changed or exposed reviewable knowledge evidence.
```

Typical sources:

```text
kb_changed
kb_delta.new_nodes
kb_delta.updated_nodes
knowledge_nodes created/updated counts
node_content evidence
review documents
```

Primary consumer:

```text
knowledge governance queue
manual review
future S-A-O distillability audit
future outcome-domain aggregator
```

Decision it can change:

```text
Whether a signal enters review.
Whether a knowledge claim needs verification or resolution.
Whether a design contract should be drafted.
```

Observable consumption:

```text
queue item created
review decision recorded
contract draft created
verification command attached
```

Allowed effects:

```text
May affect governance queue state.
May create review work.
May support training-readiness only after review consumption.
```

Forbidden interpretation:

```text
Knowledge writes alone do not reset physical dry-state.
Knowledge writes alone do not prove downstream use.
Knowledge writes alone do not increase confidence.
```

## 4.3 line_activity_evidence

Definition:

```text
PLS Line activity was produced or attempted.
```

Typical sources:

```text
pls_telemetry.lines_created
pls_telemetry.cross_round_lines
pls_telemetry.same_round_lines
pls_telemetry.line_errors
events.record_line
NodeVault.reasoning_lines count
```

Primary consumer:

```text
PLS Line Outcome Schema review
yogg_signal_promotion_queue
line/graph contract review
```

Decision it can change:

```text
Whether line/graph outcome schema is needed.
Whether successful and rejected Line attempts must be separated.
```

Observable consumption:

```text
line evidence enters review queue
line rejection analysis is created
line/graph contract is drafted
```

Allowed effects:

```text
May affect line-specific review queues.
May justify defining line_delta or graph_delta.
```

Forbidden interpretation:

```text
Line creation is not Line outcome.
Line count is not evidence of future reasoning impact.
Line activity should not reset physical dry-state.
```

## 4.4 line_consumption_evidence

Definition:

```text
A line-created node or reasoning line was later used by another process.
```

Evidence tiers:

```text
weak: line-created node appears in active context
structural: later reasoning_lines.basis_point_id = earlier.new_point_id
governance: review decision cites the line-created node
behavioral: later decision/action changed because of the line evidence
training: included in a training-ready S-A-O sample
```

Primary consumer:

```text
line consumption audit
knowledge governance review
future S-A-O sample builder
```

Decision it can change:

```text
Whether a Line can move from activity evidence to consumption evidence.
Whether a Line is eligible for outcome or training-readiness review.
```

Observable consumption:

```text
active context sample
reasoning_lines self-join sample
review decision reference
trace span or queue transition
training sample reference
```

Allowed effects:

```text
Weak evidence may enter needs_verification.
Structural or governance evidence may enter resolved evidence state.
Behavioral or training evidence may support outcome claims.
```

Forbidden interpretation:

```text
Active context selection alone is not resolved outcome.
Storage in reasoning_lines is not consumption.
Availability in search is not consumption.
```

## 4.5 governance_review_outcome

Definition:

```text
A review process consumed evidence and changed governance state, design direction, promotion eligibility, canary status, or training readiness.
```

Typical sources:

```text
yogg_signal_promotion_review.md
knowledge_governance_layer.md queue decisions
manual review decisions
promotion/canary review records
training-readiness audit decisions
```

Primary consumer:

```text
human reviewer
governance aggregator
future promotion gate
future canary gate
future training data builder
```

Decision it can change:

```text
Whether a candidate is accepted, held, rejected, quarantined, or promoted to a contract.
```

Observable consumption:

```text
review decision document
queue state transition
contract artifact created
promotion gate input
canary gate input
training-readiness inclusion/exclusion
```

Allowed effects:

```text
May advance evidence from review to contract.
May justify future runtime proposal.
May support training-readiness labels.
```

Forbidden interpretation:

```text
A review outcome is not automatically a runtime outcome.
A governance decision does not by itself patch the system.
```

## 5. Report shape recommendation

Future reports should preserve existing fields and add domain-separated entries rather than overloading `outcome_detected`.

Recommended shape:

```text
outcome_domains: [
  {
    domain: physical_file_outcome | knowledge_domain_evidence | line_activity_evidence | line_consumption_evidence | governance_review_outcome,
    state: observed | candidate | needs_verification | needs_resolution | needs_human_review | quarantined_candidate | resolved | ignored,
    evidence_refs: [],
    consumer_refs: [],
    decision_effect: none | review_created | contract_required | dry_state_changed | promotion_gate_changed | canary_state_changed | training_readiness_changed,
    verification_method: string,
    non_actions: []
  }
]
```

Compatibility rule:

```text
Keep `outcome_detected` as physical-file/sandbox outcome until explicitly migrated.
Do not silently broaden it to knowledge or line domains.
```

## 6. Dry-state rules

Default rule:

```text
Only physical_file_outcome may affect existing physical dry-state counters.
```

Future concept-exploration dry-state may exist only if it has a separate name and consumer:

```text
concept_review_dry_state
knowledge_evidence_freshness
line_consumption_freshness
governance_review_freshness
```

Forbidden rule:

```text
Do not let `kb_changed=True` or `lines_created>0` directly reset existing dry-state logic.
```

## 7. Promotion and canary rules

A signal may enter promotion only after:

```text
concrete evidence refs
+ read-only verification method
+ named outcome domain
+ explicit consumer
+ review decision
+ risk boundary check
```

A signal may enter canary only after:

```text
promotion decision
+ rollback boundary
+ pre/post observation plan
+ failure behavior
```

A signal may enter training only after:

```text
state/action/outcome fields are canonicalized
+ weak proxy labels are marked as weak
+ pollution flags are known
+ reviewer decision is attached
```

## 8. Mapping from current review

Current accepted mappings:

```text
knowledge_outcome_without_physical_outcome -> governance_review_outcome requiring outcome-domain contract
kb_delta_node_only_line_gap -> line_activity_evidence requiring line_delta/graph_delta contract
activity_signal_promotion_candidates -> evidence_signal through ActivitySignalPromotionGate
reasoning_line_activity_visible -> line_activity_evidence
reasoning_line_node_selected_into_active_context -> weak line_consumption_evidence, needs_verification
reasoning_lines_unconsumed_or_unproven -> missing consumption evidence, needs_verification
privileged_promotion_review_required -> needs_human_review risk boundary
raw_progress_class_activity_only -> ignored
no_observed_outcome_domain -> ignored
```

## 9. Open questions

```text
Should knowledge_domain_evidence have its own freshness counter?
Should line_delta and graph_delta be separate domains?
What is the minimum trace evidence for behavioral line consumption?
Which governance decisions are training-ready labels?
Where should outcome_domains live: round report, governance aggregator, or both?
```

## 10. Next implementation boundary

Before any runtime change, create a read-only compatibility audit that answers:

```text
How many existing reports can be mapped into this contract?
Which fields are missing?
Which consumer would use each mapped domain?
What breaks if `outcome_detected` remains physical-only?
```

Until then, this contract remains design-level.

## 11. Read-only compatibility audit

Implemented consumer:

```text
genesis/v6/audit_outcome_domain_compatibility.py
tests/test_v6_outcome_domain_compatibility.py
```

Consumer purpose:

```text
Map existing round reports into this contract without changing runtime behavior.
```

It answers:

```text
How many rounds are mappable per outcome domain?
How many rounds observe each domain?
Which requirements are missing?
Which non-physical domains are hidden when `outcome_detected` remains physical-only?
Which consumer refs and decision effects would use each domain?
```

Non-actions:

```text
No NodeVault writes.
No dry-state changes.
No C-Phase changes.
No broadening of `outcome_detected`.
No training.
```

### Latest remote read-only result

Source:

```text
/home/yoga/Genesis/runtime/auto_reports
max_rounds: 500
```

Decision:

```text
PROCEED_TO_READ_ONLY_DOMAIN_CANONICALIZER_DESIGN
```

Domain compatibility:

```text
physical_file_outcome: mappable=500 observed=2
knowledge_domain_evidence: mappable=500 observed=414
line_activity_evidence: mappable=500 observed=376
line_consumption_evidence: mappable=331 observed=0
governance_review_outcome: mappable=0 observed=0
```

Physical-only shadow gap:

```text
physical_absent_rounds: 498
physical_only_shadow_gap_rounds: 414
shadow_gap_ratio_among_physical_absent_rounds: 0.8313
```

Interpretation:

```text
If `outcome_detected` remains the only outcome lens, it hides non-physical evidence in 83.13% of physical-absent rounds in this sample.
```

Missing compatibility surfaces:

```text
line_consumption_evidence missing:
- phase_trace.current_state_preview.active_nodes: 134
- record_line_success: 125

governance_review_outcome missing:
- governance_review_or_review_decision_or_outcome_domains: 500
```

Boundary:

```text
This validates the need for a read-only domain canonicalizer.
It does not justify changing `outcome_detected`, dry-state, C-Phase, or training behavior yet.
```

## 12. Read-only domain canonicalizer

Implemented consumer:

```text
genesis/v6/canonicalize_outcome_domains.py
tests/test_v6_outcome_domain_canonicalizer.py
```

Consumer purpose:

```text
Convert each round/domain pair into one stable canonical row.
```

Canonical grain:

```text
one row = one round × one outcome domain
```

Each row preserves:

```text
source_path
session_id
round
status
progress_class
domain
domain_state
governance_state_hint
mappable
observed
legacy_outcome_detected
physical_outcome_observed
physical_only_shadowed
consumption_tier
evidence_refs
missing_requirements
consumer_refs
decision_effects
allowed_decision_effects
non_actions
```

Remote read-only validation:

```text
/home/yoga/Genesis/runtime/auto_reports
max_rounds: 500
```

Output:

```text
decision: PROCEED_TO_READ_ONLY_DOMAIN_ROW_CONSUMER_DESIGN
rounds_loaded: 500
total_rows: 2500
```

Observed canonical rows:

```text
knowledge_domain_evidence: 414
line_activity_evidence: 376
physical_file_outcome: 2
```

Physical-only shadowed rows:

```text
knowledge_domain_evidence: 412
line_activity_evidence: 374
```

Governance state hints:

```text
observed: 1041
needs_verification: 790
ignored: 669
```

Boundary:

```text
Canonical rows are review/training-readiness inputs only.
They are not runtime outcomes.
They must not be written to NodeVault by this script.
They must not change dry-state or `outcome_detected`.
```

## 13. Read-only canonical row consumer

Implemented consumer:

```text
genesis/v6/consume_outcome_domain_rows.py
tests/test_v6_outcome_domain_row_consumer.py
```

Consumer purpose:

```text
Consume canonical rows into bounded governance queues without promoting them to runtime outcome.
```

Output queues:

```text
review_queue
verification_queue
training_readiness_candidates
human_review_required
rejected_rows
```

Remote read-only validation:

```text
/home/yoga/Genesis/runtime/auto_reports
max_rounds: 500
total canonical rows: 2500
```

Queue counts:

```text
review_queue: 417
verification_queue: 377
training_readiness_candidates: 0
human_review_required: 0
rejected_rows: 1706
```

Decision distribution:

```text
reject_unobserved: 1038
reject_unmappable: 668
review_knowledge_evidence: 415
verify_line_activity: 377
review_physical_artifact: 2
```

Physical-only shadowed rows:

```text
knowledge_domain_evidence: 413
line_activity_evidence: 375
```

Ratios:

```text
training_candidate_ratio: 0.0
review_or_verification_ratio: 0.3176
```

Interpretation:

```text
Canonical rows are now consumable as governance inputs.
They do not yet produce training candidates because no governance_review_outcome rows exist in the source reports.
```

Boundary:

```text
The consumer may route rows to review or verification.
It must not write queues to NodeVault.
It must not promote review rows without human decision.
It must not treat training candidates as training data.
```

## 14. Read-only governance aggregator

Implemented consumer:

```text
genesis/v6/aggregate_outcome_governance.py
tests/test_v6_outcome_governance_aggregator.py
```

Consumer purpose:

```text
Aggregate canonical row consumer queues into a small number of manual governance items.
```

Input:

```text
/home/yoga/Genesis/runtime/auto_reports
max_rounds: 500
canonical rows: 2500
```

Input row queues:

```text
review_queue: 416
verification_queue: 377
training_readiness_candidates: 0
human_review_required: 0
rejected_rows: 1707
```

Aggregate governance queues:

```text
candidate: 1
needs_verification: 1
needs_resolution: 1
ignored: 6
```

Row counts by aggregate state:

```text
ignored: 1707
needs_resolution: 414
needs_verification: 377
candidate: 2
```

Priority distribution:

```text
P0: 1
P1: 2
P3: 6
```

P0 item:

```text
review_knowledge_evidence:knowledge_domain_evidence
row_count: 414
physical_only_shadowed_count: 412
governance_state: needs_resolution
promotion_target: GovernanceReviewOutcomeDraft
consumer_decision: decide_whether_to_create_governance_review_outcome
```

P1 items:

```text
verify_line_activity:line_activity_evidence
row_count: 377
physical_only_shadowed_count: 375
governance_state: needs_verification
promotion_target: LineActivityVerification

review_physical_artifact:physical_file_outcome
row_count: 2
governance_state: candidate
promotion_target: PhysicalArtifactReview
```

Interpretation:

```text
The evidence surface is now small enough for human governance review.
The next real decision is whether the P0 knowledge-domain evidence aggregate should create a governance_review_outcome artifact.
```

Boundary:

```text
The aggregator is report-only.
It must not write aggregation results to NodeVault.
It must not create governance_review_outcome without human decision.
It must not train from aggregates.
It must not change runtime from aggregates.
```

## 15. P0 GovernanceReviewOutcomeDraft

Review artifact:

```text
docs/yogg_governance_review_outcome_draft.md
```

Purpose:

```text
Turn the P0 aggregate into an explicit human governance decision without changing runtime behavior.
```

Final decision:

```text
accept_as_governance_review_outcome
```

Accepted claim:

```text
Yogg's recent output contains substantial knowledge-domain evidence that is hidden by a physical-only interpretation of outcome.
```

Boundary:

```text
The accepted governance outcome changes design interpretation only.
It is not promotion/canary approval.
It is not a training label.
It does not change runtime or dry-state behavior.
It does not change outcome_detected.
```
