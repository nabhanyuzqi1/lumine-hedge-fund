# AI Promotion Gates — Machine-Enforced Eval Linkage

## Overview

Decision **D13-4**: a `prompt_versions` row cannot be flipped to
`production` status without a passing eval run, pinned by hash, for
the exact model version being promoted. This closes the gap in Phase
4's promotion discipline: today the registry schema
(`registry-schema.md:34-45`) permits the CIO to promote a prompt on
judgment alone, with no structural link between the prompt and the
eval evidence that justifies it.

This document binds Phase 4 prompts, Phase 6 models, and Phase 13
evals into a single machine-enforced invariant:

> **No prompt ships to production without a passing eval, pinned by
> hash, for the exact model_version being promoted.**

The human CIO still decides promotion (principle #7). This gate makes
the decision auditable and refuses promotion that lacks evidence —
the CIO signs off on eval-gated promotions, not in spite of them.

## Decision: eval linkage on `prompt_versions`

### Schema additions

`prompt_versions` (Phase 3 registry) gains two columns:

```sql
ALTER TABLE prompt_versions
  ADD COLUMN eval_suite_id   UUID REFERENCES eval_suites(id),
  ADD COLUMN eval_pass_hash  TEXT;
```

| Column | Semantics |
|--------|-----------|
| `eval_suite_id` | FK to the `eval_suites` row that the prompt must pass. NULL only for rows that have never been promoted (sandbox). Non-NULL required to enter `production`. |
| `eval_pass_hash` | SHA-256 of the passing eval result manifest. Immutable once set. Pinned in `lineage_records` so a historical decision's prompt is provably eval-gated. |

Both columns are immutable once the row reaches `production`. A row in
`production` with a null `eval_pass_hash` is a schema violation
(enforced by the promotion API, not just convention).

### New table: `eval_suites`

```sql
CREATE TABLE eval_suites (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name           TEXT NOT NULL,
  version        SEMVER NOT NULL,
  dataset_ref    TEXT NOT NULL,          -- content-addressed (hash-pinned corpus path or URI)
  eval_code_hash TEXT NOT NULL,          -- SHA-256 of the eval harness code that ran
  threshold      JSONB NOT NULL,         -- per-metric pass thresholds (see below)
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (name, version)
);
```

`threshold` is a JSONB object keyed by metric name with pass criteria:

```json
{
  "brier_score_max": 0.18,
  "schema_valid_rate_min": 1.00,
  "bias_accuracy_min": 0.80,
  "hallucination_rate_max": 0.00,
  "containment_rate_min": 1.00
}
```

A metric absent from `threshold` is not evaluated; a metric present is
binding. The eval harness code is hash-pinned (`eval_code_hash`) so a
passing run is reproducible against the exact harness version, not
just the exact dataset.

## Promotion API contract

The registry's promotion endpoint (`staging` → `production`)
**refuses** to flip a `prompt_versions` row to `production` unless:

1. `eval_suite_id` is non-NULL and resolves to an `eval_suites` row.
2. An eval run exists for the **exact** `model_version_id` being
   promoted (the production-bound model for the role the prompt
   serves — no cross-model substitution).
3. The eval run's result manifest, when hashed, equals
   `eval_pass_hash`.
4. Every metric in `eval_suites.threshold` passes (≥ for `_min`, ≤
   for `_max`) against the run's measured values.

The API returns a structured rejection if any condition fails. The
rejection is itself logged as an audit event (Phase 7 journal).

### No cross-model substitution

A passing eval for model A does not authorize promoting the prompt
against model B. The eval must run on the exact `model_version_id`
the routing policy will resolve at decision time. Rationale: a prompt
that passes on GPT-5.5 may fail on DeepSeek V4; substituting eval
evidence hides that. The `eval_pass_hash` is bound to a specific
`(prompt_version_id, model_version_id, eval_suite_id)` triple.

### "Passing" definition

A run passes when, for every entry in
`eval_suites.threshold`:

| Threshold suffix | Comparison |
|------------------|------------|
| `_max` | measured ≤ threshold |
| `_min` | measured ≥ threshold |
| `_eq` | measured == threshold (within 1e-9) |

All metrics in `threshold` must pass. There is no partial credit and
no averaging across metrics. A run that passes 9 of 10 metrics fails.

### Eval result manifest

The manifest is a JSON document hashed to produce `eval_pass_hash`:

```json
{
  "eval_suite_id": "<uuid>",
  "prompt_version_id": "<uuid>",
  "model_version_id": "<uuid>",
  "eval_code_hash": "<sha256>",
  "dataset_ref": "<content-addressed ref>",
  "ran_at": "<iso8601>",
  "metrics": {
    "brier_score": 0.14,
    "schema_valid_rate": 1.00,
    "bias_accuracy": 0.87,
    "hallucination_rate": 0.00,
    "containment_rate": 1.00
  },
  "threshold_version": "<eval_suites.version>",
  "verdict": "pass"
}
```

`eval_pass_hash = SHA-256(canonical_json(manifest))`. The manifest is
stored alongside the eval run (Phase 14 eval harness); the hash lives
on `prompt_versions` and is pinned in `lineage_records`.

## Audit: eval-gate proof in lineage

When a decision is made, the `prompt_version_id` pinned in
`lineage_records` carries its `eval_pass_hash`. An auditor asking
"was the prompt that produced this decision eval-gated?" answers it
by:

1. Resolving `prompt_version_id` from the lineage row.
2. Reading `eval_pass_hash` from that prompt row.
3. Confirming the hash resolves to a passing eval manifest for the
   pinned `model_version_id`.

A lineage row whose prompt has a null `eval_pass_hash` is, after this
gate ships, impossible in production — the promotion API would have
refused the prompt. Pre-gate historical rows are flagged in audit
reports as "pre-eval-gate" and not retroactively amended (the table
is append-only).

## What this document does NOT define

- Eval harness implementation (Phase 14+).
- Eval dataset authoring (Phase 14+, alongside prompts —
  `ai-testing.md` defines methodology, not content).
- Drift detection on production prompts (that is `ai-testing.md`'s
  drift layer; this gate is promotion-time, not runtime).
- The promotion API's HTTP shape (Phase 9).
- Calibration metrics (those live in `confidence-calibration.md`;
  this gate treats `brier_score_max` as a threshold input, not a
  definition).

## Phase boundary

This document binds Phase 4 (prompt storage/versioning), Phase 6
(model registry — the exact `model_version_id` requirement), and
Phase 13 (eval methodology) into a machine-enforced promotion gate.
It amends `registry-schema.md` (Phase 3) by adding two columns to
`prompt_versions` and one new table; it does not alter the status
lifecycle, the CIO human gate, or the replaceability contract. It
does not define eval harness code, dataset content, or the promotion
API's transport.
