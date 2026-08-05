# ADR-0040 — TCA and execution-quality reporting

- **Status:** Accepted
- **Phase:** 08-trading
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

`order-lifecycle.md` defines the order state machine and records
`slippage` on `fills` as `fill_price - expected_price`. But
`expected_price` is undefined, there is no aggregate execution-quality
analysis, no alerting on slippage breaches, and no feedback loop from
execution quality into strategy evaluation. Execution bleed — the slow
cost of poor fills — is invisible.

## Decision

The slippage benchmark is the arrival mid at `decision_ts` (DB-authoritative),
session-clamped to the next-session-open mid if the market is closed. A
`tca_records` table stores per-fill TCA (1:1 with `fills`): benchmark
price, slippage in bps, slippage cost in account currency, `regime_id`,
`broker_id`, `account_id`. Aggregate materialized views roll up daily by
strategy, broker, symbol, regime, and session. Execution-quality alerts
fire on per-fill threshold breach (per-symbol, per-regime policy) and
cluster pages on systematic degradation. TCA feeds strategy evaluation via
slippage-adjusted Sharpe. TCA records serve as regulatory best-execution
evidence (MiFID II / SEC Rule 605/606 spirit), retained permanently.

## Rationale

- Arrival-mid at `decision_ts` is the institutional TCA standard — the
  price the decision actually saw, sourced from the same market-data feed
  as the feature store.
- Aggregate rollups by regime and broker expose whether a strategy bleeds
  in high-vol or through a specific MT5 bridge.
- Slippage-adjusted Sharpe prevents a strategy with attractive raw Sharpe
  but poor TCA from being promoted.
- Permanent retention provides regulatory best-execution evidence.

## Consequences

- Positive: execution bleed is visible and alertable.
- Positive: strategy promotion accounts for execution cost (slippage-
  adjusted Sharpe).
- Positive: best-execution evidence is queryable for regulatory review.
- Negative: TCA computation adds a post-fill processing step.
- Reversibility: thresholds are policy; the benchmark definition is
  structural.

## Cross-references

- Related ADRs: ADR-0021, ADR-0024, ADR-0031, ADR-0034
- Implements principle(s): #4, #10
- Affects phases: 08, 05, 11
- Source document: `../08-trading/tca-and-execution-quality.md` (S19)
