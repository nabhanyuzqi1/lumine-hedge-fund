# ADR-0028 — Machine-enforced eval gate on prompt promotion

- **Status:** Accepted
- **Phase:** 13-testing
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

A `prompt_versions` row cannot be flipped to `production` status without a
passing eval run, pinned by hash, for the exact model version being
promoted. Phase 4's promotion discipline permits the CIO to promote a
prompt on judgment alone, with no structural link between the prompt and
the eval evidence that justifies it. Rule 10 (prompts and schemas
versioned, hashed, auditable) is satisfied but not evaluated — there is no
machine-enforced gate.

## Decision

No prompt ships to production without a passing eval, pinned by hash, for
the exact `model_version_id` being promoted. `prompt_versions` gains
`eval_suite_id` (FK to a new `eval_suites` table) and `eval_pass_hash`
(SHA-256 of the passing eval result manifest, immutable). The promotion
API refuses to flip a row to `production` unless: the eval suite resolves,
an eval run exists for the exact model version, the manifest hash matches,
and every metric in the suite's threshold passes. No cross-model
substitution: a passing eval for model A does not authorize promoting the
prompt against model B.

## Rationale

- The human CIO still decides promotion (principle #7); this gate makes
  the decision auditable and refuses promotion that lacks evidence.
- No partial credit: all metrics in the threshold must pass; a run that
  passes 9 of 10 fails.
- No cross-model substitution: a prompt that passes on GPT-5.5 may fail on
  DeepSeek V4; substituting eval evidence hides that.
- `eval_pass_hash` is pinned in `lineage_records` so a historical
  decision's prompt is provably eval-gated.

## Consequences

- Positive: no prompt reaches production without machine-enforced eval
  evidence.
- Positive: audit can prove every production prompt was eval-gated.
- Negative: pre-gate historical rows are flagged "pre-eval-gate" and not
  retroactively amended (table is append-only).
- Reversibility: the gate is structural; thresholds are policy
  (`eval_suites.threshold`).

## Cross-references

- Related ADRs: ADR-0015, ADR-0030, ADR-0044
- Implements principle(s): #4, #6, #7
- Affects phases: 13, 04, 06, 03
- Source document: `../13-testing/ai-promotion-gates.md` (S8)
