# ADR-0021 — Daily broker reconciliation is a SETTLED gate

- **Status:** Accepted
- **Phase:** 08-trading
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

There is no reconciliation against broker statements. The bridge-level
reconciliation contract (compare `mt5.positions` to PostgreSQL `positions`)
is internal drift detection, not reconciliation against the broker of
record. For an institutional trading system, daily reconciliation against
the broker statement is table stakes: it is how the system proves its
internal ledger matches the broker's view of trades, positions, and cash.
Internal SETTLED without broker reconciliation means silent position drift.

## Decision

Daily automated reconciliation against the broker statement is mandatory.
Reconciliation is a GATE: an order cannot reach SETTLED without a passing
reconciliation for the trading day the order closed on. The job compares
fills, quantities, prices, positions, swaps, commissions, and balance
against MT5 `HistoryOrders`/`HistoryDeals`. Breaks are classified into a
fixed taxonomy; material breaks page the operator and arm the kill switch
for the affected book. Reconciliation reports are hash-pinned artifacts.

## Rationale

- Broker reconciliation proves the internal ledger matches the broker; it
  does not replace the journal (D7-5).
- Making it a SETTLED gate means an unreconciled order's PnL is not
  finalized — it cannot be reported as realized P&L.
- A fixed break taxonomy makes auto-resolution and escalation
  deterministic.
- Corrections are new `fills` rows with new `lineage_id`, never overwrites
  (D7-8).

## Consequences

- Positive: the system proves ledger-broker parity daily.
- Positive: a `position_mismatch` halts trading on the affected book (safe
  state).
- Negative: a failed reconciliation job (broker unreachable) holds all
  CLOSED orders in CLOSED, not SETTLED.
- Reversibility: the gate is structural; tolerances are policy.

## Cross-references

- Related ADRs: ADR-0007, ADR-0005, ADR-0024, ADR-0040
- Implements principle(s): #4, #10
- Affects phases: 08, 05, 11
- Source document: `../08-trading/reconciliation.md` (S20)
