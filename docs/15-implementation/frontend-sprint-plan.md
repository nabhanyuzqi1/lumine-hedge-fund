# Frontend Sprint Plan

- **Status:** draft
- **Owner:** frontend
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

Phase 10 locked the frontend stack (React, Vite, Tailwind, Motion, shadcn/ui,
TanStack Query, Zustand, lightweight-charts, ECharts, SSE). This document
sequences frontend implementation so the first PR bootstraps with
conventions, not chaos.

## Pre-conditions

- Phase 9 API contracts (`rest-api.md`, `sse-api.md`, `auth.md`) implemented
  or mocked.
- `docs/09-api/api-versioning.md` OpenAPI generation working.

## Sprints

### F-Sprint 1 — Scaffold (conventions before features)
- `package.json`, `vite.config.ts`, `tsconfig.json`, `eslint.config.js`,
  `prettier`, `tailwind.config.ts`, `postcss`.
- `src/main.tsx`, `src/app/` router shell, one route (`/health`).
- Design tokens from `docs/10-frontend/design-tokens.md` wired into Tailwind.
- CI `ci-frontend.yml` runs `lint`, `typecheck`, `build`, `test`.
- Output: empty-but-conventioned app deployed to a preview URL.

### F-Sprint 2 — Design system primitives
- shadcn/ui base components (Button, Card, Table, Badge, Dialog, Toast).
- Tabular-numerals typography; semantic color tokens.
- Accessibility baseline (focus rings, reduced-motion, contrast AA).
- Storybook or equivalent for component documentation per Phase 10 rule
  (purpose, variants, states, accessibility, motion, performance, testing).

### F-Sprint 3 — Realtime data layer
- SSE client (`sse-api.md` contract); reconnection/backoff.
- TanStack Query for REST; Zustand for realtime client state.
- Virtualized table for positions/orders (Phase 10 perf budget).

### F-Sprint 4 — Financial visualization
- lightweight-charts: candlestick, equity, drawdown.
- ECharts: exposure, allocation, correlation, agent votes, P&L.
- 60 FPS target; chart optimization per Phase 10.
- **Status: implemented 2026-08-11** — local gate PASS + independent
  verification PASS, evidence in `sprint-evidence/f-sprint-4-charts.md`.
  Approval gate pending before F-Sprint 5.

### F-Sprint 5 — Surfaces
- Portfolio, risk, positions, execution, AI committee, market intelligence,
  strategy performance, research/backtesting, paper/production operations,
  model & LLM cost, infrastructure & memory health, journal, prompt history,
  audit logs (per Phase 10 wireframes).

### F-Sprint 6 — Keyboard, responsive, a11y, performance
- Command palette, keyboard model, focus visibility.
- Lighthouse / Web Vitals budgets enforced in CI.

## Boundaries

- Frontend consumes Phase 9 contracts; it does not redefine them.
- Frontend does not own data persistence (Phase 5) or transport (Phase 9).
- All financial math is backend-authoritative; frontend only renders.
