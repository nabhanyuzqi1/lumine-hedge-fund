# Runbook — MT5 Reconnect with Open Position (P0)

- **Status:** active · **Drilled:** no
- **Owner:** execution / cio
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

## Why P0
An open position during a bridge outage is unmonitored exposure. Price can
move against the position with no stop-loss enforcement from Lumine. (MT5
broker-side SL/TP remain in effect if placed.)

## Steps
1. **Engage kill switch** if the outage is prolonged or the position is
   large relative to risk limits. CIO authority (ADR-0010).
2. **Verify broker-side SL/TP** are in place for the open position (these
   live on the broker, independent of Lumine's connection).
3. **On reconnect:** reconcile internal `positions` against broker state
   before resuming (see `reconciliation-break.md` if mismatch).
4. **Check for missed fills / partial fills** that occurred during the
   outage; match by `lineage_id`.
5. **Resume** only after reconciliation passes and the position's risk
   envelope is within limits.

## Never
- Never resume dispatch with an unreconciled open position.
- Never clear the kill switch autonomously.
