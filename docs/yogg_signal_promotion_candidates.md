# Yogg Signal Promotion Candidates

## 0. Purpose

This document is a review queue for Yogg outputs created from 2026-05-23 onward.

It is not a node-count audit, and it is not a patch plan.

Final value audit summary:

```text
docs/yogg_value_audit_summary.md
```

First manual consumption review:

```text
docs/yogg_signal_promotion_review.md
```

Reasoning proof review:

```text
docs/yogg_reasoning_proof_review.md
docs/yogg_reasoning_proof_review_cases.md
```

The purpose is to identify which Yogg-produced `P_*` signals can be promoted from `ACTIVITY` into one of the following reviewable artifacts:

```text
EvidenceLine
PatchPoint
GovernanceSignal
RiskBoundary
```

The working question is:

```text
Which Yogg outputs can enter an activity → evidence → review → promotion → canary → outcome chain?
```

Not:

```text
Which Yogg outputs are deep, numerous, or rhetorically compelling?
```

## 1. Source and epistemic status

### Source

Live Yogg environment:

```text
yoga-tailscale
/home/yoga/Genesis/runtime/auto_reports
/home/yoga/.genesis/workshop_v4.sqlite
```

Local workspace documents used for conceptual alignment:

```text
docs/yogg_21_23_deep_dive.md
docs/pls_self_evolution_loop.md
docs/knowledge_governance_layer.md
docs/genesis_self_model_leverage_audit.md
```

### Epistemic status

This document is based on read-only inspection.

No runtime logic was changed.
No NodeVault nodes were modified.
No Yogg service was restarted.

The candidate list should be treated as a promotion queue, not as accepted truth.

## 2. Promotion criteria

A Yogg signal is promotion-worthy only if it has at least one stable path into review or action.

Before applying the promotion criteria, review the signal's reasoning chain:

```text
claim → definitions → evidence bindings → inference steps → falsifiers → scope boundary → artifact class
```

A rhetorically strong conclusion should not be promoted unless its proof chain survives this review.

| Criterion | Question |
|---|---|
| Evidence strength | Does the node cite concrete code, config, DB state, report schema, or command output? |
| Verification path | Can the claim be reproduced with read-only checks? |
| Action landing | Can the claim become a PatchPoint, EvidenceLine, GovernanceSignal, or ReviewLine? |
| Outcome semantics | Does the claim clarify what counts as actual outcome rather than activity? |
| Risk boundary | Does the claim touch C-Phase, Arena, SelfEvolution, NodeVault, permissions, or service control? |

## 3. Current core finding

The highest-value Yogg signals do not merely say that Genesis has bugs.

They point to a deeper surface:

```text
Genesis produces many signals, but many signals lack a stable elevation path into consumption, evidence, governance, promotion, canary, or training.
```

This makes the important distinction:

```text
ACTIVITY = something was produced, written, classified, summarized, or named.
OUTCOME = something changed a future decision, behavior, evidence state, promotion state, or training-ready trajectory.
```

Therefore, a Yogg node is not valuable just because it exists.

It becomes valuable when it can enter a promotion chain.

## 4. Candidate groups

## 4.1 OUTCOME/ACTIVITY signal immunity chain

### Nodes

```text
P_OUTCOME_ACTIVITY_SELECTIVE_IMMUNITY
P_OUTCOME_ACTIVITY_SIGNAL_DICHOTOMY
P_PROGRESS_CLASS_EXPLICIT_IMMUNITY_REJECTION
P_METACOGNITIVE_SIGNAL_GP_CONTEXT_PARASITISM
```

### Category

```text
EvidenceLine
GovernanceSignal
```

### Claim

C-Phase does not simply forget `progress_class`.

It explicitly treats `progress_class` as an `ACTIVITY` signal and excludes it from C-Phase outcome consumption because activity signals can be inflated by probe writing.

The more precise follow-up claim is selective immunity:

