# Phase 10 — Locked Decisions

## Decision log

| # | Decision | Rationale |
|---|----------|-----------|
| D10-1 | **React SPA + Vite** | The dashboard is a read-only institutional consumer (Phase 9 D9-1). No SSR/SEO requirement — all meaningful data arrives via SSE after load, not during initial render. Vite gives fast dev iteration and small production bundles. React has the most mature enterprise chart/table ecosystem (lightweight-charts, ECharts, ag-Grid). Next.js SSR adds server complexity with no benefit behind HMAC-authenticated operator access. |
| D10-2 | **Hybrid IA: single terminal + detail pages** | Operators monitor continuously — page switches must never drop SSE connections. The default route `/` is a multi-pane terminal aggregating all 6 streams. Deep investigation (single order, workflow run, lineage record) gets dedicated deep-linkable pages. Workspace views (Trading/Research/Risk/Ops) rearrange panes without routing, keeping streams alive. |
| D10-3 | **Zustand store per SSE stream + TanStack Query for REST** | Strict data-source separation: the 6 SSE streams each write to a dedicated Zustand store (market, orders, committee×3 merged feed, risk); REST request-response (quotes, features, signals, journal, lineage, admin) uses TanStack Query with staleTime/refetchInterval. Tick-frequency market updates bypass Query cache normalization which would be wasteful at 1/sec. Granular selectors prevent full-tree re-renders. |
| D10-4 | **lightweight-charts for price action + ECharts for institutional charts** | lightweight-charts (TradingView) is Canvas-based, appends ticks incrementally at 60fps, ~45KB gzip, and ships trading primitives (crosshair, price lines, order markers). ECharts covers gauges, equity/drawdown curves, exposure treemaps, and correlation heatmaps with a consistent declarative API. Best tool per domain rather than one compromised library. Full TradingView Charting Library deferred — commercial license and 1MB+ bundle are unjustified for XAUUSD-only V1 (upgrade path preserved). |

## Principles honored

- **#1 Architecture before code**: frontend contracts fixed; no components written.
- **#9 Replaceability**: chart library, state library, and transport are isolated behind hooks/stores — swappable without touching page architecture. WebSocket can replace SSE behind `useStream` without UI changes (Phase 9 D9-1 Port/Adapter).
- **#10 Safe state by default**: invalid auth stops at the auth screen; kill switch disables write actions visibly; stream degradation is always surfaced, never hidden.
- **Evidence before capital**: every committee reasoning step, decision, and risk verdict is streamed and inspectable; lineage is one click from any decision card.
- **Fail visible, not silent**: every API error (with trace_id), stream gap, and drop appears in the ActivityLog pane.

## Phase boundary respected

Phase 10 fixes frontend architecture: stack, IA, state model, token
structure, components, wireframes, and performance budgets. It does NOT
define: implementation (Phase 14+), backend concerns (Phase 9/11),
final visual theme values (locked at design-system execution with
specialist tooling), or payload schemas owned by Phases 4/7/8.
