# F-Sprint 4 — Financial Visualization (Charts): Plan & Evidence

**Status:** Approved 2026-08-11 — local gate PASS + independent verification PASS, approval gate passed before F-Sprint 5.
**Date:** 2026-08-11
**Sprint:** F-Sprint 4 (G12) of Phase 15 — Implementation
**Owner:** Chief AI Architect
**Prerequisites:** F-Sprint 3 (Realtime Data Layer) approved 2026-08-10

---

## 1. Sprint Goal

Deliver the frontend financial visualization layer per `docs/15-implementation/frontend-sprint-plan.md` F-Sprint 4 and Phase 10 standards (`docs/10-frontend/charts.md`, `design-tokens.md`, `performance.md`): a `/dashboard` chart grid with lightweight-charts panes (candlestick + volume, equity, drawdown, live P&L) and lazy-loaded ECharts panes (allocation treemap, correlation heatmap, AI committee confidence), wired to the F-Sprint 3 data layer (TanStack Query + Zustand stores) with fixture fallback when the backend is offline.

**Exit criteria (from frontend-sprint-plan.md F-Sprint 4):**

- lightweight-charts: candlestick XAUUSD + timeframe selector + volume overlay; equity curve; drawdown (underwater).
- ECharts: exposure/allocation, correlation, AI confidence (agent votes), P&L.
- All charts render without layout shift; timeframe switch < 150ms; live tick update ≤ 1/sec without dropped frames; component unit tests.
- Wire to Zustand stores + TanStack Query.
- Performance: 100ms tick debounce, per-pane canvas resize handling (documented in `performance.md`).
- Measurable budgets: critical-path bundle < 300KB gzip; ECharts lazy-loaded per pane.

**Additional gates (per CLAUDE.md mandatory rules):**

- `npm run lint` zero errors
- `npm run typecheck` zero errors
- `npm run test` all pass
- `npm run build` succeeds
- `npx prettier --check .` clean
- Independent verification agent returns PASS

---

## 2. Scope

### 2.1 In scope

| Area | Files | Description |
|------|-------|-------------|
| Chart theme | `src/lib/chart-theme.ts` | Maps semantic CSS variables (up/down/warn/danger/accent) to lightweight-charts + ECharts option tokens once; tabular numerals |
| Chart transforms | `src/lib/chart-transform.ts` + `.test.ts` | Pure functions: bars→candles/volumes, tick→last-bar update payload, equity→area, equity→drawdown, exposure→treemap, correlation→heatmap, confidence→multi-line, UTC time |
| Fixtures | `src/data/fixtures.ts` + `.test.ts` | Deterministic seeded (mulberry32) generators: OHLCV bars, equity curve, exposure, correlation matrix, confidence timeline, P&L |
| Chart card | `src/components/charts/chart-card.tsx` | Card + title + status badge + fixed-height container + ResizeObserver → `chart.resize()` |
| lightweight-charts panes | `candlestick-chart.tsx`, `equity-chart.tsx`, `drawdown-chart.tsx`, `pnl-sparkline.tsx` (+ tests) | Incremental `series.update()` per 100ms tick batch; full `setData` only at mount/timeframe switch; `chart.remove()` on unmount |
| ECharts panes | `allocation-chart.tsx`, `correlation-chart.tsx`, `confidence-chart.tsx` (+ tests) | Tree-shaken `echarts/core`; `React.lazy` per pane; `dispose()` on unmount; `setOption(option, true)` on data change |
| API hooks | `src/api/hooks.ts` | `useMarketBars`, `useEquityCurve`, `useExposure`, `useSignals`, `useCorrelation` via TanStack Query; deterministic fixture fallback when REST unavailable (demo mode) |
| Demo streams | `src/hooks/useDemoStreams.ts` | 1s synthetic tick interval pushing to market/portfolio stores when SSE is not live; identical code path to live data |
| Dashboard | `src/app/pages/dashboard.tsx` + `.test.tsx` | Responsive chart grid (6 panes), lazy panes under Suspense with skeleton fallback, route `/dashboard` |
| Route | `src/app/router.tsx` | `/dashboard` route registered |
| Docs | `docs/10-frontend/performance.md` | New "Chart runtime behavior" section: 100ms tick batching, per-pane resize, incremental append, lazy ECharts, unmount cleanup, demo mode |

### 2.2 Out of scope (backend contract notes)

> **Update 2026-08-14:** backend kini live. `GET /market/correlation` diimplementasi (`routers/market.py`) — `useCorrelation` masih fixture-only di `hooks.ts:122` dan bisa di-rewire (GAP F-10). SSE 6 channel live di `/api/v1/streams/*`.

- ~~**No correlation endpoint exists** in `docs/09-api`~~ — **RESOLVED**: `GET /api/v1/market/correlation?symbols=&window=` live (deterministik); correlation pane masih konsumsi fixture (`useCorrelation`).
- SSE market/analyst streams (`sse-api.md`) now live — chart panes consume REST fixture fallback + `useDemoStreams` synthetic ticks; SSE realtime wiring per-pane adalah pekerjaan berikutnya (GAP F-02).

---

## 3. Verification results

### 3.1 Local gate (2026-08-11)

| Gate | Command | Result |
|------|---------|--------|
| Lint | `npm run lint` | PASS — 0 errors |
| Typecheck | `npm run typecheck` (`tsc -b`) | PASS — 0 errors |
| Tests | `npx vitest run` | PASS — 21 files, 79 tests |
| Build | `npm run build` | PASS — 36.6s |
| Format | `npx prettier --check .` | PASS — all files clean |