```text
progress_class="error" is consumed as an outcome-like exception signal.
progress_class="strong" / "soft" / "evidence" / "idle" remains activity-like and is excluded.
```

### Verified evidence

Remote code inspection confirmed:

```text
genesis/v4/c_phase.py:438-444
```

`_build_cross_round_observations()` states that it only uses outcome signals and avoids activity signals like `progress_class` because they can mislead C.

```text
genesis/v4/chapter_state.py:195-208
```

`add_progress_class()` writes `progress_classification` into the chapter state as a diagnostics snapshot.

```text
genesis/auto_mode.py:1603-1604
```

`error_count` is computed from `progress_class == "error"`, proving that the `error` branch is still consumed.

### Missing review

The unresolved question is not whether `progress_class` exists.

The unresolved question is:

```text
Which activity signals are allowed to become EvidenceLine candidates, and under what constraints?
```

### Promotion target

Define an `ActivitySignalPromotionGate` concept before changing C-Phase logic.

Candidate rule shape:

```text
activity signal
+ external/read-only evidence
+ non-self-reported verification path
+ outcome domain
+ review decision
= EvidenceLine candidate
```

### Outcome criterion

A promoted activity signal should not directly increase confidence or count as success.

It should first become a reviewable evidence item with:

```text
source
verification method
outcome domain
risk level
promotion decision
```

### Decision

Promote to governance design queue.

Do not patch C-Phase to consume all `progress_class` values directly.

## 4.2 Sandbox diff / knowledge outcome mismatch chain

### Nodes

```text
P_ONTOLOGICAL_PROXY_COLLAPSE
P_SANDBOX_DIFF_TRIPLE_SHORT_CIRCUIT
P_KB_DELTA_EDGE_BLINDNESS
```

### Category

```text
EvidenceLine
GovernanceSignal
PatchPoint candidate
```

### Claim

Genesis currently mixes or separates outcome signals across incompatible ontological layers:

```text
sandbox/git diff = physical file outcome
kb_changed = knowledge-base outcome
edge delta = PLS line outcome
semantic_progress = semantic outcome, currently weak or unknown
```

For concept exploration, knowledge and edge changes may be meaningful outputs, but `outcome_detected` is mainly based on sandbox tracked file diff.

This can make concept exploration look dry even when the knowledge graph changed.

### Verified evidence

Remote code inspection confirmed:

```text
genesis/auto_mode.py:2759-2768
```

`outcome_changed_since_snapshot()` compares the current sandbox diff status hash with the pre-round snapshot.

It returns `False` when `applied_this_session` is true.

```text
scripts/doctor.sh:523-530
```

`diff-status` computes `tracked_hash` from `git diff HEAD`.

```text
genesis/auto_mode.py:4113-4119
```

`consecutive_dry` resets only when `progress_profile.get("outcome_detected")` is true.

Therefore, `kb_changed=True` does not by itself reset dry state.

### Missing review

The key unresolved question is:

```text
Should concept-exploration outcomes be represented as a separate outcome domain instead of being judged by sandbox file diff?
```

### Promotion target

Define multi-domain outcome semantics:

```text
physical_outcome: sandbox/git diff changed
knowledge_outcome: node/content/freshness/provenance changed
line_outcome: edge or PLS Line changed
behavioral_outcome: future route/policy changed
training_outcome: S-A-O distillability improved
```

### Outcome criterion

A round should be able to declare which outcome domain it affected, instead of collapsing all progress into `outcome_detected` or `kb_changed`.

Minimum useful schema:

```text
outcome_domain
outcome_signal_kind
outcome_strength
evidence_source
promotion_status
```

### Decision

Promote to governance design queue.

`P_SANDBOX_DIFF_TRIPLE_SHORT_CIRCUIT` may later become a PatchPoint, but only after the outcome-domain semantics are agreed.

## 4.3 SelfEvolution privileged cold path chain

### Nodes

