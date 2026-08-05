# Runbook — LLM Cost Spike (P1)

- **Status:** active · **Drilled:** no
- **Owner:** ai-engineers / cio
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

## Trigger
FinOps alert: gateway spend > budget threshold, or token consumption spikes
without a corresponding decision-volume increase (see `95-finops/`).

## Steps
1. Check `gateway_tokens_in_flight`, `gateway_admission_total{lane,outcome}`,
   `workflow_runs_total`. Is a lane stuck retrying? Is research running
   unbounded?
2. Check escalation rate: are too many cycles escalating to `strongest`
   tier? (Calibration drift — ADR-0032 — can cause this.)
3. If research is the cause: cut `research_budget` to zero
   (`comparative-replay-isolation.md` ADR-0026) to drain research runs.
4. If a runaway loop: engage kill switch for the affected book/strategy
   (CIO authority).
5. Inspect `llm_usage` by model_version / role / tier; identify the cost
   source.
6. Apply rate reduction via the admission-control token-bucket
   (ADR-0022) if needed.

## Prevention
- Monthly cost review (`95-finops/monthly-cost-review.md`).
- Per-tier budgets and alerts (`95-finops/llm-budget.md`).
- Calibration gates prevent over-escalation (ADR-0032).
