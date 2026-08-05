# Clock & Time Synchronization Contract

## Overview

No phase currently fixes how clocks agree across trade-core, the MT5
bridge, Redis, Postgres, and the LLM gateway. In isolation each host
drifts; on the critical path, a 200 ms skew between the bridge wall
clock and trade-core turns `decision_ts` ordering into noise and makes
reconciliation false-positive. This document fixes the synchronization
budget, the authoritative time source, dual timestamps on fills, skew
rejection, monotonic-vs-wall-clock separation, and the UTC-everywhere
rule.

Phase 11 owns runtime delivery; clock discipline is infrastructure.
Phase 7 (workflow lifecycle) and Phase 8 (trading) consume the
contract.

## Decision: D11-6 — Single authoritative clock, 50 ms skew budget

### Synchronization

Every host in the critical path (trade-core, MT5 bridge, Redis,
Postgres, LLM gateway) runs chrony (or equivalent NTP) against a
documented upstream — a GPS-backed stratum-1 source or a cloud time
service (e.g. AWS Time Sync Service). The upstream is named in the
deployment manifest, not guessed.

### Skew budget

Max allowable skew within the critical path: **50 ms**. This is the
budget that keeps `decision_ts` ordering and fill-time reconciliation
meaningful at intraday latency. Anything wider is a break, not a
tolerance.

### Authority

Postgres is the clock authority for critical-path timestamps.
`decision_ts` on `lineage_records` is written as
`transaction_timestamp()` (alias `now()`) inside the blocking ACID
insert — not a host-side wall clock passed in by trade-core. This
guarantees:

- one time source for every decision timestamp;
- the timestamp is transaction-consistent with the row commit;
- no cross-host drift can corrupt ordering, because the DB assigns it.

Host-side wall clocks are still used for non-authoritative fields
(see dual timestamps below), but the canonical decision time is DB-
assigned.

## Dual timestamps on fills

Bridge fills carry BOTH:

| Column | Source | Meaning |
|--------|--------|---------|
| `bridge_ts` | bridge-side wall clock (UTC) | when the bridge observed the fill from MT5 |
| `ingest_ts` | listener-side wall clock (UTC) | when the trade-core listener ingested the event |

Both are stored on `fills` (amend `positions-fills-schema.md`). The
existing `ts` column is retained as the canonical fill time for
ledger queries and is set to `ingest_ts` by default; `bridge_ts` is
the cross-check field.

## Skew rejection

For every fill, compute `skew = |bridge_ts - ingest_ts|`:

```
if skew > 50ms_budget:
    REJECT the event (do not silently accept)
    raise alert: clock_skew_breach
        { lineage_id, bridge_ts, ingest_ts, skew_ms, broker_id }
    route through reconciliation as a break type
```

Silent acceptance of skewed events would corrupt the ledger and mask
bridge/MT5 clock drift — violations of principles #4 and #10. Reject
and alert; never absorb.

## Monotonic vs wall clock

| Use | Clock | Why |
|-----|-------|-----|
| Timestamps stored in DB / logs / lineage | wall clock (UTC) | comparable across hosts, replayable, queryable |
| Duration / latency measurement (stage timing, call elapsed) | `CLOCK_MONOTONIC` | immune to NTP step adjustments; never goes backwards |

Stage-latency instrumentation in Phase 7 (`workflow-lifecycle.md`
per-state deadlines) measures elapsed time with the monotonic clock
and reports it as a duration, never as a wall-clock difference. Wall-
clock subtraction is forbidden for latency math — NTP slews can make
durations negative or misleading.

## UTC everywhere

- All stored timestamps are UTC. `TIMESTAMPTZ` columns store UTC
  internally; no `TIMESTAMP WITHOUT TIME ZONE` on the critical path.
- All log lines emit UTC ISO-8601 with explicit `Z`.
- No local time, no DST conversion in storage or logs. Internal
  services never call `localtime()`.
- Display layers (Phase 10 frontend, operator dashboards) convert to
  the viewer's timezone at render time only; the stored value is
  always UTC.

## DST handling

DST is irrelevant internally because every stored value is UTC.
Market-session shifts (e.g. London/NY sessions moving by an hour
twice a year) are handled by the market-session calendar
(`market-calendar-contract.md`), which encodes IANA timezone rules
and emits session windows in UTC. Clock discipline here never
hardcodes an offset.

## Reconciliation detects residual skew

`reconciliation.md` (Phase 8) treats residual clock skew as a first-
class break type: if a fill's `bridge_ts` and `ingest_ts` disagree
within the 50 ms budget but the cumulative drift across a session is
monotonic and trending, reconciliation flags it as `clock_drift_trend`
for operator review before it breaches the hard 50 ms gate. This
catches slow drift early rather than waiting for a hard reject.

## What this document does NOT define

- chrony configuration file contents (Phase 11 ops runbook).
- LLM gateway internal clock discipline — the gateway is a consumer;
  its timestamps are not authoritative and are not stored as
  `decision_ts`.
- Display-timezone selection logic (Phase 10).
- Market-session calendar rules (`market-calendar-contract.md`,
  Phase 3/5 amendment).

## Phase boundary

This document fixes the synchronization budget, the authoritative
clock (Postgres), dual fill timestamps, skew rejection, monotonic-vs-
wall-clock separation, and UTC-everywhere. It is Phase 11
infrastructure consumed by Phase 7 (lifecycle deadlines, latency
measurement) and Phase 8 (fill timestamps, reconciliation). It does
not define the market calendar (separate contract) or ops runbook
details.
