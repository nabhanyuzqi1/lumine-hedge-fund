# F-Sprint 3 — Realtime Data Layer: Plan & Evidence

**Status:** Implementation complete — local gate PASS + independent verification PASS. Pending approval gate before F-Sprint 4.
**Date:** 2026-08-10
**Sprint:** F-Sprint 3 (G11) of Phase 15 — Implementation
**Owner:** Chief AI Architect
**Prerequisites:** F-Sprint 2 (Design System Primitives) approved 2026-08-10

---

## 1. Sprint Goal

Deliver the frontend realtime data layer per `docs/15-implementation/frontend-sprint-plan.md` F-Sprint 3: a streaming SSE client, TanStack Query REST wiring, Zustand domain stores, a virtualized `DataTable`, and a `/streams` demo page that exercises market, portfolio, and committee activity streams.

**Exit criteria (from frontend-sprint-plan.md F-Sprint 3):**

- Custom SSE hook with fetch/`ReadableStream` polyfill, reconnect/backoff, `Last-Event-ID`, heartbeat stale detection, and lifecycle callbacks.
- TanStack Query v5 provider + `queryClient.ts` wrapper for REST endpoints.
- Zustand stores for `market`, `portfolio`, `committee`, and `stream` with ring-buffer limits.
- Virtualized `DataTable` built on `@tanstack/react-virtual`.
- `/streams` demo page consuming live stream stores.
- Colocated tests for all new surface area.

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
| API client | `src/api/client.ts` + `.test.ts` | Envelope-aware `get/post/del` with `ApiError` mapping; `allowNull` support for `DELETE` responses |
| Query client | `src/api/query-client.ts` | TanStack Query v5 client with stale/gc times aligned to realtime feeds |
| SSE hook | `src/hooks/useSSE.ts` + `.test.ts` | fetch-based SSE reader, `Last-Event-ID`, exponential backoff, `Retry-After`, heartbeat stale detection, lifecycle events |
| Market store | `src/stores/marketStore.ts` + `__tests__/marketStore.test.ts` | XAUUSD tick ring buffer (1k ticks), bid/ask/last quote snapshot |
| Portfolio store | `src/stores/portfolioStore.ts` + `__tests__/portfolioStore.test.ts` | Position map, P&L updates, ring-buffered position history |
| Committee store | `src/stores/committeeStore.ts` + `__tests__/committeeStore.test.ts` | Activity feed with filtering and 500-item ring buffer |
| Stream store | `src/stores/streamStore.ts` | Connection status aggregation across SSE subscriptions |
| Data table | `src/components/ui/data-table.tsx` + `.test.tsx` + `.md` | Virtualized table with sticky header, stable row keys, empty state |
| Health page | `src/app/pages/health.tsx` + `.test.tsx` | REST smoke test page using TanStack Query |
| Streams page | `src/app/pages/streams.tsx` + `.test.tsx` | Dashboard demo of market/portfolio/committee streams |
| Test infra | `src/test/setup.ts` | `ResizeObserver` mock + `getBoundingClientRect` override for virtualizer in JSDOM |
| Router | `src/app/router.tsx` | Wires `/health` and `/streams` routes |

### 2.2 Out of scope (later F-Sprints)

- **F-Sprint 4/5/6** — charts, surface layouts, command palette, keyboard shortcuts, performance profiling.
- Backend SSE endpoints (mocked or local-only for the demo page).

---

## 3. Implementation Notes

- **Additive only:** No changes to F-Sprint 2 components or design tokens. The new layer consumes existing `Badge`, `Card`, `NumericText`, and `DataTable` primitives.
- **SSE polyfill design:** Uses `fetch` + `ReadableStream` so custom auth headers can be injected; `EventSource` cannot carry authorization tokens. Reconnect logic honors `Retry-After` on 429 and falls back to exponential backoff capped at ~30s.
- **Last-Event-ID bugfix:** The reconnect callback originally closed over a stale `lastEventId` state. Moved the header value to a ref so the latest event ID is always sent on resume (`src/hooks/useSSE.ts`).
- **Zustand selectors:** Avoided returning derived arrays directly inside selectors (e.g. `Object.values(state.positions)`) to prevent infinite render loops; consumers derive arrays with `useMemo`.
- **Virtualizer JSDOM support:** Added a `ResizeObserver` mock and a `getBoundingClientRect` override for `[data-testid="data-table-scroll"]` in `src/test/setup.ts` so `@tanstack/react-virtual` measures a non-zero viewport.
- **API client DELETE fix:** Added `allowNull` parameter to `throwOnError` so `DELETE` responses with `data: null` no longer throw `EMPTY_RESPONSE`; typed with overloads to preserve `T` return type for `get`/`post`.
- **Bundle delta:** JS gzip grew from ~98 kB to ~131 kB, still well under the 300 kB budget. The delta is dominated by `@tanstack/react-query`, `zustand`, and `@tanstack/react-virtual`.

