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
