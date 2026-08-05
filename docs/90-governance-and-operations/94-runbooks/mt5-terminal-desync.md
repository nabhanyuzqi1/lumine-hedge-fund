# Runbook — MT5 Terminal Desync (P1)

- **Status:** active · **Drilled:** no
- **Owner:** execution
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

## Symptoms
- Internal `positions`/`fills` diverge from MT5 terminal state.
- Reconciliation reports `position_mismatch` or `qty_mismatch`.

## Steps
1. Halt dispatch.
2. Pull authoritative state from MT5 (`AccountInfo`, `HistoryOrders`).
3. Compare to internal `positions`/`fills`.
4. Resolve per `reconciliation-break.md` taxonomy.
5. If a fill was missed: backfill via `lineage_id` match; never fabricate
   a fill — if no lineage exists, treat as a reconciliation break and
   investigate.
6. Resume after reconciliation passes.
