# ADR-0048 — Observability: Prometheus + Grafana + Loki + Tempo, self-hosted

- **Status:** Accepted
- **Phase:** 11-infrastructure
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

Operational telemetry of a trading fund must not leave the node — consistent
with Phase 1 minimal-egress. The `trace_id` flowing through logs and spans is
the same key Phase 9 `error-contract.md` returns to clients, closing the loop
between frontend ActivityLog and backend traces. A self-hosted stack avoids
license costs and data exfiltration.

## Decision

All telemetry stays on the VPS: Prometheus (metrics), Loki + Promtail (logs),
Tempo via OTel collector (traces), Grafana (dashboards), Alertmanager (alerts
to operator).

## Rationale

- Operational data of a trading fund does not leave the node — consistent
  with Phase 1 minimal-egress; zero license cost.
- The `trace_id` flowing through logs and spans is the same key Phase 9
  `error-contract.md` returns to clients, closing the loop between frontend
  ActivityLog and backend traces.
- Grafana Cloud rejected because it exfiltrates operational data.
- Sentry rejected to avoid another external dependency (error data is already
  captured by structured logs + traces).

## Consequences

- Positive: full observability stack with no data egress and zero license cost.
- Positive: trace_id correlation across logs, metrics, and traces.
- Negative: self-hosted observability stack adds VPS resource overhead.
- Reversibility: components are replaceable; metrics/logs/traces export to
  external sinks if needed later.

## Cross-references

- Related ADRs: ADR-0054
- Implements principle(s): #3, #5
- Affects phases: 11
- Source document: `../11-infrastructure/decisions.md` (D11-4)
