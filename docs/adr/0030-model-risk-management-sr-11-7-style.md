# ADR-0030 — Model risk management (SR 11-7 style)

- **Status:** Accepted
- **Phase:** 90-governance-and-operations
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

The system uses LLMs to make investment decisions. That makes every
`model_version` a model under SR 11-7 (Federal Reserve Supervisory Letter
on Model Risk Management) scope: it must have a model card, measured
calibration, an approval record, drift monitoring, and a rollback
criterion. Phase 6's `model-registry.md` defines the lifecycle; this
decision defines the risk management discipline that governs it.

## Decision

Every `model_version` is a registered model subject to model risk
management discipline aligned to SR 11-7. Each `production` model must
have: (1) a model card (purpose, training data summary, known limitations,
eval results, calibration metrics, owner, approval record); (2) an
approval workflow requiring eval pass + calibration measured + CIO
sign-off; (3) a shadow promotion gate (>= 200 cycles, >= 80%
shadow-vs-production agreement); (4) rollback criteria (calibration
drift, eval regression, FAILED_SAFE spike, provider incident); (5)
continuous drift monitoring (weekly rolling sample); (6) an agent-behavior
regression suite gating per-agent prompt/model changes.

## Rationale

- The system cannot approve itself (principle #7); the CIO is the model
  risk approver of record.
- Eval and calibration are preconditions the CIO verifies, not substitutes
  for judgment.
- Shadow promotion catches models that pass eval but disagree with
  production on live inputs.
- Rollback is automatic on trigger — a protective action (principle #10);
  the CIO reviews post-hoc.
- Drift monitoring is continuous model risk surveillance, not a one-time
  promotion check.

## Consequences

- Positive: every production model has a documented, hash-pinned evidence
  trail.
- Positive: drift and regression trigger automatic rollback before
  capital is at risk.
- Negative: model promotion is slower (shadow window + eval + calibration
  + CIO sign-off).
- Reversibility: rollback restores the prior production model; the
  retired model stays queryable.

## Cross-references

- Related ADRs: ADR-0028, ADR-0032, ADR-0004
- Implements principle(s): #4, #7, #10
- Affects phases: 90, 06, 13
- Source document: `../90-governance-and-operations/96-ai-governance/model-risk-management.md` (S13)
