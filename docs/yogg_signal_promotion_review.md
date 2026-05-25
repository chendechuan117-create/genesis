# Yogg Signal Promotion Review

## 0. Purpose

This document consumes the first `yogg_signal_promotion_queue` output.

It is not a runtime patch plan.

It records review decisions for queue items so the chain can advance from:

```text
activity → evidence → review
```

without pretending that review has already produced promotion, canary, or outcome.

## 1. Review source

Input queue source:

```text
genesis/v6/audit_yogg_signal_promotion.py
```

Latest read-only Yogg run:

```text
auto_reports: /home/yoga/Genesis/runtime/auto_reports
nodevault: /home/yoga/.genesis/workshop_v4.sqlite
service file: /etc/systemd/system/yogg-auto.service
max_rounds: 500
created_since: 2026-05-23 00:00:00
```

Queue snapshot after weak-consumption tightening:

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

## 2. Review rules

This review accepts only these decision verbs:

```text
accept_as_governance_signal
accept_as_evidence_signal
hold_for_verification
needs_contract_resolution
needs_human_review
reject_as_activity_only
```

Non-actions:

```text
Do not modify NodeVault.
Do not change confidence or epistemic_status.
Do not restart services.
Do not patch C-Phase.
Do not change dry-state logic.
Do not train models from this review.
```

## 3. Decisions

## 3.1 knowledge_outcome_without_physical_outcome

Queue state:

```text
needs_resolution
```

Review decision:

```text
accept_as_governance_signal
```

Accepted claim:

```text
Recent Yogg output shows a strong mismatch between knowledge-domain activity and physical sandbox outcome.
```

Evidence:

```text
knowledge_outcome: 414
line_activity_evidence: 370
physical_outcome: 2
```

Meaning:

```text
Yogg's recent value is not primarily physical patch production.
It is surfacing that concept-exploration work needs separate outcome domains.
```

Decision boundary:

```text
This does not justify resetting dry-state logic.
This does not make knowledge writes equal outcome.
This does justify drafting an outcome-domain contract.
```

Next action:

```text
Draft a V6 outcome-domain contract separating physical file outcome, knowledge-domain evidence, line activity evidence, line consumption evidence, and governance review outcome.
```

## 3.2 kb_delta_node_only_line_gap

Queue state:

```text
needs_resolution
```

Review decision:

```text
needs_contract_resolution
```

Accepted claim:

```text
Round reports can show Line activity while `kb_delta` remains node-oriented and does not expose line/graph delta as a first-class domain.
```

Decision boundary:

```text
Do not add runtime fields until their consumer is defined.
Do not rename `kb_delta` without preserving compatibility.
Do not treat line creation as outcome.
```

Next action:

```text
Define a consumer contract for `line_delta` / `graph_delta` before any runtime schema change.
```

## 3.3 record_line_rejections_present

Queue state:

```text
needs_resolution
```

Review decision:

```text
hold_for_verification
```

Accepted claim:

```text
Rejected Line attempts must be separated from successful Line evidence.
```

Decision boundary:

```text
Line errors are quality evidence, not failure outcome by themselves.
They should not be merged into successful line counts.
```

Next action:

```text
Inspect representative rejected `record_line` results and classify whether failures are duplicate prevention, validation errors, malformed arguments, or environmental faults.
```

## 3.4 activity_signal_promotion_candidates

Queue state:

```text
candidate
```

Review decision:

```text
accept_as_evidence_signal
```

Accepted claim:

```text
Activity-positive rounds can enter review only when they carry concrete evidence refs and a named outcome domain.
```

Decision boundary:

```text
`progress_class` remains activity.
It can become review input, not direct outcome.
```

Next action:

```text
Use the ActivitySignalPromotionGate draft as the minimum rule for future activity promotion.
```

## 3.5 reasoning_line_activity_visible

Queue state:

```text
needs_verification
```

Review decision:

```text
accept_as_evidence_signal
```

Accepted claim:

```text
Line production is visible and measurable through telemetry, events, and NodeVault reasoning_lines.
```

Decision boundary:

```text
Visible Line production is not Line outcome.
```

