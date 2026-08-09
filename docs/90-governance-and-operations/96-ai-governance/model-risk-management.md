# Model Risk Management — SR 11-7 Aligned Governance for LLM Investment Decisions

## Overview

Decision **D-GOV-1**: every `model_version` is a registered model
subject to model risk management discipline aligned to SR 11-7
(Federal Reserve Supervisory Letter on Model Risk Management), adapted
for an AI-native hedge fund where LLMs produce investment proposals.

The system uses LLMs to make investment decisions. That makes every
model_version a model under SR 11-7 scope: it must have a model card,
measured calibration, an approval record, drift monitoring, and a
rollback criterion. Phase 6's `model-registry.md` defines the
lifecycle; this document defines the risk management discipline that
governs it.

This document is governance policy. It is consumed by the Phase 6
registry (enforcement points), Phase 13 evals (evidence), and the CIO
(approver of record). It does not define code.

## Decision: model inventory and model cards

### Model inventory

Every row in `model_versions` (Phase 3 registry) is a registered
model. No model may be invoked by the live pipeline without a row in
`production` status. This is already enforced by the registry; this
document adds the model-card requirement.

### Model card

Each `model_versions` row in `production` must have a corresponding
model card. The model card is a registry artifact (versioned,
hash-pinned, stored alongside the model row). It records:

| Field | Content |
|-------|---------|
| `purpose` | The role(s) the model serves (e.g. "CIO Proposer, context-rich tier") and the decisions it informs |
| `training_data_summary` | What is known about the model's training data (provider-disclosed; "unknown" is an acceptable and noted answer for proprietary models) |
| `known_limitations` | Documented failure modes, calibration gaps, context-window limits, provider-noted caveats |
| `eval_results` | Reference to the passing eval manifest (`eval_pass_hash` from `ai-promotion-gates.md`) |
| `calibration_metrics` | Brier score, ECE, reliability diagram summary (from `confidence-calibration.md`) |
| `owner` | The human accountable for the model (CIO or delegate) |
| `approval_date` | When the CIO approved promotion to production |
| `approval_record_id` | Reference to the immutable approval record (see below) |

A `production` row without a model card is a governance violation.
The promotion API (Phase 6, extended by `ai-promotion-gates.md`)
refuses promotion without it.

## Decision: approval workflow

A model cannot enter `production` without all three:

1. **Eval pass.** A passing eval run for the model, pinned by
   `eval_pass_hash` (`ai-promotion-gates.md`). The eval runs against
   the exact `model_version_id`.
2. **Calibration measured.** Brier score, ECE, and a reliability
   diagram summary are recorded in the model card
   (`confidence-calibration.md`). A model with ECE above the
   governance threshold (initial: 0.15) cannot be promoted — it is
   uncalibrated and its confidence cannot drive escalation.
3. **CIO sign-off.** The CIO is the model risk approver of record.
   Sign-off is recorded immutably: an approval record with CIO
   identity, timestamp, model_version_id, and a reference to the eval
   and calibration evidence. The approval record is append-only.

The system cannot approve itself (principle #7). The CIO's approval
is the final gate; the eval and calibration requirements are
preconditions the CIO verifies, not substitutes for judgment.

## Decision: shadow promotion gate

Before a model enters `production`, it runs in **shadow** for N
cycles (initial: 200 cycles, configurable via `policy_versions`).
Shadow means:

- The model runs alongside the production model on the same cycle
  inputs.
- Its outputs are recorded (in `reasoning_traces` and a shadow
  comparison log) but never executed.
- No order is dispatched based on shadow output.

Promotion requires **shadow-vs-production agreement ≥ threshold**:
the shadow model's parsed output must structurally agree with the
production model's output (same action, same side, confidence within
a policy band) on ≥ 80% of shadow cycles (initial threshold, in
`policy_versions`). Disagreement is recorded and analyzed — it is
evidence, not an automatic blocker above the threshold.

A model that cannot reach the agreement threshold after the shadow
window is not promoted; the shadow report goes to the CIO for review.