```text
P_PRIVILEGED_COLD_PATH_SELF_EVOLUTION_RESTART
P_PERMISSION_TRUST_CHAIN_DANGLING_END
P_CONSTRAINT_SURFACE_PRIVATE_BYPASS_ARCHETYPE
P_CRITICAL_SELF_EVOLUTION_FILES_SCOPE_GATE_VERIFIED
P_SELFEVOLUTION_DIAGNOSIS_TREATMENT_DECOUPLING
```

### Category

```text
EvidenceLine
PatchPoint candidate
RiskBoundary
```

### Claim

SelfEvolution has a high-consequence restart path that connects sandbox modification, testing, git commit, systemd restart, crash guard, and canary observation.

The risk is not just that restart exists.

The risk is that the runtime permission model may bypass the apparent constraint surface.

### Verified evidence

Remote code inspection confirmed:

```text
genesis/auto_mode.py:3222-3228
```

SelfEvolution restart executes:

```text
sudo systemctl restart yogg-auto.service
```

Remote service file inspection confirmed:

```text
/etc/systemd/system/yogg-auto.service
```

The service runs with:

```text
User=yoga
WorkingDirectory=/home/yoga/Genesis
MemoryMax=3400M
MemoryHigh=2800M
OOMPolicy=stop
Restart=always
```

Remote sudo inspection confirmed:

```text
User yoga may run:
(ALL : ALL) ALL
(ALL) NOPASSWD: ALL
```

### Missing review

The unresolved questions are:

```text
Should Yogg be allowed NOPASSWD: ALL?
Should automatic SelfEvolution restart be allowed without a privileged action review record?
Should restart permission be restricted to one command?
Should promotion require a human review line when privileged paths are involved?
```

### Promotion target

Create a `PrivilegedPromotionReview` gate before enabling or expanding SelfEvolution.

A review should include:

```text
command
service target
runner user
sudo scope
rollback mechanism
canary behavior
audit record
manual override path
```

### Outcome criterion

A privileged promotion should not be considered successful merely because the service restarts.

Minimum outcome criteria:

```text
restart completed
canary rounds completed
no crash loop
rollback marker cleared only after canary
privileged action recorded
permission scope verified
```

### Decision

Promote to risk review queue.

Do not patch automatically.

## 4.4 KB delta / Line blindness chain

### Nodes

```text
P_KB_DELTA_EDGE_BLINDNESS
```

### Category

```text
EvidenceLine candidate
GovernanceSignal candidate
```

### Claim

Yogg claims that `kb_delta` and downstream summaries may underrepresent edge changes, causing PLS `Line` creation to be weaker than node creation in outcome accounting.

This matters because Yogg frequently reports:

```text
三条线全部写入成功
```

If line creation is not represented as an outcome-domain signal, PLS Line work remains activity-only.

### Verified evidence

Verified, with a narrower conclusion than the original node title implies.

Remote report/schema inspection showed:

```text
639/639 inspected round reports had kb_delta keys:
new_nodes
updated_nodes
error
```

There is no `edges`, `lines`, `reasoning_lines`, or `node_edges` field inside `kb_delta`.

Remote report statistics from the same window showed:

```text
telemetry_lines_created_rounds: 453
topology_lines_successful_rounds: 341
record_line_success_events: 1743
record_line_existing_events: 62
record_line_error_events: 139
```

Remote NodeVault inspection showed:

```text
reasoning_lines created >= 2026-05-22 16:00:00: 1743
node_edges created >= 2026-05-22 16:00:00: 1002
```

Code inspection confirmed that `record_line` writes to `reasoning_lines`, not `node_edges`:

```text
genesis/tools/node_tools.py:224-304
genesis/v4/manager.py:2235-2269
```

Code inspection also confirmed that `kb_delta` only queries `knowledge_nodes`:

```text
genesis/auto_mode.py:541-566
```

Line information is visible elsewhere:

```text
genesis/auto_mode.py:848-918
```

`_build_pls_telemetry()` captures:

