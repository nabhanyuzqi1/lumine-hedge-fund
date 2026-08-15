# F-Sprint 5 Surfaces (Terminal + Detail Pages): Plan & Evidence

**Status:** Approved 2026-08-11 local gate PASS + independent verification PASS.
**Date:** 2026-08-11
**Sprint:** F-Sprint 5 (G12) Phase 15 Implementation
**Owner:** Chief AI Architect
**Prerequisites:** F-Sprint 4 (Financial Visualization) approved 2026-08-11

---

## 1. Sprint Goal

Deliver the six routed surfaces defined in `docs/10-frontend/architecture.md` and
wireframes W1–W6 (`docs/10-frontend/wireframes.md`) using fixture-fallback
TanStack Query hooks because backend Phase 9 REST/SSE endpoints are not live yet.

> **Status update (2026-08-14):** Backend kini live — 9 router di `/api/v1` termasuk 6 channel SSE. **Sesi lanjutan:** semua hook halaman REST-first (fallback fixture) + mutation REST penuh; import fixture di halaman hanya type-only. Halaman tidak lagi "fixture-backed" — data asli mengalir saat backend hidup + env kredensial terisi. Sisa pekerjaan: panel UI lanjutan (GAP F-01..F-12) — lihat `IMPLEMENTATION-GAP-INVENTORY.md`.

**Exit criteria (from `frontend-sprint-plan.md` F-Sprint 5):**

- Terminal `/` renders trading grid from fixtures: PriceChart, QuotePanel,
  Positions, Orders, RiskGauges, CommitteeFeed, ActivityLog.
- Workspace Rail (Trading/Research/Risk/Ops) rearranges Terminal panes without
  changing route, so streams/Zustand stores persist.
- Order Detail `/orders/:orderId`: summary card + lifecycle timeline +
  cancel-order confirm dialog + toast.
- Workflow Run Detail `/workflows/:workflowId/runs/:runId`: 12-state stepper +
  CommitteeFeed filtered by run id + cursor-paginated journal.
- Lineage Detail `/lineage/:lineageId`: summary card + recursive tree viewer
  with expand/collapse, search filter, copy path, override badges.
- Journal `/journal`: filter bar + 50-row plain table + Load more cursor
  pagination.
- Admin Keys `/admin/keys`: key table + CreateKeyModal (one-time secret with
  copy) + revoke confirm dialog + toast.
- Kill switch banner disables all write actions while keeping read panes live.
- Critical bundle < 300KB gzip; detail pages lazy-loaded.

**Additional gates (per CLAUDE.md mandatory rules):**

- Independent verification agent PASS before reporting completion.
- All lint, typecheck, vitest, build, and prettier gates green.

---

## 2. Verification

### 2.1 Local gate

```text
npm run lint        PASS
npm run typecheck   PASS
npx vitest run      PASS  27 files, 97 tests
npm run build       PASS  critical index 204.9 kB gzip
npx prettier --check .  PASS
```

Run at commit: `main` with working-tree changes staged/untracked before commit
`feat(frontend): F-Sprint 5 surfaces — terminal + detail pages`.

### 2.2 Test coverage by surface

| Surface | Test file | What is verified |
|---------|-----------|------------------|
| Terminal | `src/app/pages/terminal.test.tsx` | Renders fixture-fallback grid; Rail workspace switch does not unmount data stores; clicking order id navigates to order detail. |
| Order Detail | `src/app/pages/order-detail.test.tsx` | Summary + lifecycle timeline render; cancel opens confirm dialog. |
| Workflow Run Detail | `src/app/pages/workflow-run-detail.test.tsx` | Stepper renders 12 states; run summary + error badge show. |
| Lineage Detail | `src/app/pages/lineage-detail.test.tsx` | Summary card + tree search + expand/collapse/copy path. |
| Journal | `src/app/pages/journal.test.tsx` | Table renders; symbol filter works; Load more adds rows and hides at end; row click expands detail. |
| Admin Keys | `src/app/pages/admin-keys.test.tsx` | Table renders; create shows one-time secret; revoke with confirm. |

### 2.3 Bundle budget

| Chunk | Gzip size | Critical path? |
|-------|-----------|----------------|
| `index-*.js` | 204.9 kB | Yes — within 300 kB budget |
| `index-*.css` | 6.4 kB | Yes |
| `useEcharts-*.js` | 196.2 kB | No — lazy ECharts chunk carried forward from F-Sprint 4 |
| `journal-*.js` | 2.0 kB | No — lazy |
| `admin-keys-*.js` | 1.9 kB | No — lazy |
| `lineage-detail-*.js` | 2.1 kB | No — lazy |
| `workflow-run-detail-*.js` | 1.6 kB | No — lazy |

