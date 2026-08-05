# Runbook — Broker Slippage Spike (P1)

- **Status:** active · **Drilled:** no
- **Owner:** execution / cio
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

## Trigger
TCA alert: slippage > threshold (e.g. 5 bps on XAUUSD) sustained over N
fills, or a single fill > 2× threshold (ADR-0040).

## Steps
1. Inspect the TCA records: which symbol, broker, account, regime, session?
2. Check market context: news event (consult `market-calendar-contract.md`
   blackout windows), low-liquidity session, regime change.
3. If a regime shift: confirm the regime classifier updated; strategies
   incompatible with the new regime should be blocked (ADR-0034).
4. If broker-side: consider routing reduction or halt for that broker
   (`multi-broker-model.md` ADR-0024); consult CIO.
5. If strategy-side: the strategy's slippage-adjusted Sharpe may now breach
   the promotion/demotion gate (ADR-0031) → demotion review.
6. Resume normal routing only after cause is understood.

## Best-exec evidence
TCA records are the regulatory best-exec evidence; preserve them.
