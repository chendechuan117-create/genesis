# V6 Outcome Domains Runtime Proposal

Phase B implementation plan:

```text
docs/v6_outcome_domains_phase_b_plan.md
```

## 0. Purpose

This is a runtime/report-schema proposal, not a runtime patch.

It proposes an additive `outcome_domains` field for future auto round reports so Genesis can preserve separate outcome semantics without broadening `outcome_detected`.

Accepted governance outcome that motivates this proposal:

```text
Genesis should preserve separate outcome domains because Yogg produced substantial knowledge-domain evidence that would be misclassified or hidden by a physical-only outcome lens.
```

## 1. Non-goals

Do not:

```text
change outcome_detected
reset dry-state from kb_changed
reset dry-state from lines_created
change C-Phase behavior
modify NodeVault
restart services
change promotion/canary behavior
train models from this proposal
patch runtime before review
```

This proposal only defines what a future additive report field could look like.

## 2. Current problem

Current round reports expose domain evidence across separate fields:

```text
physical_file_outcome -> outcome_detected
knowledge_domain_evidence -> kb_changed, kb_delta, pls_telemetry.points_created
line_activity_evidence -> pls_telemetry.lines_created, pls_telemetry.cross_round_lines, events.record_line
line_consumption_evidence -> phase_trace.current_state_preview.active_nodes, reasoning_lines self-join, later review citation
governance_review_outcome -> currently absent from raw reports
```

This forces downstream consumers to infer outcome domains repeatedly.

The main risk is semantic collapse:

```text
kb_changed=True or lines_created>0 gets treated as outcome_detected=True
```

This proposal prevents that collapse.

## 3. Compatibility rule

`outcome_detected` remains physical-only.

Meaning:

```text
outcome_detected=True means physical/sandbox file outcome was detected.
outcome_detected=False does not mean no knowledge-domain evidence exists.
```

No existing consumer should reinterpret `outcome_detected` as a multi-domain success flag.

## 4. Proposed additive field

Future reports may include:

```json
{
  "outcome_domains": [
    {
      "domain": "physical_file_outcome",
      "state": "observed",
      "mappable": true,
      "observed": true,
      "evidence_refs": ["outcome_detected"],
      "consumer_refs": ["physical dry-state", "patch/canary review"],
      "decision_effects": ["physical_review_candidate"],
      "consumption_tier": "none",
      "non_actions": []
    }
  ]
}
```

This field is additive.

Legacy fields remain the source of truth during shadow/report-only phases.

## 5. Domain vocabulary

Allowed domains:

```text
physical_file_outcome
knowledge_domain_evidence
line_activity_evidence
line_consumption_evidence
governance_review_outcome
```

No new domain should be added without updating:

```text
docs/v6_outcome_domain_contract.md
genesis/v6/audit_outcome_domain_compatibility.py
genesis/v6/canonicalize_outcome_domains.py
genesis/v6/consume_outcome_domain_rows.py
genesis/v6/aggregate_outcome_governance.py
```

## 6. Domain state vocabulary

Allowed per-domain states:

```text
missing_fields
mappable_absent
observed
needs_verification
needs_resolution
accepted_governance_outcome
ignored
```

State meanings:

```text
missing_fields: required source fields are absent.
mappable_absent: source fields exist but domain evidence is not observed.
observed: domain evidence is present.
needs_verification: evidence exists but consumption/outcome claim is not strong enough.
needs_resolution: evidence changes governance interpretation and needs a review decision.
accepted_governance_outcome: human review accepted a governance outcome.
ignored: evidence is absent or unsuitable for promotion.
```

## 7. Domain-specific mapping

## 7.1 physical_file_outcome

Source fields:

```text
outcome_detected
sandbox diff / tracked file diff if available
```

Observed when:

```text
outcome_detected is true
```

Allowed consumer effects:

```text
physical_review_candidate
patch_review_candidate
canary_review_candidate
```

Dry-state rule:

```text
Only this domain may affect existing physical dry-state counters.
```

## 7.2 knowledge_domain_evidence

Source fields:

```text
kb_changed
kb_delta.new_nodes
kb_delta.updated_nodes
pls_telemetry.points_created
```

Observed when any of these holds:

```text
kb_changed is true
new_nodes count > 0
updated_nodes count > 0
points_created > 0
```

Allowed consumer effects:

```text
review_created
contract_required
governance_review_outcome_candidate
```

Forbidden effects:

```text
physical dry-state reset
physical task success
training label without governance review
```

## 7.3 line_activity_evidence

Source fields:

```text
pls_telemetry.lines_created
pls_telemetry.cross_round_lines
pls_telemetry.line_errors
events.record_line
```

Observed when:

```text
line counters or record_line events exist
```

Allowed consumer effects:

```text
line_schema_review
line_rejection_review
line_consumption_followup
```

Forbidden effects:

```text
line outcome claim
physical dry-state reset
training label without consumption evidence
```

## 7.4 line_consumption_evidence

Source fields:

```text
record_line successful new_point_id
phase_trace.current_state_preview.active_nodes
reasoning_lines later.basis_point_id = earlier.new_point_id
review decision citation
behavioral trace effect
training sample inclusion
```

