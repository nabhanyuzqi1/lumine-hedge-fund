# Confidence Calibration — Calibrated Escalation

## Overview

Decision **D6-7**: escalation in `model-routing.md` (trigger #1, low
confidence) fires on **calibrated** confidence, not raw LLM
confidence. LLMs are poorly calibrated — a raw "0.8 confidence" often
maps to 0.55 empirical accuracy. Escalating on raw confidence fires
on noise: it escalates when the model is loud, not when the model is
uncertain.

This document defines the calibration measurement, the calibration
map applied at routing time, the drift alert that blocks promotion,
and the lineage pinning that keeps escalation decisions reproducible.

This document amends `model-routing.md` (Phase 6) trigger #1 and
ties to `model-risk-management.md` (the ECE threshold blocks
promotion).

## Decision: calibration measured per (role, model_version)

### The problem

Raw LLM confidence is the probability the model asserts, not the
probability the model is right. On a held-out eval set where each
scenario has a ground-truth outcome (bias correctness for analysts,
action correctness for IC/CIO), the empirical accuracy at raw
confidence 0.8 may be 0.55. Escalating at `raw < 0.7` therefore
escalates on the model's assertiveness, not its uncertainty — the
opposite of the intent.

### Calibration measurement

For each `(role, model_version_id)` pair, calibration is measured on
a held-out eval set (disjoint from the prompt-quality eval set in
`ai-testing.md`):

| Metric | Definition | Target |
|--------|------------|--------|
| Brier score | Mean squared error between predicted probability and binary outcome | ≤ 0.18 (governance threshold, initial) |
| Reliability diagram | Bin raw confidence into deciles; plot empirical accuracy per bin | Visual + tabular |
| Expected Calibration Error (ECE) | Weighted average of |accuracy(bin) - mean_confidence(bin)| across bins | ≤ 0.15 (governance threshold, initial) |

The eval set for calibration is **ground-truth-labeled**: each
scenario has a known correct bias (analysts) or action (IC/CIO). The
set is versioned (`eval_suite_id` in `eval_suites`, per
`ai-promotion-gates.md`) and hash-pinned.

## Decision: calibration map on `model_versions`

`model_versions` (Phase 3 registry) gains two columns:

```sql
ALTER TABLE model_versions
  ADD COLUMN calibration_map JSONB,
  ADD COLUMN eca            FLOAT;
```

| Column | Semantics |
|--------|-----------|
| `calibration_map` | JSONB array of `{raw_bin, calibrated_prob}`. Example: `[{"raw_bin": [0.7, 0.8), "calibrated_prob": 0.58}, ...]`. Applied at routing time to convert raw confidence to calibrated confidence. |
| `eca` | Expected Calibration Error on the held-out set. Float in [0, 1]. |

`calibration_map` is the isotonic-regression (or binned-empirical)
mapping from raw confidence to calibrated probability. It is computed
once per `(role, model_version_id)` on the held-out set and stored on
the model row. A model row without calibration data has
`calibration_map = NULL` and `eca = NULL`; such a row cannot be
promoted (see drift / promotion gate below).

### Applying the map at routing time

`model-routing.md` trigger #1 is amended:

> **Low confidence (amended)**: role output `calibrated_confidence < policy.escalation.min_confidence` → re-run same role at next tier.

Where `calibrated_confidence = apply(calibration_map,
raw_confidence)`. The application is a bin lookup: find the
`raw_bin` containing the raw confidence, return the
`calibrated_prob`. Out-of-range raw values (e.g. raw 0.95 when the
top bin is [0.8, 0.9)) clamp to the nearest bin.

The raw confidence and the calibrated confidence are both recorded
in `reasoning_traces.parsed_output` (Phase 7) and in
`lineage_records.proposal`, so the escalation decision is
reconstructable: the auditor sees both values and the bin applied.

## Decision: drift alert blocks promotion

A new `model_version_id` with ECE > governance threshold (initial:
0.15) **cannot be promoted** to production. This ties directly to
`model-risk-management.md`'s approval workflow: calibration measured
is a precondition, and a model that is too poorly calibrated to
support escalation-based routing is not approvable.

On version bump (model A → model B):

- Measure B's calibration on the held-out set.
- If B's ECE > threshold → promotion refused. The model is too
  poorly calibrated; escalating on its confidence would fire on
  noise.
- If B's ECE ≤ threshold but B's ECE > A's ECE + 0.05 → warn (drift
  toward worse calibration) but permit promotion with CIO sign-off.
- If B's ECE ≤ A's ECE → no alert.

This is a **promotion-time** gate (blocks bad models from entering)
complemented by the **runtime** drift monitoring in
`model-risk-management.md` (recalibration on rolling production
sample).

## Decision: recalibration cadence

Calibration drifts over time even for the same model_version (provider
silent updates, distribution shift). Recalibration runs **monthly** on
a rolling production sample:

1. Sample the last month's production decisions (stratified by book,
   strategy, regime).
2. Label each with ground-truth outcome (bias correctness / action
   correctness).
3. Recompute Brier, ECE, reliability diagram.
4. If ECE on the production sample > 1.5× the approved-at ECE →
   alert + automatic rollback trigger (per
   `model-risk-management.md`).
5. If drift is within bounds → update `calibration_map` via a new
   `model_versions` row (the map is part of identity; changing it =
   new row, old rows stay pinned in lineage).

The monthly cadence is a policy value (`policy_versions`, scope
`calibration`), adjustable by the CIO.

## Lineage pinning: reproducible escalation

The `calibration_map` is versioned and pinned in `lineage_records`
via the existing `model_version_id` foreign key. The model row
carries the map; the lineage row pins the model; therefore the map
that governed escalation for any historical decision is
re-addressable.

An auditor reconstructing an escalation decision:

1. Resolves `model_version_id` from the lineage row.
2. Reads `calibration_map` and `eca` from that model row.
3. Reads the raw confidence from
   `reasoning_traces.parsed_output.confidence_raw`.
4. Applies the map → calibrated confidence.
5. Compares to `policy.escalation.min_confidence` (resolved from the
   pinned `policy_version_id`).

Every step is deterministic and re-addressable. The escalation
decision is reproducible (principle #6).

## What this document does NOT define

- Calibration computation code (isotonic regression implementation,
  binning strategy — Phase 14+).
- The held-out eval set's content (Phase 14+, alongside prompts and
  `ai-testing.md` datasets).
- Ground-truth labeling methodology for IC/CIO actions (Phase 13 +
  Phase 14; "correct action" is strategy-dependent and defined in the
  eval suite).
- Alert routing (Phase 11).

## Phase boundary

This document amends `model-routing.md` (Phase 6) trigger #1 to use
calibrated confidence. It adds two columns to `model_versions`
(Phase 3 registry). It ties to `model-risk-management.md` (ECE
threshold blocks promotion) and `ai-promotion-gates.md` (the
calibration eval is an `eval_suites` row). It does not define the
routing tiers, the other escalation triggers, the registry status
lifecycle, or code. Calibration computation, eval set authoring, and
recalibration automation belong to Phase 14+.
