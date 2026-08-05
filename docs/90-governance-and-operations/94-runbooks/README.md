# Runbooks

- **Status:** active
- **Owner:** devops / architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

Operational runbooks. A runbook that has never been run is a **draft** —
drill it, then mark it `drilled`.

## Index

### Incident response
- [`incident-response.md`](incident-response.md) — generic severity triage and escalation.
- [`chain-verification-failure.md`](chain-verification-failure.md) — audit hash-chain break (page).

### Deployment
- [`deployment-runbook.md`](deployment-runbook.md) — safe deploy with graceful drain.
- [`rollback-runbook.md`](rollback-runbook.md) — revert a deploy.

### Trading / MT5
- [`mt5-disconnection.md`](mt5-disconnection.md) — bridge lost connection.
- [`mt5-reconnect-open-position.md`](mt5-reconnect-open-position.md) — reconnect with open exposure.
- [`mt5-terminal-desync.md`](mt5-terminal-desync.md) — terminal state diverges from internal.
- [`broker-slippage-spike.md`](broker-slippage-spike.md) — slippage > threshold cluster.
- [`reconciliation-break.md`](reconciliation-break.md) — internal vs broker mismatch.

### AI / agents
- [`agent-failure-matrix.md`](agent-failure-matrix.md) — (agent × failure_code) → action (ADR-0033).
- [`llm-cost-spike.md`](llm-cost-spike.md) — gateway spend anomaly.
- [`agent-stuck-loop.md`](agent-stuck-loop.md) — repeated FAILED_SAFE / ABORTED_STALE.

### Recovery
- [`restore-test.md`](restore-test.md) — monthly DR restore drill (ADR-0017, backup-dr).

## Severity

| Sev | Meaning | Response |
|-----|---------|----------|
| P0 | Capital at risk / audit integrity lost | Page immediately; CIO notified |
| P1 | Degraded trading / missed decisions | Page on-call |
| P2 | Degraded non-critical | Next business day |
| P3 | Cosmetic / tech debt | Backlog |
