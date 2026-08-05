# Phase 10 — Frontend Architecture

## Overview

Phase 10 defines the frontend architecture for the Lumine operator
dashboard. It consumes the Phase 9 API contracts (REST + SSE), the
Phase 8 order lifecycle, and the Phase 7 workflow lifecycle. It
produces the UI architecture consumed by Phase 14+ implementation.

Phase 10 does NOT write code. It fixes the frontend contract surface:
stack, information architecture, realtime state model, design token
structure, component catalog, wireframes, and performance budgets.

## Documents in this folder

| File | Purpose |
|------|---------|
| `decisions.md` | Locked Phase 10 decision log |
| `architecture.md` | Stack, IA, routing, realtime state architecture |
| `design-tokens.md` | Token structure, semantics, typography, density, motion |
| `components.md` | Component catalog with data sources and realtime behavior |
| `wireframes.md` | Layout wireframes per page |
| `performance.md` | Performance budgets and error/degraded handling |

## Decisions at a glance

| # | Decision | Rationale |
|---|----------|-----------|
| D10-1 | **React SPA + Vite** | Dashboard is read-only institutional consumer (D9-1); no SSR/SEO need; data arrives via SSE not initial render; small fast bundle. |
| D10-2 | **Hybrid IA: terminal + detail pages** | Single multi-pane terminal for continuous monitoring (SSE never interrupted); dedicated detail pages for deep investigation with deep-linking. |
| D10-3 | **Zustand per SSE stream + TanStack Query for REST** | Strict separation: streaming state = Zustand stores, request-response = Query cache. Tick-frequency updates bypass React cache normalization. |
| D10-4 | **lightweight-charts + ECharts** | TradingView lightweight-charts for price action (Canvas, 60fps tick append, ~45KB); ECharts for institutional charts (gauges, equity, exposure, heatmaps). Best tool per domain. |

## What Phase 10 does NOT define

- Component implementation or scaffolding (Phase 14+).
- Backend middleware, gateway, or SSE handler implementation (Phase 14+).
- Concrete visual theme values — final palette hex values locked during
  design-system execution with specialist design tooling; token
  *structure and semantics* are fixed here.
- Deployment/hosting of the frontend bundle (Phase 11).
- Payload schemas owned by other phases (Phase 4 proposals, Phase 7
  workflow runs, Phase 8 orders).

## Phase boundary

This phase fixes the frontend architecture contract. Implementation
(React components, store wiring, chart integration) belongs to
Phase 14+.