```text
lines_created
same_round_lines
cross_round_lines
line_existing
line_errors
```

```text
genesis/auto_mode.py:921-1010
```

`_build_round_topology()` captures successful lines and anchored-point topology.

V6 audit code also recognizes PLS line activity:

```text
genesis/v6/audit_sao_distillability.py:149-223
```

`classify_route_family()` can classify `pls_point_line_anchor`, and `weak_outcome_labels()` can add `pls:line_created`.

Therefore, the precise finding is:

```text
PLS Line is not completely invisible.
It is represented in event/telemetry/topology/audit layers.
But it is absent from kb_delta and has no first-class outcome-domain status.
```

### Missing review

Need decide:

```text
Should reasoning_lines be part of knowledge_outcome?
Should node_edges and reasoning_lines be separate outcome domains?
Should kb_delta remain node-only and be renamed or complemented?
Should line creation reset any dry or freshness state for concept-exploration sessions?
Should line outcome require cross-round basis, non-existing duplicate status, or future retrieval impact?
```

### Promotion target

Promote to:

```text
PLS Line Outcome Schema review
```

### Outcome criterion

A PLS Line should have first-class outcome representation when it affects graph structure or future retrieval.

Candidate fields:

```text
lines_created
same_round_lines
cross_round_lines
line_existing
line_errors
reasoning_lines_delta
node_edges_delta
line_outcome_domain
line_promotion_status
```

### Decision

Promote as a verified EvidenceLine and GovernanceSignal.

Do not patch immediately.

The next design question is whether `kb_delta` should be renamed to node-only delta or complemented by a separate `line_delta` / `graph_delta` outcome domain.

## 4.5 Constraint surface private bypass chain

### Nodes

```text
P_CONSTRAINT_SURFACE_PRIVATE_BYPASS_ARCHETYPE
```

### Category

```text
GovernanceSignal
RiskBoundary
```

### Claim

Genesis may present explicit constraints at one layer while private or privileged runtime channels bypass those constraints at another layer.

The SelfEvolution sudo path is one concrete instance.

### Verified evidence

Partially verified through the SelfEvolution permission chain.

The broader archetype should not be treated as a PatchPoint by itself.

### Missing review

Need identify which constraints are:

```text
documented
implemented
enforced at runtime
audited
bypassable through private channels
```

### Promotion target

Use as a ReviewLine anchor for high-risk governance checks.

### Outcome criterion

A constraint should be considered real only if it has:

```text
declared rule
runtime enforcement
observable audit signal
bypass analysis
failure behavior
```

### Decision

Promote as an architectural review lens, not as a direct patch.

## 5. First promotion queue

| Priority | Node group | Promotion type | Decision |
|---|---|---|---|
| P0 | OUTCOME/ACTIVITY signal immunity | GovernanceSignal + EvidenceLine | Implemented in read-only queue |
| P0 | Sandbox diff / knowledge outcome mismatch | GovernanceSignal + EvidenceLine | Implemented as multi-domain outcome audit |
| P1 | SelfEvolution privileged cold path | RiskBoundary + ReviewLine | Implemented as privileged review queue item |
| P1 | KB delta / Line blindness | EvidenceLine + GovernanceSignal | Implemented with line production/consumption split |
| P2 | Constraint surface private bypass | GovernanceSignal | Implemented as constraint surface audit |

## 5.1 Implementation status

Read-only consumer implemented:

```text
genesis/v6/audit_yogg_signal_promotion.py
tests/test_v6_yogg_signal_promotion.py
```

Current behavior:

```text
No NodeVault writes.
No confidence or epistemic_status changes.
No service restart.
No patch apply.
No C-Phase behavior change.
No model training.
```

The script maps all candidate groups above into governance queues.

### Latest remote read-only run

Source:

```text
/home/yoga/Genesis/runtime/auto_reports
/home/yoga/.genesis/workshop_v4.sqlite
/etc/systemd/system/yogg-auto.service
```

Window:

