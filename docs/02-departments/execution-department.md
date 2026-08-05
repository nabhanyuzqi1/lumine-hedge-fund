# Execution Department (Deterministic + MT5 Bridge)

## Overview

The Execution Department spans two zones: the ExecutionRouter sub-module
inside trade-core (Zone 1, in-proc sync) and the MT5 Bridge (Zone 2, isolated
process). The router dispatches; the bridge is the sole holder of the MT5 API.

This document fixes the execution flow, reconciliation, broker-side SL/TP
safety net, and reconnect isolation. It does not define the MT5 protocol,
payload field definitions, or code.

## Components

```
ExecutionRouter (Zone 1, sub-module of trade-core)
  - input:  sized order from PortfolioSizer
  - lineage write (blocking, ACID) — MUST succeed before dispatch
  - output: publish to mt5.commands stream (Redis)
       ↓ Redis stream
MT5 Bridge (Zone 2, isolated process)
  - consume mt5.commands
  - call MT5 API (order submit, SL/TP hard-set at entry)
  - emit fill / position events
       ↓ Redis stream
Trade-core Listener (Zone 1)
  - consume mt5.fills + mt5.positions
  - update position in PostgreSQL
  - compute slippage, compare vs expected
  - reconciliation drift check (target: zero)
```

## Execution flow

1. PortfolioSizer produces sized order + attribution tag.
2. ExecutionRouter writes lineage record (sync, blocking, ACID). If write
   fails → safe state, no dispatch.
3. ExecutionRouter publishes order to `mt5.commands` stream.
4. MT5 Bridge consumes command, submits to MT5 API with SL/TP hard-set.
5. Bridge emits fill event to `mt5.fills` and position sync to
   `mt5.positions`.
6. Trade-core listener consumes fill, updates PostgreSQL, runs reconciliation.

## Reconciliation flow (deterministic, critical)

```
order dispatched (lineage ID recorded)
     ↓
bridge submits to MT5 → fill event (price, size, commission, slippage)
     ↓
listener consumes fill:
  - match fill to lineage ID
  - update position in PostgreSQL (ACID)
  - compute slippage = fill_price − expected_price
  - if slippage > threshold → drift flag → review worker (async)
     ↓
position sync: bridge emits mt5.positions, listener reconciles vs PostgreSQL
  - if mismatch → drift flag, safe state per policy
```

Reconciliation target is zero drift. Any divergence between broker state and
PostgreSQL state is a drift flag, never silently accepted (principle #4:
evidence before capital; principle #10: safe state by default).

## Broker-side SL/TP as safety net

- SL/TP are submitted to MT5 at entry, together with the order.
- If the bridge or trade-core crashes, the broker still honors SL/TP → loss
  is capped.
- Engine-side management (breakeven, trailing) optimizes outcomes but is not
  safety-critical. Broker-side SL/TP is the safety net (Phase 1 invariant).

## Reconnect isolation

- MT5 reconnect logic is isolated inside the bridge. Trade-core remains safe.
- Bridge crash → trade-core detects stream timeout → safe state (no new
  entries, manage existing via broker-side SL/TP).
- Bridge resumes from last consumed stream offset. Command processing is
  idempotent: a replayed command must not produce a duplicate order.

## Authority

- **ExecutionRouter**: order dispatch only. Cannot bypass the lineage rule.
- **Bridge**: executes MT5 API calls only. Cannot initiate an order (only
  consumes `mt5.commands`).
- **Listener**: updates state + reconciliation. Cannot modify orders.
- No Execution component may override a Risk REJECT.

## Forbidden anti-patterns (Phase 1, reaffirmed)

- Trade-core calling the MT5 API directly (must go via bridge).
- Bridge initiating an order on its own (must consume `mt5.commands`).
- Lineage write performed async or non-blocking (must be sync, blocking,
  ACID, before dispatch).
- Batching lineage writes (one write per decision).

## Phase boundary

This document fixes the execution flow, reconciliation, and safety-net
invariants. It does not define:

- MT5 protocol details / API surface (Phase 8 — Broker Integration).
- Payload field definitions for `mt5.commands` / `mt5.fills` /
  `mt5.positions` (Phase 3).
- Idempotency key implementation (Phase 14+).
- Code (Phase 14+).
