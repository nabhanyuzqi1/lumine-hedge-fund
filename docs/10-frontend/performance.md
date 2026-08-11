# Performance Budget & Error Handling

## Overview

Measurable performance budgets and the error/degraded-state handling
contract for the dashboard. Error semantics map directly to Phase 9
`error-contract.md`; stream behavior to `sse-api.md`.

## Performance budgets

| Metric | Budget |
|--------|--------|
| Initial load (TTI) | < 2s; critical-path bundle < 300KB gzip; ECharts and ag-Grid lazy-loaded per pane |
| Tick render latency | SSE event → DOM update < 50ms |
| Frame rate | 60fps with all 6 streams active; incremental chart append, no layout thrash |
| Tables | ag-Grid virtualization; 60fps scroll at >10k rows; delta transactions only, never full `setData` |
| Re-render scope | Granular Zustand selectors; one market tick touches only components subscribed to changed fields |
| Memory | Ring buffer ≤ 1000 events per store (aligned with Phase 9 replay/buffer semantics); committee feed trimmed to last 500 entries |
| Long sessions | No EventSource leaks — cleanup on unmount; exactly one connection per stream, shared across panes |

## Chart runtime behavior

How chart panes uphold the budgets above. Implemented in F-Sprint 4
(`frontend/src/components/charts/`), driven by `docs/10-frontend/charts.md`.

| Concern | Contract |
|---------|----------|
| Tick batching | SSE ticks batch at 100ms per pane; the batch mutates only the last bar via `series.update()` — never a full `setData` rebuild. |
| Initial data | Full history via `setData` once per series at mount/timeframe switch. |
| Timeframe switch | Pure transform (`lib/chart-transform.ts`) → `setData`; no animation, no layout shift (fixed-height container). Budget < 150ms interaction. |
| Resize | One `ResizeObserver` per chart container; `chart.resize()` with explicit pixel dims; container fixed-height so no layout shift. |
| ECharts loading | Tree-shaken `echarts/core` imports + `React.lazy` per pane with skeleton fallback; critical bundle stays < 300KB gzip. |
| Theme | Semantic CSS variables mapped once in `lib/chart-theme.ts` (up/down/warn/danger/accent, tabular numerals). |
| Cleanup | `chart.remove()` / `dispose()` on unmount; `setOption(option, true)` (notMerge) on data change; no leaked instances in long sessions. |
| Demo mode | Deterministic fixtures (seeded PRNG) + 1s synthetic ticks when REST/SSE unavailable; identical code path to live data. |

## Surface runtime behavior

How F-Sprint 5 surfaces uphold the budgets above. Implemented in
`frontend/src/app/pages/`, `frontend/src/app/components/`, and
`frontend/src/components/terminal/`.

| Concern | Contract |
|---------|----------|
| Workspace rail | Pure `uiStore` state switch — no route change, no stream remount; stores persist across Trading/Research/Risk/Ops workspaces. |
| Terminal layout | Static grid of existing chart + table components; detail pages lazy-loaded so critical bundle stays < 300KB gzip. |
| Kill switch | One global flag in `uiStore`; write actions (Cancel Order, Revoke key, Create key) disabled via prop/tooltip while banner is active. |
| Committee feed | `committeeStore` trims to last 500 activities; detail pages filter by `workflow_run_id` without copying the buffer. |
| Activity log | Ring buffer ≤ 1000 entries per `activityStore`; detail filters by symbol/run id in render, not by mutating the buffer. |
| Tables | Positions/orders use existing virtualized `DataTable`; journal uses plain HTML table with 50-row cursor pagination (no virtualization needed for audit log). |
| Detail pages | `React.lazy` + Suspense skeleton; loaded only on navigation, keeping initial chunk under budget. |
| Demo mode | All detail hooks follow F-Sprint 3/4 fixture-fallback pattern (`try { get(...) } catch { return generateX() }`); deterministic seeds keep tests/screenshots reproducible. |

## Error & degraded-state handling

Mapping from Phase 9 error-contract.md and sse-api.md:

| Condition | UI behavior |
|-----------|-------------|
| `401` (REST or SSE) | Auth-config screen (key missing/invalid/revoked); SSE does not retry (sse-api.md rule). |
| `403 INSUFFICIENT_SCOPE` | Pane-level notice listing `details.required_scopes`. |
| `403 KILL_SWITCH_ACTIVE` | Global banner + toast; write actions disabled with explanatory tooltips. |
| `409 CONFLICT` (idempotency) | Dialog: "Key reused with different body — generate a new key." |
| `429 RATE_LIMITED` | Toast + honor `Retry-After` (header mirrors `details.retry_after`); action button disabled during countdown. |
| `5xx` / `DEGRADED_MODE` | Toast with `trace_id`; pane degraded status; SSE reconnects with backoff (DEGRADED_MODE may recover — sse-api.md). |
| `DUPLICATE_IDEMPOTENCY` (HTTP 200 replay) | Info toast: "Response replayed (idempotent) — operation already completed." Treated as success per error-contract.md. |
| SSE stale (`now - meta.timestamp > 2 × heartbeat`) | `StreamStatusDot` yellow + "stale" label on affected pane. |
| SSE `stream_dropped` / `gap_detected` | `GapBanner` on pane + ActivityLog entry; offer REST refetch to close the gap. |
| SSE `stream_error` (terminal) | Stream marked errored; reconnect policy by error code (no reconnect on 401/403/404). |
| REST query failure | TanStack Query retry 3× exponential backoff, then inline pane error state — never a page crash. |
| Every error | Logged to ActivityLog with `trace_id` (click to copy) — closes the loop with Phase 7 observability per error-contract.md traceability. |

## Accessibility & i18n

- `aria-live="polite"` on the kill-switch banner; assertive on
  stream-dropped alerts.
- All actions keyboard-reachable; ⌘K CommandPalette; visible focus
  rings (2px accent).
- AA contrast on the dark theme; directional colors always paired
  with non-color cues (arrows/signs).
- `prefers-reduced-motion` disables value-flash and non-essential
  animation.
- UI language: English (standard trading terminology).

## What this document does NOT define

- Profiling tooling and CI performance gates (Phase 13 testing
  strategy).
- Bundle hosting/compression (Phase 11).
- Implementation-level memoization tactics (Phase 14+).

## Phase boundary

Budgets and error-handling semantics are fixed here. Enforcement
tooling belongs to Phase 13; implementation to Phase 14+.