## Decision: rollback criteria

Any of the following triggers **automatic rollback** to the prior
`production` model_version for the affected (tier, role-class) slot:

| Trigger | Threshold | Source |
|---------|-----------|--------|
| Calibration drift | ECE on rolling production sample > 1.5× the approved-at ECE, sustained over 1 week | `confidence-calibration.md` recalibration |
| Eval regression | Re-run of the pinned eval suite drops any metric below 90% of its pass threshold | Phase 13 drift detection |
| FAILED_SAFE rate spike | FAILED_SAFE rate for the model's role > 2× the rolling baseline over 1 week | Phase 7 observability |
| Provider incident | Provider-confirmed degradation or deprecation | ops lane |

Rollback flips the model_version to `retired` and the prior
`production` row back to `production` (the registry lifecycle permits
this — `retired` rows stay queryable, and the prior production row
was never deleted). The rollback is recorded as a governance audit
event with the trigger, threshold, and CIO notification. The CIO is
notified within the cycle; rollback does not wait for CIO approval
because it is a protective action (principle #10: safe state by
default). The CIO reviews post-hoc.

## Decision: drift monitoring

Ongoing eval on a **rolling sample of production decisions**: weekly,
the eval harness re-runs the pinned eval suite against the current
`production` model_version on a stratified sample of the last week's
decision contexts. Alert on drift:

- Any metric degrades by more than 10% relative to the
  promotion-time value → warn.
- Any metric drops below its pass threshold → page + automatic
  rollback trigger (above).

Drift monitoring is not a one-time promotion check; it is continuous
model risk surveillance. The weekly cadence is a policy value
(`policy_versions`, scope `model_risk`), adjustable by the CIO.

## Decision: agent-behavior regression suite

Per-agent evals gate agent prompt/model changes. When a
`prompt_version_id` or `model_version_id` changes for a role
(CIO Proposer, IC Forum, any analyst), the agent's eval suite must
pass before the change reaches production. This is the
`ai-promotion-gates.md` invariant applied per-agent: the eval
suite is scoped to the role, and the gate is the same machine-enforced
refusal.

The regression suite is the union of:

1. The role's schema contract tests (Phase 13, Layer 1).
2. The role's prompt-quality eval (Phase 13, Layer 2).
3. The role's contribution to decision-quality backtest (Phase 13,
   Layer 5) — measured in shadow, not live.

A change that regresses any layer is blocked.

## Decision: human oversight

The CIO is the **model risk approver of record**. The system records
approvals immutably (approval records are append-only, hash-pinned).
The CIO's responsibilities under this policy:

- Approve each model promotion to production (after eval, calibration,
  and shadow).
- Review drift reports weekly.
- Acknowledge rollback events post-hoc.
- Approve recalibration cadence changes.

The system's responsibilities:

- Refuse promotion without evidence (machine-enforced).
- Monitor drift continuously.
- Execute rollback automatically on trigger.
- Present evidence to the CIO for review.

The CIO cannot delegate approval to the system (principle #7). The
system cannot approve itself. The boundary is absolute.

## What this document does NOT define

- Eval harness implementation (Phase 14+).
- Calibration computation code (`confidence-calibration.md` defines
  the metrics; code is Phase 14+).
- Shadow comparison log schema (Phase 5 physical storage, when
  implemented).
- Alert routing and paging (Phase 11).
- The CIO's review tooling (Phase 10 frontend, outside this policy).

## Phase boundary

This document is governance policy. It is consumed by:

- **Phase 6** (`model-registry.md`): the promotion gate enforcement
  points and the model card requirement.
- **Phase 13** (`ai-testing.md`, `ai-promotion-gates.md`): the eval
  evidence and drift detection that feed this policy.
- **Phase 12** (Security): the immutability and audit-log
  requirements for approval records.

It does not modify the registry schema (Phase 3), the status
lifecycle, or the CIO human gate. It adds the risk-management
discipline that makes the existing lifecycle SR 11-7-aligned for
LLM-driven investment decisions.