```text
max_rounds: 500
created_since: 2026-05-23 00:00:00
```

Queue output:

```text
observed: 2
candidate: 1
needs_verification: 4
needs_resolution: 3
needs_human_review: 1
quarantined_candidate: 0
resolved: 0
ignored: 2
```

Outcome-domain evidence:

```text
knowledge_outcome: 414
line_activity_evidence: 370
physical_outcome: 2
```

This confirms the sandbox/knowledge mismatch:

```text
Knowledge and line activity dominate the recent output,
while physical sandbox outcome is rare.
```

Line production / consumption evidence:

```text
lines_created: 1452
cross_round_lines: 1452
line_errors: 96
reasoning_lines_total since 2026-05-23: 1470
consumed_as_basis: 0
unconsumed_or_unproven: 1470
active-context weak consumption evidence: needs_verification queue has reasoning_line_node_selected_into_active_context
```

Constraint surface evidence:

```text
service_snapshot_available: true
service_user_declared: true
service_memory_limit_declared: true
service_restart_declared: true
sudo_snapshot_available: false
broad_sudo_detected: false
risk_level: medium
```

Because no sudo snapshot was supplied to the script, the constraint bypass item remains a service-level audit rather than a quarantined broad-sudo finding in this run.

### Current mapped items

```text
activity_signal_promotion_candidates -> candidate
knowledge_outcome_without_physical_outcome -> needs_resolution
kb_delta_node_only_line_gap -> needs_resolution
record_line_rejections_present -> needs_resolution
reasoning_lines_unconsumed_or_unproven -> needs_verification
privileged_promotion_review_required -> needs_human_review
constraint_surface_private_bypass_audit -> needs_verification when service constraints are visible without sudo bypass evidence
reasoning_line_node_selected_into_active_context -> needs_verification as weak consumption evidence
raw_progress_class_activity_only -> ignored
no_observed_outcome_domain -> ignored
```

## 6. Immediate next review questions

Before writing runtime code, answer these:

```text
1. What are the valid outcome domains for Yogg concept exploration?
2. Which activity signals can be promoted to EvidenceLine, and by what gate?
3. Does PLS Line creation have first-class outcome representation?
4. What permission review is required before SelfEvolution promotion or restart?
5. How should round reports encode promotion status without turning activity into fake outcome?
```

## 7. Design guardrails

These guardrails exist to prevent this review queue from becoming a new form of activity noise.

### 7.1 Do not create a second governance system

Any new review state in this document must map back to the existing governance vocabulary:

```text
observed
candidate
needs_verification
needs_resolution
needs_human_review
quarantined_candidate
resolved
ignored
```

New terms such as `line_review_candidate`, `activity_review_candidate`, or `privileged_promotion_review` are draft labels only.

They are not authoritative lifecycle states until a consumer exists.

### 7.2 Evidence is not outcome

The queue must preserve this distinction:

```text
activity_created != evidence_verified != outcome
```

A stricter outcome definition:

```text
outcome = consumed evidence that changed a decision, behavior, review state, promotion state, canary state, or training readiness.
```

Therefore:

```text
node created
line created
evidence line verified
```

are not sufficient outcomes by themselves.

### 7.3 Every field needs a consumer

Before adding runtime fields, answer:

```text
Who consumes this field?
What decision changes because of it?
Where is the consumption observable?
```

If there is no consumer, the field should stay in this review document rather than enter runtime reports.

### 7.4 Availability is not consumption

Being stored, visible, or queryable is not enough.

For a signal to count as consumed, there must be evidence such as:

```text
used in a review decision
selected into active context
opened as supporting evidence
used as basis for another node or line
changed a governance queue status
changed canary or promotion state
included in a training-ready S-A-O sample
```

### 7.5 Current path and desired path must stay separate

For SelfEvolution, distinguish:

```text
current privileged cold path:
apply → restart → observe / rollback
```

from:

```text
desired privileged promotion path:
review → bounded apply → pre/post canary → promote
```

