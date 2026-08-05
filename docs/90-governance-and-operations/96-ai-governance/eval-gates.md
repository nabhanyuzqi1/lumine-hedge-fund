# Eval Gates

- **Status:** active
- **Owner:** ai-engineers / qa
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

The matrix of eval gates binding artifacts to evidence before promotion.

## Gate matrix
| Artifact | Gate | Evidence | Blocks promotion? |
|----------|------|----------|-------------------|
| Prompt version | Eval suite pass on target model_version | `eval_pass_hash` (ADR-0028) | Yes (machine-enforced) |
| Model version | Eval suite pass + calibration measured + shadow agreement | calibration_map, ECA, shadow report (ADR-0030, ADR-0032) | Yes |
| Strategy version | OOS performance gates + regime coverage + capacity check | promotion readiness report (ADR-0031) | Yes (CIO sign-off on the report) |
| Feature version | Point-in-time correctness test + reproducibility test | feature store test (ADR-0020) | Yes |
| Policy version | Parity backtest vs prior version | parity score ≥ 0.95 (ADR-0019) | Yes |
| Regime version | Classifier agreement on labeled history + stability | regime eval (ADR-0034) | Yes |
| Message schema version | Compatibility test against all consumers | inter-agent compatibility CI (ADR-0038) | Yes |

## Eval suites registry
`eval_suites` table: id, name, version, dataset_ref, eval_code_hash,
threshold (JSONB), created_at. Thresholds are versioned — changing a
threshold is an eval-suite version promotion.

## Shadow period (models)
A new model runs in shadow (outputs recorded, not executed) for N cycles.
Promotion requires shadow-vs-production agreement ≥ threshold. Rollback
criteria: calibration drift, eval regression, FAILED_SAFE spike (ADR-0030).

## Continuous eval
Not just at promotion: a rolling sample of production decisions is
re-evaluated to detect drift. Alert on drift → rollback review.
