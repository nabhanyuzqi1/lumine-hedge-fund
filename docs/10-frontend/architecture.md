# Frontend Architecture

## Overview

Stack, information architecture, routing, and realtime state model for
the Lumine operator dashboard. Consumes Phase 9 contracts
(`rest-api.md`, `sse-api.md`, `error-contract.md`).

## Stack (D10-1)

| Concern | Choice |
|---------|--------|
| Framework | React 18 SPA |
| Build | Vite |
| Routing | React Router |
| Server state (REST) | TanStack Query (D10-3) |
| Stream state (SSE) | Zustand, one store per stream (D10-3) |
| Price charts | lightweight-charts (D10-4) |
| Institutional charts | Apache ECharts (D10-4) |
| Dense tables | ag-Grid (virtualized, delta updates) |
| Layout grid | resizable split-pane/grid |
| Auth | HMAC-SHA256 signing client per Phase 9 `auth.md` (key + secret held by operator; signs every request with `X-Lumine-API-Key` / `X-Lumine-Timestamp` / `X-Lumine-Signature`) |

## Information architecture (D10-2)

Hybrid: one terminal for continuous monitoring + dedicated detail
pages for investigation.

### Routes

| Route | Page | Data sources |
|-------|------|--------------|
| `/` | Terminal (default) | All 6 SSE streams + REST polling panes |
| `/orders/:orderId` | Order Detail | `GET /orders/{id}` + SSE execution-orders (symbol filter) |
| `/workflows/:workflowId/runs/:runId` | Workflow Run Detail | REST run + journal + SSE analyst-outputs / ic-decisions / cio-proposals (`workflow_run_id` filter) |
| `/lineage/:lineageId` | Lineage Detail | `GET /lineage/{id}` (full proposal JSONB) |
| `/journal` | Journal | `GET /journal` (cursor pagination, filters) |
| `/admin/keys` | API Key Admin | admin domain REST (`POST/GET/DELETE /admin/keys`) |

### Terminal layout (`/`)

```
┌──────────────────────────────────────────────────────────────┐
│ TopBar: kill-switch | UTC clock | stream health | key scope  │
├────────┬───────────────────────────────────┬─────────────────┤
│ Rail   │  Main pane grid (resizable):      │  Right panel:   │
│ nav    │   PriceChart + QuotePanel         │   CommitteeFeed │
│ (work- │   Positions/Orders (ag-Grid)      │   ActivityLog   │
│ space) │   RiskGauges                      │                 │
└────────┴───────────────────────────────────┴─────────────────┘
```

- **Rail**: workspace switcher (Trading / Research / Risk / Ops).
  Switching rearranges panes only — no route change, SSE connections
  persist.
- **Main grid**: resizable panes — price chart, quotes, positions and
  orders tables, risk gauges.
- **Right panel**: `CommitteeFeed` (merged analyst → IC → CIO streams)
  and `ActivityLog` (errors with trace_id, gap events, kill-switch
  events).
- **TopBar**: global indicators — kill-switch status (red pulsing when
  active), UTC clock, aggregate stream health (n/6 live), API key
  scope identity.

### Detail pages

Full-page investigation views, deep-linkable, opened from terminal
rows/cards:

- Order lifecycle timeline (Phase 8 state machine visualization).
- Workflow run: 12-progress + 4-terminal state stepper (Phase 7),
  committee trace, journal.
- Lineage: proposal JSONB tree viewer with override badge.

## Realtime state architecture (D10-3)

**Rule: streaming data → Zustand; request-response → TanStack Query.
Never duplicate state into components.**

### SSE side

- `StreamProvider` + `useStream(streamName, filters)` hook owns the
  `EventSource` lifecycle per stream: connect, `Last-Event-ID`
  reconnect, backoff 1s→2s→4s→8s→max 30s (per sse-api.md), no
  reconnect on 401/403/404, honor `Retry-After` on 429.
- One connection per stream, shared by all panes (subscription
  multiplexing in the store, not multiple EventSources).
- Stores: `marketStore`, `ordersStore`, `committeeStore`,
  `riskStore`. Committee store merges 3 streams into one timeline.
- Each store keeps a ring buffer (max 1000 events — aligned with the
  Phase 9 replay/buffer semantics); committee feed trimmed to last 500
  entries.
- Lifecycle events handled per sse-api.md: `stream_open`,
  `stream_resumed` (sets `gap_detected` flag → `GapBanner`),
  `stream_error` (terminal → status), `stream_closed`,
  `stream_dropped` (→ ActivityLog + reconnect).
- Freshness: `now - meta.timestamp > 2 × heartbeat_interval` → store
  marks stream `stale` → pane shows degraded indicator.

### REST side

- TanStack Query for all request-response data: quotes, features,
  signals (polling with `refetchInterval`), journal, lineage, orders
  list/detail, admin keys.
- Mutations (`POST /orders`, `DELETE /orders/{id}`,
  `POST /rpc/kill-switch`, `POST /rpc/trigger-workflow`,
  `POST /rpc/override-proposal`, admin key ops) via Query mutations
  with automatic `Idempotency-Key` generation per write.
- Idempotent replay: `meta.idempotent_replay: true` → info toast
  ("response replayed — operation already completed"), treated as
  success per error-contract.md.
- Errors map to the Phase 9 error envelope; every error logs
  `trace_id` to ActivityLog.

### Render discipline

- Components subscribe via granular selectors; one market tick touches
  only components bound to the changed fields.
- ag-Grid receives delta transactions per event, never full `setData`.
- PriceChart appends candles incrementally; no full series rebuild.

## Auth & request signing

- API key + secret configured by the operator (settings screen, stored
  locally). Every REST call and SSE connection signed per Phase 9
  `auth.md` HMAC scheme.
- 401 on REST → auth-config screen (key missing/invalid/revoked). 401
  on SSE → no reconnect (sse-api.md rule) → auth screen.
- 403 `INSUFFICIENT_SCOPE` → pane-level notice listing
  `details.required_scopes`.

## What this document does NOT define

- Component implementations (Phase 14+).
- Visual theme values (design-tokens.md fixes structure, not palette).
- SSE handler/backend implementation (Phase 14+).
- Hosting/CDN for the bundle (Phase 11).

## Phase boundary

This document fixes the stack, IA, routing, and realtime state model.
It does not define implementation or backend concerns.
