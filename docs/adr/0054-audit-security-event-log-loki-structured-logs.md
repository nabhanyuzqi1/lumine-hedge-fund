# ADR-0054 — Audit: security event log + Loki structured logs

- **Status:** Accepted
- **Phase:** 12-security
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

Security-relevant events (auth attempts, kill-switch toggles, order
cancellations, proposal overrides, key rotations, deploy events, config
changes) need a queryable, structured audit trail separate from operational
logs. The audit trail must be tamper-resistant at the application layer. The
threat model (ADR-0001) does not include an attacker with database root
access.

## Decision

PostgreSQL `security_events` table (append-only, 90-day retention) for
structured security events: auth attempts, kill-switch toggles, order
cancellations, proposal overrides, key rotations, deploy events, and config
changes. Loki + Promtail for all structured logs with `security=true` label
and `trace_id` correlation. Prometheus alerting on security anomalies.

## Rationale

- Two complementary logging paths: PostgreSQL for queryable, structured audit
  trail; Loki for operational log correlation via `trace_id`.
- Append-only table with no DELETE permission means the audit trail cannot be
  tampered with by the application. Only direct SQL by the operator can
  modify or archive records.
- 90-day retention for security events (vs 30-day for operational logs) gives
  a longer investigation window for security incidents.
- Alerting on patterns (brute force, kill-switch, overrides) means the
  operator is notified of security-relevant events, not just system health
  events.
- SIEM integration (Splunk/ELK Cloud) rejected: self-hosted Loki +
  PostgreSQL is sufficient for a single-node deployment; SIEM adds cost and
  an external dependency.
- Blockchain/tamper-proof log rejected: the threat model does not include an
  attacker with database root access; PostgreSQL access control +
  append-only policy is sufficient.
- Real-time anomaly detection ML rejected: rules-based alerting catches the
  known patterns; ML adds complexity without clear benefit at V1 scale.

## Consequences

- Positive: structured, queryable audit trail with no application-level
  DELETE.
- Positive: `trace_id` correlation across security events and operational
  logs.
- Negative: 90-day retention may be insufficient for slow-burn incidents
  (mitigated: extendable by policy).
- Reversibility: retention and alerting rules are policy; the dual-path
  architecture is structural.

## Cross-references

- Related ADRs: ADR-0001, ADR-0048, ADR-0017
- Implements principle(s): #10
- Affects phases: 12, 11
- Source document: `../12-security/decisions.md` (D12-6)
