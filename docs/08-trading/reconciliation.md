# Reconciliation Contract

## Overview

Finding S20: there is no reconciliation against broker statements.
`positions-fills-schema.md` defines a reconciliation contract at the
bridge level (compare `mt5.positions` to PostgreSQL `positions`), but
that is internal drift detection, not reconciliation against the
broker of record. For an institutional trading system, daily
reconciliation against the broker statement is table stakes: it is how
the system proves its internal ledger matches the broker's view of
trades, positions, and cash.

This document fixes the broker-reconciliation contract. It binds
Phase 8 (trading) to Phase 5 (storage) and Phase 11 (ops).

Decision **D8-8**: daily automated reconciliation against the broker
statement is mandatory. Reconciliation is a GATE: an order cannot
reach SETTLED without a passing reconciliation.

## Decision D8-8 — Broker reconciliation contract

### Daily automated reconciliation

Once per trading day, after the session close, a reconciliation job
(Phase 11 ops) pulls the broker statement and compares it to internal
state:

- **Broker source:** MT5 `AccountInfo` (balance, equity, margin) and
  `HistoryOrders` / `HistoryDeals` for the trading day (fills, swaps,
  commissions).
- **Internal source:** `positions`, `fills` (`positions-fills-schema.md`),
  and the order state machine (`order-lifecycle.md`).

The job compares, per symbol and per order:
- fill existence (every broker fill has an internal `fills` row and
  vice versa),
- fill quantity,
- fill price,
- resulting position (side, size, avg entry),
- swap and commission,
- account balance/equity.

### Break taxonomy

Every mismatch is classified into a break type. The taxonomy is fixed
so that auto-resolution rules and escalation paths are deterministic.

| Break type | Meaning | Severity |
|------------|---------|----------|
| `missing_fill` | A broker fill with no internal `fills` row, or vice versa. | High |
| `qty_mismatch` | Fill exists on both sides but quantity differs. | High |
| `price_mismatch` | Fill exists on both sides but price differs beyond tolerance. | High |
| `position_mismatch` | Internal `positions` snapshot disagrees with broker position (side, size, or existence). | Critical |
| `swap_mismatch` | Swap/finance charge differs beyond tolerance. | Medium |
| `commission_mismatch` | Commission differs beyond tolerance. | Medium |
| `corporate_action_missing` | A corporate action (split, dividend, rollover) affected the position and was not reflected internally. | Critical (when applicable) |
| `balance_mismatch` | Account balance/equity differs beyond tolerance after all of the above are resolved. | High |

Tolerances are defined per field in `policy_versions.reconciliation`
JSONB (e.g. `price_tolerance_pips: 0.5`, `qty_tolerance: 0.0001`,
`swap_tolerance: 0.01`). Tolerances absorb rounding and float noise;
anything beyond tolerance is a real break.

`corporate_action_missing` is N/A for XAUUSD spot in V1 (no dividends,
no splits) but is in the taxonomy for when the platform scales to
stocks and futures. The break type exists now so the taxonomy does not
need to change later.

### Auto-resolution rules

Benign breaks driven by latency or timing are auto-resolved. Each
auto-resolution is logged with the rule that fired and the before/after
state. Auto-resolution never silently overwrites the internal ledger;
it either (a) marks the break as `auto_resolved_latency` with an
explanation, or (b) inserts a correcting `fills` row with a new
`lineage_id` (never mutates an existing row — D7-8).

| Break | Auto-resolve rule |
|-------|-------------------|
| `missing_fill` (broker has fill, internal does not, and fill is < 2 min after session close) | Latency-driven ordering: insert a correcting `fills` row, mark `auto_resolved_latency`. |
| `missing_fill` (internal has fill, broker does not, and fill ts is within 2 min of job run) | Bridge lag: wait one re-run; if still missing, escalate. |
| `swap_mismatch` within tolerance | Mark `auto_resolved_tolerance`; record the delta in a `reconciliation_deltas` audit row. |
| `commission_mismatch` within tolerance | Same as swap. |
| `price_mismatch` within tolerance | Same as swap. |

Anything outside these rules is a material break and escalates.

### Escalation

- **Material breaks** (any `position_mismatch`, any
  `corporate_action_missing`, `balance_mismatch`, or any break above
  tolerance with value > `policy.reconciliation.material_threshold`)
  page the on-call operator immediately (D12-6 alerting).
