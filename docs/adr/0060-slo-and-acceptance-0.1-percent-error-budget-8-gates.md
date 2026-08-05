# ADR-0060 — SLO and acceptance: 0.1% error budget, 8 pre-launch gates

- **Status:** Accepted
- **Phase:** 13-testing
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

A single-node deployment with no external dependencies in the critical path
(MT5 and LLM are the only external calls, and both have graceful degradation)
can achieve 99.9% availability. Without an explicit error budget, every alert
becomes noise and every outage becomes a subjective judgment call. Live
capital must not be deployed until a minimum viable confidence threshold is
met.

## Decision

Service level objective: 99.9% API availability. Error budget: 0.1% = 43
minutes 50 seconds per month. Burn rate alerts: critical (2% burned in 1
hour), warning (5% burned in 6 hours). Pre-launch acceptance: 8 gates must
pass before live capital is deployed — all 4 blocking CI gates, backtest
(Sharpe > 0, max drawdown < 20%), paper trading (2 weeks with zero order
errors and zero lineage gaps), kill-switch test, backup restore test, MT5
bridge failover test, security pentest (no critical/high open), and deploy
verify.

## Rationale

- 99.9% is achievable for a single-node deployment with no external
  dependencies in the critical path (MT5 and LLM are the only external calls,
  and both have graceful degradation — broker-side SL/TP and cycle-skip
  respectively).
- 8 pre-launch gates are the minimum viable confidence threshold before live
  capital. Each gate tests a distinct failure mode. Skipping any gate means
  accepting an untested risk.
- Backtest thresholds (Sharpe > 0, max drawdown < 20%) are deliberately low
  — they are sanity checks, not performance targets. A strategy that fails
  these thresholds is likely broken, not just unprofitable.
- 99.99% availability rejected: requires redundant infrastructure (hot
  standby, load balancer, multi-AZ) that V1 does not have.
- No error budget rejected: without an explicit budget, every alert becomes
  noise and every outage becomes a subjective judgment call.
- Backtest as performance gate (Sharpe > 1.0) rejected: performance targets
  belong to strategy research, not system acceptance. The acceptance gate
  verifies the system works correctly; performance is a strategy concern.

## Consequences

- Positive: explicit error budget makes the availability/cost trade-off
  visible.
- Positive: 8 pre-launch gates ensure no untested risk reaches live capital.
- Negative: 99.9% allows ~44 min/month downtime — may not satisfy external
  SLA expectations (mitigated: V1 has no external SLA obligation).
- Reversibility: SLO target and gate thresholds are policy; the gate
  structure is structural.

## Cross-references

- Related ADRs: ADR-0055, ADR-0057, ADR-0059
- Implements principle(s): #4, #7
- Affects phases: 13, 14
- Source document: `../13-testing/decisions.md` (D13-6)
