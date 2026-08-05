# Runbook — Rollback

- **Status:** active · **Drilled:** no
- **Owner:** devops
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

## When to roll back
- P0/P1 metric degradation after a deploy with no immediate fix.
- A model/prompt/policy promotion causes FAILED_SAFE spike or calibration
  drift (ADR-0030, ADR-0032).

## Roll back the build
1. Drain (per deployment-runbook).
2. Deploy the previous known-good image.
3. Revert DB migrations ONLY if reversible and required. Never revert a
   migration that would destroy append-only audit data (lineage, journal,
   fills, reasoning_traces). If a migration is irreversible and the cause
   is data, patch forward, don't roll back.

## Roll back a model/prompt/policy version
- Flip the registry row status: current `production` → `deprecated`;
  previous `deprecated` → `production` (per supersession model, ADR-0025).
- This is a configuration change, not a redeploy.
- In-flight runs pinning the rolled-back version: per resume gate semantics
  (ADR-0025). `exact`/`breaking` → ABORTED_STALE (fresh run with the
  restored version); `backward_compatible` → may continue.

## After rollback
- Post-mortem within 48h. ADR if the rollback revealed an architectural issue.
- Update `deviation-log.md`.