The review queue should not accidentally legitimize the current path just by documenting it.

## 8. Consumer contract: Yogg Signal Promotion Queue

This is the first intended consumer of the ReviewLine drafts in this document.

It is read-only and report-only.

### 8.1 Consumer name

```text
yogg_signal_promotion_queue
```

### 8.2 Purpose

The consumer answers:

```text
Which observed Yogg signals have enough evidence to enter a review queue?
```

It does not answer:

```text
Which signals should automatically change runtime behavior?
```

### 8.3 Input sources

Allowed input sources:

```text
auto_reports round JSON
NodeVault knowledge_nodes / node_content
NodeVault reasoning_lines
NodeVault node_edges
systemd service file snapshots
read-only command outputs captured by audit
local review documents
```

### 8.4 Accepted signal types

The queue may accept:

```text
activity_signal
evidence_signal
risk_signal
governance_signal
```

It must not accept raw activity as outcome.

### 8.5 Governance state mapping

The queue should emit only the existing governance states:

```text
observed
candidate
needs_verification
needs_resolution
needs_human_review
quarantined_candidate
resolved
ignored
```

Draft labels from this document map into those states.

Example:

```text
activity_review_candidate -> candidate / needs_verification
line_review_candidate -> candidate / needs_verification
privileged_promotion_review -> needs_human_review or quarantined_candidate
line_promoted -> resolved only if actual consumption evidence exists
```

### 8.6 Output shape

The first report should look like:

```text
{
  "dry_run": true,
  "governance_mode": "report_only",
  "consumer": "yogg_signal_promotion_queue",
  "queues": {
    "observed": [],
    "candidate": [],
    "needs_verification": [],
    "needs_resolution": [],
    "needs_human_review": [],
    "quarantined_candidate": [],
    "resolved": [],
    "ignored": []
  }
}
```

### 8.7 Queue item minimum fields

Each item should contain:

```text
signal_id
signal_type
source_refs
claim
evidence_refs
verification_method
governance_state
promotion_target
consumer_decision
non_actions
```

### 8.8 Non-actions

This consumer must not:

```text
modify NodeVault
change confidence
promote epistemic_status
restart services
apply patches
change C-Phase behavior
clear rollback/canary markers
train models
```

### 8.9 Consumption evidence

The consumer itself only produces a queue.

A later signal can claim actual consumption only if there is evidence that an item from the queue was:

```text
reviewed
accepted or rejected
used to change a design decision
used to create a PatchPoint
used to gate a promotion
used to construct a training-ready S-A-O sample
```

### 8.10 First implementation boundary

The first implementation, if any, should be:

```text
read-only script
local output file or stdout report
no database writes
no runtime behavior changes
```

The contract must be reviewed before implementation.

## 9. Activity signal promotion gate review draft

This section is a ReviewLine draft for the OUTCOME/ACTIVITY signal immunity chain.

The verified gap is not:

```text
C-Phase forgot progress_class.
```

The verified gap is:

```text
C-Phase intentionally excludes progress_class-like activity signals from outcome observation,
but the system does not yet define a safe promotion path from activity signal to evidence.
```

### 9.1 Signal classes

Minimum separation:

```text
self_report_signal: text claim made by GP / C / report narrative
activity_signal: tool use, progress_class, node write, line write, telemetry counter
evidence_signal: externally checkable code/config/DB/report fact
outcome_signal: a fact that changed behavior, review status, promotion status, canary state, or training readiness
```

This keeps the system from treating all visible activity as progress.

### 9.2 Promotion states

Activity signals should have an explicit review lifecycle.

These labels must map back to governance queue states before implementation:

```text
activity_observed: signal exists in report/state → observed
activity_rejected: signal is activity-only and has no evidence path → ignored
activity_review_candidate: signal cites concrete evidence and has a verification path → candidate / needs_verification
evidence_line_created: review records the evidence and source → needs_verification
evidence_line_verified: independent/read-only check confirms the claim → candidate
promotion_candidate: evidence has an action or governance target → needs_resolution / needs_human_review
promoted_outcome: later behavior, review, canary, or training state consumes it → resolved
```