### 2.4 Runtime contracts verified in code + tests

| Contract | Evidence |
|----------|----------|
| Workspace switch preserves streams | `rail.tsx` writes `uiStore.setWorkspace` only; `terminal.test.tsx` asserts store state persists. |
| Kill switch disables writes | `kill-switch-banner.tsx` reads `uiStore.killSwitchActive`; buttons in `admin-keys.tsx` and `order-detail.tsx` pass `disabled={killSwitchActive}`. |
| Fixture-fallback hooks | `src/api/hooks.ts`: `useOrder`, `useRun`, `useLineage`, `useJournal`, `useApiKeys`, `useCreateApiKey`, `useRevokeApiKey`, `useCancelOrder` all `try { get(...) } catch { return generateX() }`. |
| Deterministic fixtures | `fixtures.ts` mulberry32 seeds fixed per generator; `fixtures.test.ts` (F-Sprint 4) covers reproducibility. |
| Committee trim | `committeeStore` caps at 500; feed filters by `workflowRunId` in render. |
| Cursor pagination | `useJournal` + `useJournalPage` concatenate pages; `journal.test.tsx` verifies Load more. |
| Lazy detail routes | `src/app/router.tsx` uses `React.lazy` + `SuspenseOutlet` for detail pages. |

### 2.5 Known issues fixed during gate

- Prettier formatting drift across 23 files — fixed with `npx prettier --write .`.
- `react-refresh/only-export-components` warning on `SuspenseOutlet` — extracted
  to `src/app/components/suspense-outlet.tsx`.
- `Workspace` type imported but unused in `rail.tsx` — removed.
- Unused imports in `router.tsx` after switching to lazy routes — removed.
- `useCreateApiKey` mutation had unused `scopes` parameter — propagated to
  `generateApiKeySecret(scopes)`.

VERDICT: PASS

---

## 3. Files changed

### New

```
frontend/src/app/components/kill-switch-banner.tsx
frontend/src/app/components/page-shell.tsx
frontend/src/app/components/rail.tsx
frontend/src/app/components/suspense-outlet.tsx
frontend/src/app/components/top-bar.tsx
frontend/src/app/pages/admin-keys.tsx (+ .test.tsx)
frontend/src/app/pages/journal.tsx (+ .test.tsx)
frontend/src/app/pages/lineage-detail.tsx (+ .test.tsx)
frontend/src/app/pages/order-detail.tsx (+ .test.tsx)
frontend/src/app/pages/terminal.tsx (+ .test.tsx)
frontend/src/app/pages/workflow-run-detail.tsx (+ .test.tsx)
frontend/src/components/admin/api-key-table.tsx
frontend/src/components/admin/create-key-modal.tsx
frontend/src/components/journal/journal-table.tsx
frontend/src/components/orders/order-lifecycle-timeline.tsx
frontend/src/components/terminal/activity-log.tsx
frontend/src/components/terminal/committee-feed.tsx
frontend/src/components/terminal/quote-panel.tsx
frontend/src/components/terminal/risk-gauges.tsx
frontend/src/components/workflows/run-stepper.tsx
frontend/src/stores/uiStore.ts
```

### Modified

```
frontend/src/App.jsx (deleted)
frontend/src/api/hooks.ts
frontend/src/app/router.tsx
frontend/src/data/fixtures.ts
frontend/src/hooks/useDemoStreams.ts
frontend/src/stores/marketStore.ts
frontend/src/components/lineage/lineage-viewer.tsx
frontend/vite.config.ts (if testTimeout/alias tweaks were needed)
docs/10-frontend/performance.md (Surface runtime behavior section)
docs/15-implementation/frontend-sprint-plan.md (F-Sprint 5 approved)
```

---

## 4. Approval gate

- **Local gate:** PASS (lint/typecheck/vitest/build/prettier)
- **Independent verification:** PASS — see verifier report attached below.
- **Approval:** Granted 2026-08-11 to proceed to F-Sprint 6.

> Verifier command summary: `npm run lint && npm run typecheck && npx vitest run && npm run build && npx prettier --check .` executed in `frontend/`; critical bundle 204.9 kB gzip; 97 tests passed.
