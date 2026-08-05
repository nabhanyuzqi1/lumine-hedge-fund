# ADR-0032 — Confidence calibration gate on escalation

- **Status:** Accepted
- **Phase:** 06-ai
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

Escalation in `model-routing.md` (trigger #1, low confidence) fires on raw
LLM confidence. LLMs are poorly calibrated — a raw "0.8 confidence" often
maps to 0.55 empirical accuracy. Escalating on raw confidence fires on
noise: it escalates when the model is loud, not when the model is
uncertain. Uncalibrated LLM confidence fired escalation on noise.

## Decision

Escalation fires on calibrated confidence, not raw LLM confidence. A
calibration map (isotonic-regression or binned-empirical mapping) is
measured per `(role, model_version_id)` on a held-out, ground-truth-labeled
eval set and stored on `model_versions` (`calibration_map` JSONB, `eca`
float). At routing time, `calibrated_confidence = apply(calibration_map,
raw_confidence)` via bin lookup. A new `model_version_id` with ECE >
governance threshold (initial: 0.15) cannot be promoted. Recalibration
runs monthly on a rolling production sample; if ECE on the production
sample > 1.5x the approved-at ECE, alert + automatic rollback trigger.

## Rationale

- Raw confidence is the probability the model asserts, not the probability
  it is right.
- Calibrated confidence makes escalation fire on actual uncertainty, not
  assertiveness.
- The calibration map is versioned and pinned in lineage via
  `model_version_id` — the map that governed escalation for any historical
  decision is re-addressable.
- ECE threshold blocks promotion of models too poorly calibrated to
  support escalation-based routing.

## Consequences

- Positive: escalation fires on real uncertainty, reducing false
  escalations.
- Positive: escalation decisions are reproducible (map + raw confidence +
  policy threshold all pinned).
- Negative: calibration measurement requires a ground-truth-labeled eval
  set (Phase 14+ authoring).
- Reversibility: the map is part of model identity; changing it = new
  `model_versions` row.

## Cross-references

- Related ADRs: ADR-0004, ADR-0030
- Implements principle(s): #6, #7
- Affects phases: 06, 03, 13
- Source document: `../06-ai/confidence-calibration.md` (S22)