Evidence tiers:

```text
weak_active_context
structural_later_basis
governance_review_citation
behavioral_decision_effect
training_inclusion
```

Allowed consumer effects:

```text
verify_consumption_before_outcome
line_consumption_review
training_readiness_review
```

Forbidden effects:

```text
Treat weak_active_context as resolved outcome.
Treat storage in reasoning_lines as consumption.
Treat search availability as consumption.
```

## 7.5 governance_review_outcome

Source fields:

```text
review artifact path
human final decision
accepted claim
verified sample refs
non-actions
```

Observed when:

```text
A human-reviewed governance outcome is accepted and documented.
```

Allowed consumer effects:

```text
governance_state_changed
training_readiness_candidate
future proposal justification
```

Forbidden effects:

```text
automatic runtime patch
automatic promotion/canary approval
automatic training inclusion
```

## 8. Proposed report example

Example future report fragment:

```json
{
  "outcome_detected": false,
  "kb_changed": true,
  "outcome_domains": [
    {
      "domain": "physical_file_outcome",
      "state": "mappable_absent",
      "mappable": true,
      "observed": false,
      "evidence_refs": ["outcome_detected"],
      "consumer_refs": ["physical dry-state", "patch/canary review"],
      "decision_effects": ["none"],
      "consumption_tier": "none",
      "non_actions": ["do_not_treat_absence_as_no_knowledge_evidence"]
    },
    {
      "domain": "knowledge_domain_evidence",
      "state": "observed",
      "mappable": true,
      "observed": true,
      "evidence_refs": ["kb_changed", "kb_delta.new_nodes", "pls_telemetry.points_created"],
      "consumer_refs": ["knowledge governance queue", "manual review"],
      "decision_effects": ["review_created", "contract_required"],
      "consumption_tier": "none",
      "non_actions": ["do_not_reset_physical_dry_state", "do_not_treat_as_task_success"]
    }
  ]
}
```

## 9. Migration plan

## 9.1 Phase A: read-only shadow generation

Generate `outcome_domains` outside runtime from existing reports.

Existing scripts already cover this role:

```text
genesis/v6/audit_outcome_domain_compatibility.py
genesis/v6/canonicalize_outcome_domains.py
```

No runtime changes.

Success criteria:

```text
field shape remains stable
no old field semantics change
consumer output matches current canonicalizer
```

## 9.2 Phase B: report-only runtime emission

Add `outcome_domains` to future round reports, but only as a report field.

No behavior changes.

Forbidden during Phase B:

```text
no dry-state changes
no promotion/canary changes
no training changes
no C-Phase changes
```

Success criteria:

```text
new reports include outcome_domains
legacy consumers still pass
shadow canonicalizer agrees with emitted field
```

## 9.3 Phase C: reviewed consumer adoption

Only after Phase B validation, allow consumers to read `outcome_domains`.

Consumer adoption must be explicit:

```text
governance aggregator may read outcome_domains
training-readiness bridge may read accepted governance_review_outcome
physical dry-state still reads physical_file_outcome only
```

## 10. Dry-state rules

Existing dry-state:

```text
physical dry-state only
```

Allowed reset source:

```text
physical_file_outcome observed
```

Forbidden reset sources:

```text
knowledge_domain_evidence observed
line_activity_evidence observed
line_consumption_evidence weak_active_context
governance_review_outcome accepted
```

Future separate freshness counters may be proposed later:

```text
knowledge_evidence_freshness
line_consumption_freshness
governance_review_freshness
```

But they must not reuse existing physical dry-state semantics.

## 11. Training-readiness rules

`outcome_domains` is not training data by itself.

Training candidates require:

```text
accepted governance_review_outcome
+ stable S-A-O fields
+ action/route canonicalization
+ pollution flags
+ reviewer decision attached
```

Weak evidence must be labeled weak.

Forbidden:

```text
training directly from knowledge_domain_evidence
training directly from line_activity_evidence
training from weak_active_context
```

## 12. Rejection conditions

Pause or reject this proposal if:

```text
outcome_domains gets used as a success score
outcome_detected semantics are broadened
kb_changed starts resetting physical dry-state
line activity is treated as line outcome
training pipeline consumes weak evidence directly
legacy reports break
consumer code cannot distinguish physical outcome from governance outcome
```

## 13. Tests required before any patch

Before changing runtime, add tests that prove:

```text
outcome_detected remains physical-only
knowledge_domain_evidence does not reset dry-state
line_activity_evidence does not become outcome success
outcome_domains is additive and absent-safe
legacy reports remain readable
shadow canonicalizer agrees with emitted outcome_domains
```

## 14. Implementation boundary

This document does not authorize implementation.

Implementation requires a separate reviewed task:

```text
Phase B report-only emission of outcome_domains
```

Any implementation task must start by reading:

```text
docs/yogg_value_audit_summary.md
docs/v6_outcome_domain_contract.md
```

and must preserve this invariant:

```text
activity/evidence/consumption/governance outcome are separate layers.
```