Next action:

```text
Keep Line production as evidence input for the line/graph outcome contract.
```

## 3.6 reasoning_line_node_selected_into_active_context

Queue state:

```text
needs_verification
```

Review decision:

```text
hold_for_verification
```

Accepted claim:

```text
A node created by a successful Line event appearing in active context is weak consumption evidence.
```

Decision boundary:

```text
Active context selection does not prove the node changed a future decision.
It must not be marked as resolved outcome.
```

Next action:

```text
Look for stronger traces: later reasoning basis use, review decision reference, promotion gate use, or training sample inclusion.
```

## 3.7 reasoning_lines_unconsumed_or_unproven

Queue state:

```text
needs_verification
```

Review decision:

```text
hold_for_verification
```

Accepted claim:

```text
Recent reasoning_lines are mostly unconsumed or lack observable downstream consumption evidence.
```

Evidence:

```text
reasoning_lines_total since 2026-05-23: 1470
consumed_as_basis: 0
unconsumed_or_unproven: 1470
```

Decision boundary:

```text
This is not proof that the lines are useless.
It is proof that the current system does not expose a strong consumption path for them.
```

Next action:

```text
Design a read-only consumption trace that connects line-created nodes to later decisions or retrieval effects.
```

## 3.8 constraint_surface_private_bypass_audit

Queue state:

```text
needs_verification
```

Review decision:

```text
hold_for_verification
```

Accepted claim:

```text
Declared service constraints require bypass analysis before they can be trusted as real safety boundaries.
```

Current evidence:

```text
service_snapshot_available: true
service_user_declared: true
service_memory_limit_declared: true
service_restart_declared: true
sudo_snapshot_available: false
broad_sudo_detected: false
risk_level: medium
```

Decision boundary:

```text
Without sudo snapshot evidence, do not quarantine as broad-sudo bypass.
Do not execute sudo to discover it.
```

Next action:

```text
Use only an already captured sudoers snapshot or manually provided read-only evidence for bypass review.
```

## 3.9 privileged_promotion_review_required

Queue state:

```text
needs_human_review
```

Review decision:

```text
needs_human_review
```

Accepted claim:

```text
Privileged restart/promotion paths require explicit human review before being treated as trusted promotion semantics.
```

Decision boundary:

```text
Do not legitimize the current privileged cold path by documenting it.
Do not restart Yogg from this review.
```

Next action:

```text
Keep current path separate from desired path: review → bounded apply → pre/post canary → promote.
```

## 3.10 raw_progress_class_activity_only

Queue state:

```text
ignored
```

Review decision:

```text
reject_as_activity_only
```

Accepted claim:

```text
A progress_class-only signal without concrete evidence path should not enter outcome review.
```

Next action:

```text
None.
```

## 3.11 no_observed_outcome_domain

Queue state:

```text
ignored
```

Review decision:

```text
reject_as_activity_only
```

Accepted claim:

```text
A round with no observed physical, knowledge, or line-domain evidence should not be promoted.
```

Next action:

```text
None.
```

## 4. Resulting promotion candidates

Accepted for next design work:

```text
knowledge_outcome_without_physical_outcome
kb_delta_node_only_line_gap
activity_signal_promotion_candidates
reasoning_line_activity_visible
```

Held for verification:

```text
record_line_rejections_present
reasoning_line_node_selected_into_active_context
reasoning_lines_unconsumed_or_unproven
constraint_surface_private_bypass_audit
```

Requires human review:

```text
privileged_promotion_review_required
```

Rejected as activity-only:

```text
raw_progress_class_activity_only
no_observed_outcome_domain
```

## 5. Next contract to draft

The next useful artifact is:

```text
V6 outcome-domain contract
docs/v6_outcome_domain_contract.md
```

Minimum domains:

```text
physical_file_outcome
knowledge_domain_evidence
line_activity_evidence
line_consumption_evidence
governance_review_outcome
```

The contract should answer:

```text
Who consumes each domain?
What decision changes?
Where is consumption observable?
Which domains are allowed to affect dry-state, promotion, canary, or training readiness?
```