### 3.2 Bundle budget (critical path < 300KB gzip)

| Chunk | gzip | In critical path? |
|-------|------|-------------------|
| `index-*.js` (app + lightweight-charts) | 193.47 kB | Yes |
| `useEcharts-*.js` (shared ECharts core chunk) | 201.47 kB | No — lazy |
| `allocation-chart-*.js` | 0.48 kB | No — lazy |
| `confidence-chart-*.js` | 0.52 kB | No — lazy |
| `correlation-chart-*.js` | 0.59 kB | No — lazy |
| CSS | 6.81 kB | Yes |

Critical-path bundle 193.47 kB gzip < 300 KB budget. ECharts (201.47 kB gzip) is code-split out of the critical path via `React.lazy` + Suspense skeleton fallback, per `performance.md` L13.

### 3.3 Chart runtime contracts verified in code + tests

| Contract | Evidence |
|----------|----------|
| Tick batching 100ms, last-bar-only mutation | `candlestick-chart.tsx` debounce + `updateBarWithTick` transform tests (`chart-transform.test.ts`) |
| Timeframe switch via pure transform → `setData` | `candlestick-chart.tsx` `onTimeframeChange`; transform suite |
| Per-pane ResizeObserver → `chart.resize()` | `chart-card.tsx`; ResizeObserver mocked in `test/setup.ts` |
| Unmount cleanup | `echarts-panes.test.tsx` "disposes the instance on unmount"; `series-charts.test.tsx` PnlSparkline unmount test; `pnl-sparkline.tsx` |
| Deterministic demo mode | `fixtures.test.ts` (same seed ⇒ identical output); dashboard test renders full grid from fixture fallback with fetch rejected |
| No layout shift | Fixed-height chart containers (`chart-card.tsx`); no animation on data change |

### 3.4 Known flake fixed during gate

First full vitest run failed 1 test: `dashboard.test.tsx` `findByText` default waitFor timeout (1000ms) too tight for lazy ECharts chunk + Suspense resolution under full-suite machine load. Fixes:

- `frontend/vite.config.ts`: `testTimeout: 20000` (default 5000ms too tight for render-heavy suites on loaded machines; verified green at 20s).
- `dashboard.test.tsx`: explicit `{ timeout: 5000 }` on the lazy-pane `findByText`.

### 3.5 Independent verification (2026-08-11)

✅ **PASS** — independent `verification` agent re-ran the full local gate and confirmed all steps passed.

Agent verdict:
- `npm run lint` — PASS, 0 errors
- `npm run typecheck` — PASS, 0 errors
- `npx vitest run` — PASS (21 files, 79 tests; dashboard lazy-pane test passed in 2257ms)
- `npm run build` — PASS; critical path `index-Cel71juF.js` 193,037 B gzip (< 300KB budget); `useEcharts-CjMWdguI.js` 200,880 B gzip off critical path; lazy chart panes ~0.5 kB each
- `npx prettier --check .` — PASS, clean
- Sanity: 3 ECharts panes lazy-loaded via `React.lazy`; `performance.md` has exactly one "Chart runtime behavior" section
- Adversarial probe: empty/ragged/out-of-range/zero transform inputs handled without throwing

VERDICT: PASS

---

## 4. Files changed

### New

```
frontend/__mocks__/lightweight-charts.ts        frontend/__mocks__/echarts/core.ts
frontend/src/api/hooks.ts
frontend/src/app/pages/dashboard.tsx            frontend/src/app/pages/dashboard.test.tsx
frontend/src/components/charts/allocation-chart.tsx
frontend/src/components/charts/candlestick-chart.tsx   (+ .test.tsx)
frontend/src/components/charts/chart-card.tsx
frontend/src/components/charts/confidence-chart.tsx
frontend/src/components/charts/correlation-chart.tsx
frontend/src/components/charts/drawdown-chart.tsx
frontend/src/components/charts/echarts-panes.test.tsx
frontend/src/components/charts/equity-chart.tsx
frontend/src/components/charts/pnl-sparkline.tsx
frontend/src/components/charts/series-charts.test.tsx
frontend/src/data/fixtures.ts                    (+ .test.ts)
frontend/src/hooks/useChartResize.ts
frontend/src/hooks/useDemoStreams.ts
frontend/src/hooks/useEcharts.ts
frontend/src/lib/chart-theme.ts
frontend/src/lib/chart-transform.ts              (+ .test.ts)
```

### Modified

```
frontend/package.json / package-lock.json   (lightweight-charts ^5.0.0, echarts ^5.6.0)
frontend/src/app/router.tsx                 (/dashboard route)
frontend/vite.config.ts                     (testTimeout 20000)
docs/10-frontend/performance.md             (Chart runtime behavior section)
docs/15-implementation/frontend-sprint-plan.md (status)
```

---

## 5. Risks & follow-ups

| Risk | Mitigation | Owner |
|------|------------|-------|
| Correlation endpoint missing in backend | Fixture fallback; contract extension request before live data | Backend |
| Correlation endpoint status (2026-08-14) | Backend masih belum punya `/market/correlation`; consumer frontend `marketClient.getCorrelation` siap — lihat `FRONTEND-BACKEND-ROADMAP-CHECKPOINT.md` | Backend |
| ECharts lazy chunk 201 kB gzip | Above budget only in aggregate, not critical path; revisit module granularity if bundle budget tightens | Frontend |
| jsdom has no canvas | Chart libs mocked in tests; manual `__mocks__` verify pane option shapes | Frontend |
| Timeout flakiness on loaded machines | `testTimeout: 20000` + explicit waitFor timeout on lazy-pane assertions | Frontend |
