# ADR-0056 — Test environments: 3 environments, no dedicated staging server

- **Status:** Accepted
- **Phase:** 13-testing
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

A single VPS is the Phase 1 constraint. Paper trading requires a live MT5
connection and continuous uptime — a developer laptop cannot provide this.
Staging must run somewhere with MT5 access. A dedicated staging server would
double VPS cost for no security benefit at V1 scale if isolation can be
achieved at the data layer.

## Decision

Three environments — CI (ephemeral GitHub Actions runner with testcontainers),
staging (same VPS as production, separate DB/Redis/ports, MT5 paper account),
and production (same VPS, live account). No dedicated staging server.

## Rationale

- A single VPS is the Phase 1 constraint. Staging runs on the same node as
  production, completely isolated at the database, Redis, network, and port
  level. This is safe because staging has no public access — it is reachable
  only via internal IP allowlist.
- Dedicated staging server rejected: doubles VPS cost for no security benefit
  at V1 scale. The isolation is at the data layer, not the hardware layer.
- CI environment is ephemeral — testcontainers provide fresh PostgreSQL and
  Redis per run. No shared state, no cross-run contamination.
- Local-only testing rejected: paper trading requires a live MT5 connection
  and continuous uptime; a developer laptop cannot provide this.

## Consequences

- Positive: no additional server cost for staging.
- Positive: CI is fully ephemeral — no cross-run contamination.
- Negative: staging shares hardware with production — a staging runaway could
  impact production performance (mitigated: resource limits in Docker
  Compose).
- Reversibility: move staging to a dedicated server by superseding this ADR.

## Cross-references

- Related ADRs: ADR-0055, ADR-0057
- Implements principle(s): #5
- Affects phases: 13, 11
- Source document: `../13-testing/decisions.md` (D13-2)
