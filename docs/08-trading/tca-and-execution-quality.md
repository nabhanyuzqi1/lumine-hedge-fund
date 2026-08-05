# TCA & Execution Quality

## Overview

`order-lifecycle.md` defines the order state machine and records
`slippage` on `fills` as `fill_price - expected_price`. But
`expected_price` is undefined, there is no aggregate execution-
quality analysis, no alerting on slippage breaches, and no feedback
loop from execution quality into strategy evaluation. Execution bleed
— the slow cost of poor fills — is invisible. This document fixes
the benchmark definition, the per-fill TCA record, aggregate rollups,
alerting, the strategy-evaluation feedback hook, and the best-
execution evidence role.

It amends `order-lifecycle.md` (Phase 8) and feeds strategy
promotion (governance, Phase 2).

## Decision: D8-4 — Arrival-mid benchmark, per-fill TCA, aggregate rollups

### Slippage benchmark = arrival mid at `decision_ts`

```
benchmark_price = arrival_mid_at(decision_ts)
slippage = fill_price - benchmark_price           (for BUY)
slippage = benchmark_price - fill_price           (for SELL)
slippage_bps = (slippage / benchmark_price) * 10000
```

The benchmark is the mid price at `decision_ts` — the moment the
decision was made (DB-authoritative, per `clock-and-time-contract.md`).
This is the arrival-price benchmark standard in institutional TCA.

### Session clamp

If `decision_ts` falls outside the session (market closed, blackout
deferral, or gap between sessions), the benchmark uses the **next-
session-open mid**:

```
if calendar.is_closed(symbol, decision_ts):
    benchmark_price = first_mid_after_session_open(symbol, decision_ts)
```

This ties to `market-calendar-contract.md`: the calendar determines
session boundaries, and the benchmark is clamped to the next open to
avoid using a stale last-tick from a previous session.

### Per-fill TCA record

A dedicated table stores TCA alongside `fills` (1:1):

```sql
CREATE TABLE tca_records (
  tca_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fill_id         UUID NOT NULL REFERENCES fills(fill_id),
  benchmark_price NUMERIC(20,5) NOT NULL,
  slippage_bps    NUMERIC(10,4) NOT NULL,
  slippage_cost_ccy NUMERIC(20,4) NOT NULL,     -- slippage * size * pip_value
  decision_ts     TIMESTAMPTZ NOT NULL,          -- copied from lineage for query convenience
  regime_id       regime_bucket NOT NULL,        -- regime at decision time (regime-model.md)
  broker_id       TEXT NOT NULL,
  account_id      TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (fill_id)
);
CREATE INDEX idx_tca_decision_ts ON tca_records (decision_ts);
CREATE INDEX idx_tca_broker_ts   ON tca_records (broker_id, decision_ts);
CREATE INDEX idx_tca_strategy_ts ON tca_records (strategy_id, decision_ts);
```

`regime_id` and `broker_id` enable slicing execution quality by
regime (does the strategy bleed in high-vol?) and by broker (is one
MT5 bridge consistently worse?).

### Aggregate TCA rollups

Materialized views aggregate TCA daily/weekly/monthly:

| Rollup | Dimensions | Metrics |
|--------|-----------|---------|
| `tca_daily_strategy` | strategy_id, date | avg_bps, p50_bps, p95_bps, total_cost_ccy, fill_count |
| `tca_daily_broker` | broker_id, date | same |
| `tca_daily_symbol` | symbol, date | same |
| `tca_daily_regime` | regime_id, date | same |
| `tca_daily_session` | session, date | same |

Weekly and monthly views aggregate from daily. Rollups are refreshed
on a schedule (Phase 11) and are the input to execution-quality
dashboards (Phase 10) and strategy review.

### Execution-quality alerts

```
if slippage_bps > threshold(symbol, regime):
    alert: slippage_breach
        { fill_id, strategy_id, broker_id, regime_id, slippage_bps, threshold }

if count(slippage_breach for strategy_id in last N fills) > cluster_limit:
    page: slippage_cluster
```

Thresholds are per-symbol, per-regime policy (e.g. 5 bps on XAUUSD
in normal regimes, 10 bps in high_vol). A single breach alerts; a
cluster pages — the distinction prevents alert fatigue while catching
systematic degradation.

### TCA feeds strategy evaluation

Strategy promotion/demotion (`governance-and-cross-department.md`
closed learning loop) uses **slippage-adjusted Sharpe**:

```
raw_return = realized_pnl
slippage_adjusted_return = raw_return - total_slippage_cost
adjusted_sharpe = sharpe(slippage_adjusted_return_series)
```

A strategy with attractive raw Sharpe but poor TCA is not promoted —
its edge is consumed by execution bleed. The Review worker consumes
`tca_daily_strategy` to compute adjusted Sharpe and flags strategies
where `adjusted_sharpe < promotion_threshold`.

### Best-execution evidence

TCA records and aggregate rollups serve as the regulatory best-
execution evidence record, in the spirit of MiFID II Best Execution
and SEC Rule 605/606. They are retained permanently (like
`lineage_records` and `fills`) and are queryable for regulatory
review. The record answers: at what benchmark, in what regime,
through which broker, with what slippage, was each fill executed?

### Benchmark integrity

The arrival mid is sourced from the **same market-data feed** used
by the feature store at `decision_ts` — point-in-time from the
feature store, not a re-computed or forward-filled value. This
guarantees the benchmark is the price the decision actually saw, not
a reconstruction. If the feature store lacks a mid at `decision_ts`
(gap), the session-clamp rule above applies and the gap is recorded
as `benchmark_source: "session_open"` rather than
`"arrival_mid"`.

## What this document does NOT define

- MT5 bridge fill-report parsing (Phase 8 `mt5-integration.md`).
- Materialized-view refresh schedule (Phase 11).
- Dashboard rendering (Phase 10).
- Alert routing infrastructure (Phase 11/12).
- Code (Phase 14+).

## Phase boundary

This document amends `order-lifecycle.md` (Phase 8) by defining the
slippage benchmark (arrival mid, session-clamped) and adding the
`tca_records` table. It feeds strategy promotion (governance, Phase 2)
via slippage-adjusted Sharpe. It does not define MT5 parsing,
dashboard code, or alert infrastructure.
