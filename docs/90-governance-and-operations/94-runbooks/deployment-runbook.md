# Runbook — Deployment

- **Status:** active · **Drilled:** no
- **Owner:** devops
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

## Pre-deploy
1. Confirm `make lint test typecheck` green on the branch.
2. Confirm CI green (including `docs.yml`, `supply-chain.yml`).
3. Review `spec-reconciliation.md` for new `Critical` gaps — do not deploy
   if a `Done`-tagged area has a new critical gap.
4. Confirm migrations are reversible; note any irreversible ones.

## Deploy (graceful drain per `07-autogen/recovery-and-termination.md`)
1. Stop accepting new triggers (drain signal per Phase 9 contract).
2. Let active runs reach their next checkpoint or terminal state.
3. Apply DB migrations (`make migrate`).
4. Deploy new build.
5. Health check.
6. Re-enable triggers.

## Post-deploy
1. Watch `workflow_failures_total`, `FAILED_SAFE` rate, `workflow_stage_duration`
   for 30 min.
2. Confirm a reconciliation passes at the next cycle.
3. If any P0/P1 metric degrades → `rollback-runbook.md`.

## Kill-switch-aware
- A deploy never auto-engages or auto-clears the kill switch (ADR-0010).
- If the kill switch is active, do not deploy unless explicitly authorized
  by the CIO.
