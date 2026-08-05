# ADR-0035 — Clock synchronization and temporal-ordering contract

- **Status:** Accepted
- **Phase:** 11-infrastructure
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

No phase currently fixes how clocks agree across trade-core, the MT5
bridge, Redis, Postgres, and the LLM gateway. In isolation each host
drifts; on the critical path, a 200 ms skew between the bridge wall clock
and trade-core turns `decision_ts` ordering into noise and makes
reconciliation false-positive. Silent acceptance of skewed events would
corrupt the ledger and mask bridge/MT5 clock drift.

## Decision

Every host in the critical path runs chrony (or equivalent NTP) against a
documented stratum-1 or cloud time source. Max allowable skew: 50 ms.
Postgres is the clock authority for critical-path timestamps —
`decision_ts` is written as `transaction_timestamp()` inside the blocking
ACID insert, not a host-side wall clock. Fills carry dual timestamps
(`bridge_ts`, `ingest_ts`); skew > 50 ms rejects the event and alerts.
Latency measurement uses `CLOCK_MONOTONIC`, never wall-clock subtraction.
All stored timestamps are UTC; no local time or DST conversion in storage
or logs.

## Rationale

- One time source for every decision timestamp (Postgres) guarantees
  transaction-consistent, cross-host-comparable ordering.
- 50 ms budget keeps `decision_ts` ordering and fill-time reconciliation
  meaningful at intraday latency.
- Rejecting skewed events prevents ledger corruption (principles #4, #10).
- Monotonic clock for latency math is immune to NTP step adjustments —
  never goes backwards.
- UTC everywhere eliminates DST ambiguity in storage and logs.

## Consequences

- Positive: `decision_ts` ordering is authoritative and cross-host
  consistent.
- Positive: clock drift is caught early (reconciliation flags
  `clock_drift_trend` before the hard 50 ms gate).
- Negative: a chrony misconfiguration halts the pipeline (safe state).
- Reversibility: the 50 ms budget is policy; the UTC-everywhere rule is
  structural.

## Cross-references

- Related ADRs: ADR-0014, ADR-0021, ADR-0037
- Implements principle(s): #4, #10
- Affects phases: 11, 07, 08
- Source document: `../11-infrastructure/clock-and-time-contract.md` (S13)
