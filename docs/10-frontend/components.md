# Component Catalog

## Overview

Core components grouped by domain. Each entry lists its data source
per Phase 9 contracts and its realtime behavior. Implementation
belongs to Phase 14+.

## A. Primitives (design system)

`Button` (primary/danger/ghost) · `Badge` (status pill) · `Tag`
(scope, tier) · `Tooltip` · `Dialog` (confirmations) · `Toast`
(non-modal notifications) · `Spinner` · `Skeleton` · `Kbd` (shortcut
hints) · `NumericText` (tabular mono, flash on change).

## B. Stream infrastructure

| Component | Behavior |
|-----------|----------|
| `StreamStatusDot` | Per-pane indicator: green live → yellow stale (>2× heartbeat, per sse-api.md freshness) → red blinking dropped/error → gray reconnecting. |
| `StreamProvider` / `useStream(name, filters)` | Owns EventSource lifecycle: `Last-Event-ID`, backoff 1→2→4→8→max 30s, no reconnect on 401/403/404, honor `Retry-After` on 429. Writes to Zustand store. One connection per stream, shared across panes. |
| `GapBanner` | Shown in pane when `stream_resumed` arrives with `gap_detected: true`: "Data missed during reconnect" + REST refetch action. |

## C. Market

| Component | Source | Realtime behavior |
|-----------|--------|-------------------|
| `PriceChart` | SSE market-data (symbol filter) | lightweight-charts candlestick + volume + order markers + price lines; incremental append per tick, never full rebuild. |
| `QuotePanel` | SSE market-data | Large tabular mono bid/ask/spread; 150ms flash on change. |
| `FeaturePanel` | `GET /market/features/{symbol}` | TanStack Query polling. |
| `SignalPanel` | `GET /market/signals/{symbol}` | TanStack Query polling. |

## D. Positions & orders

| Component | Source | Realtime behavior |
|-----------|--------|-------------------|
| `PositionsTable` | SSE execution-orders + `GET /portfolio/{id}/positions` | ag-Grid virtualized; delta transactions per event; columns: symbol, side, qty, entry, current, P&L (flash). |
| `OrdersTable` | SSE execution-orders + `GET /orders` | Virtualized; status Badge per Phase 8 lifecycle; row click → `/orders/:orderId`. |
| `OrderLifecycleTimeline` | `GET /orders/{id}` + SSE execution-orders | Phase 8 state machine visualization with per-state timestamps. |
| `CancelOrderButton` | `DELETE /orders/{id}` | Confirmation dialog → mutation with `Idempotency-Key`; 403 `KILL_SWITCH_ACTIVE` shown as explicit refusal message. |

## E. Committee (AI reasoning)

| Component | Source | Behavior |
|-----------|--------|----------|
| `CommitteeFeed` | SSE analyst-outputs + ic-decisions + cio-proposals | Unified timeline (analyst → IC → CIO), expandable entries; `workflow_run_id` filter. |
| `AnalystCard` | analyst-outputs stream | Analyst output (technical / macro / news / SMC) with confidence meter. |
| `DecisionCard` | ic-decisions / cio-proposals streams | IC decision + CIO proposal; click → `/lineage/:lineageId` or run detail. |

## F. Risk

| Component | Source | Behavior |
|-----------|--------|----------|
| `RiskGaugePanel` | SSE risk-assessments | ECharts gauges: exposure, drawdown, margin. |
| `KillSwitchBanner` | stream events + 403 responses | Global red banner when engaged: reason + tier (global/book/strategy per Phase 2 D2-5 body). |
| `KillSwitchButton` | `POST /rpc/kill-switch` | Two-step confirmation dialog with reason input + tier selector. |

## G. Workflows & lineage

| Component | Source | Behavior |
|-----------|--------|----------|
| `WorkflowRunList` | `GET /workflows/{id}/runs` | Paginated run history. |
| `RunStatusBadge` | run data | 12 progress + 4 terminal states (Phase 7 lifecycle); KILLED shown danger. |
| `RunStepper` | run data + journal | 12-state progress stepper with current state marker. |
| `LineageViewer` | `GET /lineage/{id}` | Proposal JSONB tree viewer (expand/collapse, search, copy path); override badge when manual override present. |

## H. Journal

| Component | Source | Behavior |
|-----------|--------|----------|
| `JournalTable` | `GET /journal` | Cursor-paginated; filters symbol/portfolio/date range; read-only. |

## I. Admin

| Component | Source | Behavior |
|-----------|--------|----------|
| `ApiKeyTable` | `GET /admin/keys` | Masked keys, scope Tags, last-used; revoke with confirmation (`DELETE /admin/keys/{id}`). |
| `CreateKeyModal` | `POST /admin/keys` | Secret displayed once with copy; never retrievable again (per rest-api.md). |

## J. Global

| Component | Behavior |
|-----------|--------|
| `TopBar` | Kill-switch status, UTC clock, aggregate stream health (n/6), key scope identity. |
| `ActivityLog` | Error entries with `trace_id` (click to copy), gap events, kill-switch events, 429 warnings. |
| `CommandPalette` (⌘K) | Fast navigation to specific order / run / lineage / page. |

## Destructive-action rule

Kill switch, order cancel, key revoke, and proposal override always
require explicit confirmation dialogs stating impact. Write actions
are disabled with explanatory tooltips while `KILL_SWITCH_ACTIVE` is
in effect (403 is intentional refusal, not unavailability —
error-contract.md).

## What this document does NOT define

- Component implementations (Phase 14+).
- Visual styling values (design-tokens.md).
- Payload field schemas (owned by Phases 4/7/8; Phase 9 exposes them).

## Phase boundary

The catalog fixes component responsibilities, data sources, and
realtime behavior. Implementation is Phase 14+.