---

## 4. Local Quality Gates (2026-08-10)

| Gate | Command | Result |
|------|---------|--------|
| Install | `npm install` | PASS — added `@tanstack/react-query`, `@tanstack/react-query-devtools`, `@tanstack/react-virtual`, `zustand` |
| Lint | `npm run lint` (eslint) | PASS — clean |
| Typecheck | `npm run typecheck` (tsc --noEmit) | PASS — clean |
| Test | `npm run test` (vitest) | PASS — 15 files, 40 tests |
| Build | `npm run build` (tsc + vite build) | PASS — dist: index.html 1.48 kB / css 31.06 kB (gzip 6.67 kB) / js 417.40 kB (gzip 131.46 kB) |
| Prettier | `npx prettier --check .` | PASS — all matched files clean after `prettier --write` |

**Bundle note:** JS gzip is 131.46 kB, under the 300 kF budget and a ~33 kB increase from F-Sprint 2.

---

## 5. Test Summary

| File | Tests |
|------|-------|
| `src/api/client.test.ts` | 5 |
| `src/app/pages/health.test.tsx` | 1 |
| `src/app/pages/streams.test.tsx` | 1 |
| `src/components/ui/button.test.tsx` | 4 |
| `src/components/ui/card.test.tsx` | 1 |
| `src/components/ui/data-table.test.tsx` | 3 |
| `src/components/ui/dialog.test.tsx` | 2 |
| `src/components/ui/badge.test.tsx` | 3 |
| `src/components/ui/numeric-text.test.tsx` | 4 |
| `src/components/ui/table.test.tsx` | 1 |
| `src/components/ui/toast.test.tsx` | 3 |
| `src/hooks/useSSE.test.ts` | 6 |
| `src/stores/__tests__/marketStore.test.ts` | 2 |
| `src/stores/__tests__/portfolioStore.test.ts` | 2 |
| `src/stores/__tests__/committeeStore.test.ts` | 2 |

**Total:** 15 test files, 40 tests, all passing.

---

## 6. Independent verification

✅ **PASS** — independent `verification` agent re-ran the full local gate and confirmed all steps passed.

Agent verdict (2026-08-10):
- `npm run lint` — PASS
- `npm run typecheck` — PASS
- `npm run test` — PASS (15 files, 40 tests)
- `npm run build` — PASS
- `npx prettier --check .` — PASS
- JS gzip size: 131.46 kB, under 300KB budget

VERDICT: PASS

---

## 7. Acceptance Criteria Check

| Exit criterion | Status | Evidence |
|----------------|--------|----------|
| SSE hook with reconnect/backoff/`Last-Event-ID` | ✅ | `src/hooks/useSSE.ts` + `useSSE.test.ts` (6 tests) |
| TanStack Query provider and REST wiring | ✅ | `src/api/query-client.ts`, `src/app/pages/health.tsx` |
| Zustand domain stores with ring buffers | ✅ | `src/stores/{market,portfolio,committee,stream}Store.ts` + tests |
| Virtualized `DataTable` | ✅ | `src/components/ui/data-table.tsx` + `.test.tsx` |
| `/streams` demo page | ✅ | `src/app/pages/streams.tsx` + `.test.tsx` |
| Local gate | ✅ | lint / typecheck / test / build / prettier all PASS |
| Independent verification | ✅ | verification agent PASS |

**Status legend:** ⏳ pending → ✅ done → 🚫 blocked

---

## 8. Open items before approval gate

1. ✅ **Independent verification agent** — PASS.
2. ⏳ **Approval gate: AskUserQuestion** — approve F-Sprint 3 before F-Sprint 4 (charts / surfaces).

---

## 9. Sign-off

F-Sprint 3 (Realtime Data Layer) is implementation-complete and the local gate is green. The SSE client, TanStack Query wiring, Zustand stores, virtualized table, and streams demo page are ready for independent verification. Approval gate is the remaining step before entering F-Sprint 4.