- **Break-age SLA:** a break unresolved for > 1 day pages on-call
  daily until resolved. A break unresolved for > 3 days escalates to
  the CIO.
- **Trading halt:** if a `position_mismatch` or `balance_mismatch`
  is detected, the reconciliation job arms the kill switch for the
  affected book until the break is resolved. Safe state by default
  (principle #10): do not keep trading on a ledger you cannot trust.
- No auto-correction of material breaks. The operator investigates,
  documents the resolution, and the correction is a new ledger event
  (new `fills` row, new lineage), never an overwrite.

### Reconciliation report artifact

Each reconciliation run produces a report stored as an artifact
(Phase 5/11 storage):

| Field | Content |
|-------|---------|
| `reconciliation_run_id` | UUID |
| `run_ts` | When the job ran |
| `as_of_ts` | Broker statement date |
| `broker_account` | MT5 account ID |
| `breaks` | List of breaks with type, severity, symbol, order_id, delta, status |
| `auto_resolved` | Count and list |
| `material` | Count and list |
| `status` | `pass` \| `pass_with_auto` \| `material_breaks` \| `failed` |
| `artifact_hash` | SHA-256 of the report |

The report is hash-pinned and stored alongside lineage artifacts. It
is the evidence (principle #4) that the ledger matched the broker on
a given day.

### Reconciliation is a GATE

Per the order state machine (`order-lifecycle.md`), an order transitions
`CLOSED -> SETTLED` when settlement is complete and final PnL is
recorded. This document adds: SETTLED requires a passing
reconciliation for the trading day the order closed on.

- `status = pass` or `pass_with_auto`: SETTLED may proceed.
- `status = material_breaks`: the order is held in CLOSED; it cannot
  reach SETTLED until the break is resolved and a subsequent
  reconciliation passes.
- `status = failed` (job error, broker unreachable): SETTLED is held
  until a successful run completes. A failed reconciliation job is
  treated as a material break for gating purposes (cannot prove
  parity → cannot settle).

This makes reconciliation a hard gate, not a reporting exercise. An
order that cannot be reconciled does not settle, which means its PnL
is not finalized, which means it cannot be reported as realized P&L.

## Interaction with existing decisions

- **`positions-fills-schema.md` (bridge reconciliation):** that
  contract is internal drift detection (bridge view vs DB snapshot),
  run continuously. This document is broker reconciliation, run daily.
  They are complementary: bridge reconciliation catches bridge bugs in
  real time; broker reconciliation catches broker/DB divergence once
  per day. Both are required.
- **D7-5 (journal is truth):** the internal ledger (`fills`) is the
  journal of record. Broker reconciliation proves the journal matches
  the broker; it does not replace the journal.
- **D7-8 (replay never mutates):** corrections are new `fills` rows
  with new `lineage_id`, never overwrites. Reconciliation never
  mutates history.
- **D8-7 (risk engine determinism):** reconciliation is independent of
  sizing, but a `position_mismatch` arms the kill switch, which the
  risk engine respects.
- **D12-6 (security events):** material breaks are `security_events`
  of type `reconciliation_break`.
- **Order lifecycle (`order-lifecycle.md`):** SETTLED now requires a
  passing reconciliation. The transition authority (Journal Writer)
  must check the latest reconciliation status before transitioning.

## Phase boundary

- Binds Phase 8 (trading) to Phase 5 (storage: report artifacts,
  `fills`/`positions`) and Phase 11 (ops: scheduled job, alerting,
  on-call).
- Physical storage of reconciliation reports and `reconciliation_deltas`
  is Phase 5. This document fixes the contract and the break taxonomy.
- The reconciliation job code is Phase 14+.
- MT5 `HistoryOrders`/`HistoryDeals` field mapping is Phase 8 MT5
  integration detail, not redefined here.

## What this document does NOT define

- The reconciliation job implementation (Phase 14+).
- MT5 field-level mapping (Phase 8 `mt5-integration.md`).
- Numeric tolerance values (Phase 5 registry data; this doc fixes the
  shape).
- On-call rotation and paging tooling (Phase 11/14).
- Tax/regulatory reporting (out of V1 scope).

## Phase boundary

This document fixes the daily broker-reconciliation contract, the break
taxonomy, the auto-resolution rules, the escalation and break-age SLA,
the hash-pinned report artifact, and the SETTLED gate. It does not
define physical report storage (Phase 5), job code (Phase 14+), or
MT5 field mapping (Phase 8).
