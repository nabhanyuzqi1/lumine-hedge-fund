# Runbook — MT5 Bridge Disconnection (P1)

- **Status:** active · **Drilled:** no
- **Owner:** execution / devops
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

## Symptoms
- Bridge heartbeat stale; `mt5.fills` / `mt5.positions` streams silent.
- ExecutionRouter reports dispatch failures.

## First actions
1. Halt new dispatches: ExecutionRouter stops publishing `mt5.commands`
   while the bridge is down. The blocking lineage gate still records
   decisions, but dispatch is held (safe state by default — principle #10).
2. Check for open exposure (see `mt5-reconnect-open-position.md` if any).
3. Do NOT engage the global kill switch unless capital is at risk; a
   bridge outage alone is P1, not P0.

## Recovery
1. Identify cause: network, broker maintenance, terminal crash.
2. Restart the bridge; verify terminal sync (`mt5-terminal-desync.md`).
3. Reconcile: any commands sent but unconfirmed must be matched against
   broker state on reconnect (idempotency via `processed_commands`,
   `lineage_id`).
4. Resume dispatch only after reconciliation passes.

## Broker maintenance windows
- Consult `market-calendar-contract.md` for scheduled maintenance; suppress
  dispatch during known windows.
