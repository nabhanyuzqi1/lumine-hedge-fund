# Onboarding — New DevOps / Ops

- **Status:** active
- **Owner:** devops / architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 180

## Day 1
1. `91-glossary.md`.
2. `docs/11-infrastructure/` — topology, observability, backup-dr,
   build-deploy, clock-and-time.
3. `docs/12-security/` — threat-model, ssh-access, network-firewall,
   encryption, audit-tamper-evidence, supply-chain.
4. `Makefile` — every command you'll run.
5. `.github/workflows/` — CI/CD pipelines.

## Week 1
6. `docs/90-governance-and-operations/94-runbooks/` — all runbooks.
7. `docs/11-infrastructure/backup-dr.md` + this tier's
   `94-runbooks/restore-test.md` (DR drills are monthly).
8. `docs/06-ai/gateway-admission-control.md` (the LLM gateway is a
   capacity-constrained resource).
9. Shadow on-call.

## Ops-specific invariants
- **Clock discipline.** chrony/NTP, ≤50ms skew, UTC everywhere (ADR-0035).
- **WORM anchor.** The audit hash chain anchors to S3 Object Lock
  Compliance mode; verify the anchor daily.
- **No autonomous kill-switch restart.** Only the CIO clears it (ADR-0010).
- **Reconciliation is a SETTLED gate.** A position cannot settle without
  passing daily broker reconciliation (ADR-0021).
- **Supply chain.** `pip-audit`, `osv-scanner`, `gitleaks`, SBOM run in CI
  (`.github/workflows/supply-chain.yml`).

## On-call essentials
- Page on: `TERMINATED_KILL`, `INTERNAL_INVARIANT`, `FAILED_SAFE` rate spike,
  kill-switch engaged, reconciliation break >1 day, chain-verification failure.
- See `94-runbooks/agent-failure-matrix.md` for agent-specific failures.