The important rule:

```text
activity_observed != outcome_signal
```

### 9.3 Gate inputs

Candidate input fields:

```text
signal_name
signal_source
signal_value
claimed_meaning
evidence_refs
verification_method
outcome_domain
risk_domain
promotion_target
review_decision
```

Examples:

```text
progress_class=strong
lines_created=3
kb_changed=True
c_phase_summary.supplements=2
```

These may become review candidates, but they should not directly become outcomes.

### 9.4 Minimum promotion rule

An activity signal can become an EvidenceLine candidate only when it satisfies:

```text
has concrete evidence reference
+ has read-only verification path
+ is not purely self-reported
+ names an outcome domain
+ names what would change if accepted
```

Examples of acceptable evidence references:

```text
file path + line range
SQLite table/query result
round report path + field path
systemd service file field
command output captured in audit
```

Examples of insufficient references:

```text
node title only
round count only
progress_class only
confidence score only
```

### 9.5 C-Phase implication

Do not make C-Phase consume all activity signals directly.

Safer design:

```text
C-Phase keeps rejecting raw activity as outcome.
Auto/report layer exposes promotion candidates.
Review layer decides whether an activity signal becomes EvidenceLine.
Only promoted EvidenceLine can influence governance/outcome.
```

This preserves the original C-Phase defense against probe-writing inflation while adding a path out of total immunity.

### 9.6 Decision

Promote to governance design queue.

The PatchPoint is not:

```text
use progress_class as outcome
```

The PatchPoint candidate is:

```text
represent activity_signal_promotion explicitly in reports/governance review
```

## 10. Line / graph outcome domain review draft

This section is a ReviewLine draft, not an implementation plan.

The verified gap is not:

```text
PLS Line is invisible.
```

The verified gap is:

```text
PLS Line is visible as activity/telemetry/topology, but not represented as an outcome domain.
```

### 10.1 Naming separation

Do not overload `kb_delta` until its meaning is explicit.

Minimum naming split:

```text
node_delta: changes in knowledge_nodes / node_content
reasoning_line_delta: changes in reasoning_lines
graph_edge_delta: changes in node_edges
```

This avoids a false equivalence between:

```text
node created
reasoning line created
RELATED_TO / CONTRADICTS edge created
```

These are all knowledge-structure changes, but they have different semantics.

### 10.2 Promotion states

Line creation should not automatically count as outcome.

Candidate lifecycle:

```text
line_activity_observed: record_line was attempted
line_evidence_recorded: reasoning_lines row was created
line_existing_observed: duplicate line already existed
line_rejected: endpoint/self/visibility validation rejected the line
line_review_candidate: line is cross-round, non-duplicate, and connects a new claim to a prior basis
line_promoted: later retrieval, review, or decision actually consumed the line
```

This keeps `record_line` from becoming another fake productivity counter.

### 10.3 Minimal report shape

If this becomes a PatchPoint later, prefer adding a separate object rather than mutating `kb_delta` silently:

```text
line_delta: {
  reasoning_lines_created: int,
  same_round_lines_created: int,
  cross_round_lines_created: int,
  reasoning_lines_existing: int,
  reasoning_line_errors: int,
  review_candidate_lines: int
}

graph_delta: {
  node_edges_created: int,
  related_to_created: int,
  contradicts_created: int,
  edge_errors: int
}

outcome_domains: {
  physical: bool,
  node_knowledge: bool,
  reasoning_line: bool,
  graph_edge: bool,
  behavioral: bool,
  training: bool
}
```

### 10.4 Outcome criterion

The minimum legitimate `reasoning_line` outcome is not merely:

```text
lines_created > 0
```

A stronger criterion is:

