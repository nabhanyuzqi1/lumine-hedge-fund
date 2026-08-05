# Runbook — Reconciliation Break (P0/P1)

- **Status:** active · **Drilled:** no
- **Owner:** execution / cio
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

## Trigger
Daily reconciliation (`docs/08-trading/reconciliation.md`, ADR-0021) reports
a break between internal `positions`/`fills` and the broker statement.

## Severity
- `position_mismatch` or any break > $X → P0.
- `qty_mismatch`/`price_mismatch` < $X, latency-driven → P1 (often auto-resolves).
- `swap_mismatch` → P2 (usually timing).

## Break taxonomy & resolution
| Break type | Likely cause | Auto-resolve? |
|------------|--------------|---------------|
| missing_fill | fill not yet ingested (latency) | yes, within SLA |
| qty_mismatch | partial fill not recorded | no — investigate |
| price_mismatch | slippage recording error | no — investigate |
| position_mismatch | missed close/open, corporate action | no — P0 |
| swap_mismatch | swap timing | yes, usually |
| corporate_action_missing | missed dividend/split | no — P1 |

## Steps
1. Halt dispatch for the affected account if P0.
2. Pull the broker statement again; confirm the break is real (not latency).
3. Match each break to a `lineage_id`. If no lineage exists for a broker
   fill, that's a P0 — investigate unauthorized trading or ingestion bug.
4. Resolve: backfill missing fills via lineage match; never fabricate.
5. Reconcile must pass before SETTLED state (ADR-0021) and before resuming.

## Break-age SLA
- >1 day unresolved → page.
- >3 days unresolved → escalate to CIO.
- A position cannot reach SETTLED with an open break.