```text
cross_round_lines_created > 0
+ line is not duplicate
+ endpoints are active and non-virtual
+ line connects a new claim to an existing basis
+ later review/retrieval actually consumed the line
```

Only after later consumption should it become:

```text
line_promoted
```

### 10.5 Design decision still open

The next design choice is:

```text
Keep kb_delta node-only and add line_delta / graph_delta
```

or:

```text
Redefine kb_delta as a full knowledge-structure delta
```

The safer default is the first option, because it preserves old semantics and avoids accidentally turning any graph mutation into outcome.

## 11. Privileged promotion review draft

This section is a ReviewLine draft for the SelfEvolution privileged cold path chain.

The verified gap is not:

```text
Yogg can restart itself.
```

The verified gap is:

```text
Yogg has a privileged restart path, but promotion/canary semantics are not yet tied to a privilege review record.
```

### 11.1 Risk boundary

The current risky surface is the chain:

```text
sandbox modification
→ test / apply gate
→ git commit or persistent code change
→ sudo systemctl restart yogg-auto.service
→ service restarts under systemd
→ canary observation decides whether rollback is needed
```

The permission concern is amplified when the runtime user can execute broad sudo commands.

The desired promotion path is stricter:

```text
review
→ bounded apply
→ pre-restart smoke / canary checks
→ bounded restart
→ post-restart service canary
→ promote or rollback
```

### 11.2 Required review fields

Any privileged promotion should have a review object before execution:

```text
privileged_promotion_review: {
  action: string,
  command: string,
  service_target: string,
  runner_user: string,
  sudo_scope: string,
  changed_files: list,
  tests_required: list,
  rollback_plan: string,
  canary_rounds_required: int,
  approval_mode: string,
  risk_level: string,
  review_decision: string
}
```

This review object should be produced before restart, not inferred after a successful restart.

### 11.3 Minimum allowed decisions

Candidate decisions:

```text
reject: no privileged action allowed
manual_review_required: human must approve before execution
allow_once: one bounded execution with audit record
allow_policy: repeated execution allowed by a named policy
rollback_required: promotion failed canary and must revert
```

The default should be:

```text
manual_review_required
```

for any action involving `sudo`, systemd restart, persistent code mutation, or rollback clearing.

### 11.4 Permission scope criterion

A safe permission scope is not:

```text
NOPASSWD: ALL
```

A safer target is:

```text
only the exact service command needed
+ exact service target
+ no shell expansion
+ no arbitrary command execution
+ audit record emitted
```

If the runtime environment still has broad sudo, the review should explicitly record:

```text
sudo_scope=broad
risk_level=high
```

and should not silently treat service-level limits such as `User=`, `MemoryMax=`, or `Restart=always` as sufficient safety boundaries.

### 11.5 Canary outcome criterion

Restart success is not enough.

Minimum canary outcome:

```text
service restarted
+ no immediate crash loop
+ expected process identity observed
+ canary rounds completed
+ no rollback trigger fired
+ rollback marker cleared only after canary
+ privileged action audit record exists
```

Only then can the promotion move from:

```text
privileged_action_executed
```

to:

```text
privileged_promotion_survived_canary
```

### 11.6 Design decision still open

The next design choice is:

```text
Move privileged restart behind explicit human approval
```

or:

```text
Allow bounded automated restart only under a named policy and narrow sudo scope
```

The safer default is human review until permission scope and canary semantics are both explicit.

## 12. Non-goals

Do not use this queue to justify immediate broad refactoring.

Do not directly convert `kb_changed=True` into success.

Do not make C-Phase consume all `progress_class` values.

Do not treat Yogg's self-diagnosis as final truth without review.

Do not modify SelfEvolution permission behavior without explicit risk review.

## 13. Working interpretation

The practical meaning of Yogg's recent output is:

```text
Yogg is not proving that its own activity is already valuable.
It is exposing the missing elevation chain that would let valuable activity become outcome.
```

The useful next step is therefore not more activity metrics.

It is a promotion queue.
