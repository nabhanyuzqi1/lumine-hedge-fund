# Frontend Implementation Gap Analysis — Phase 16 Sprint 16.4

**Document Date:** 2026-08-13  
**Source:** Wireframes + Component Catalog vs Actual Codebase (verified by reading source files)  
**Status:** Verified — this revision corrects an earlier draft that listed many implemented components as missing

---

## Executive Summary

Semua **10 route utama** sudah memiliki halaman yang berfungsi dengan data fixture + integrasi SSE parsial. Terminal workspace, Dashboard, Order Detail, Workflow Run Detail, Lineage Detail, Journal, dan Admin Keys semuanya ter-implementasi. Gap yang tersisa terkonsentrasi di komponen analitik (feature/signal panel), kontrol operasional (kill-switch confirm + order modify), dan monitoring stream detail (per-stream status dot, gap banner).

---

## Page-Level Status (Verified)

| Page | Route | Status | Notes |
|------|-------|--------|-------|
| **Landing** | `/` | ✅ Done | Card-based portal |
| **Terminal** | `/terminal` | ✅ Done | Chart, quote, positions, orders, risk, committee, activity |
| **Order Detail** | `/orders/:orderId` | ✅ Done | Lifecycle timeline, cancel w/ confirm dialog, kill-switch gating |
| **Dashboard** | `/dashboard` | ✅ Done | Candlestick, equity, drawdown, P&L sparkline, allocation, correlation, confidence — semua chart ter-render |
| **Streams** | `/streams` | ✅ Done | SSE → Zustand → virtualized table end-to-end |
| **Health** | `/health` | ✅ Done | Real API probe via TanStack Query (refetch 5s) |
| **Workflow Run Detail** | `/workflows/:id/runs/:runId` | ✅ Done | RunStepper, run summary, filtered CommitteeFeed |
| **Lineage Detail** | `/lineage/:lineageId` | ✅ Done | LineageViewer w/ search, override badge, summary cards |
| **Journal** | `/journal` | ✅ Done | Cursor pagination, symbol/portfolio/kind/date filters, load-more |
| **Admin Keys** | `/admin/keys` | ✅ Done | ApiKeyTable, CreateKeyModal, secret-once dialog, revoke confirm |
| **Research Workspace** | `/research` | ❌ Placeholder | Belum ada route/file |
| **Risk Workspace** | `/risk` | ❌ Placeholder | Belum ada route/file |
| **Ops Workspace** | `/ops` | ❌ Placeholder | Belum ada route/file |

> Semua halaman memakai fixture fallback. Backend Phase 9 sudah live (9 router: portfolio, orders, market, streams, workflows, journal, lineage, admin, rpc), tetapi halaman belum di-rewire dari fixture ke API client/hook asli; sebagian endpoint juga masih belum ada di backend (lihat tabel Backend Dependencies).

---

## Component-Level Gap Analysis (Verified)

### A. Primitives (Design System) — ✅ Complete

| Component | Status | File |
|-----------|--------|------|
| `Button` | ✅ | src/components/ui/button.tsx |
| `Badge` | ✅ | src/components/ui/badge.tsx |
| `Dialog` | ✅ | src/components/ui/dialog.tsx |
| `Card` | ✅ | src/components/ui/card.tsx |
| `NumericText` | ✅ | src/components/ui/numeric-text.tsx |
| `DataTable` | ✅ | src/components/ui/data-table.tsx |
| `Toast` | ✅ | src/components/ui/toast.tsx |
| `Tooltip` / `Skeleton` | ✅ | Tailwind/ui library |

### B. Stream Infrastructure — ⚠️ Partial

| Component | Status | Notes |
|-----------|--------|-------|
| `useSSE` / reconnect | ✅ | src/hooks/useSSE.ts, exponential backoff |
| TopBar aggregate health (n/6) | ✅ | `healthyCount`/`TOTAL_STREAMS` di top-bar.tsx:36 |
| `StreamStatusDot` per-stream | ❌ | Hanya agregat n/6, belum ada dot per-stream |
| `GapBanner` | ❌ | "Data missed during reconnect" belum ada |

### C. Market Components — ⚠️ Partial

| Component | Status | Notes |
|-----------|--------|-------|
| `PriceChart` (`CandlestickChart`) | ✅ | lightweight-charts, lazy-loaded |
| `QuotePanel` | ✅ | Bid/ask/spread + live tick overlay |
| `AllocationChart` | ✅ | src/components/charts/allocation-chart.tsx |
| `CorrelationChart` | ✅ | src/components/charts/correlation-chart.tsx |
| `ConfidenceChart` | ✅ | src/components/charts/confidence-chart.tsx |
| `EquityChart` | ✅ | Standalone, pakai fixture |
| `DrawdownChart` | ✅ | Standalone, pakai fixture |
| `PnlSparkline` | ✅ | src/components/charts/pnl-sparkline.tsx |
| `FeaturePanel` | ❌ | Polling `features/{symbol}` belum ada |
| `SignalPanel` | ❌ | Polling `signals/{symbol}` belum ada |

### D. Positions & Orders — ✅ Complete

| Component | Status | Notes |
|-----------|--------|-------|
| `PositionsTable` | ✅ | Virtualized, delta updates |
| `OrdersTable` | ✅ | Status badges, row-click nav |
| `OrderLifecycleTimeline` | ✅ | src/components/orders/order-lifecycle-timeline.tsx |
| Cancel order (inline) | ✅ | Confirm dialog + kill-switch gating di order-detail.tsx |
| Order modify (ModifyOrderDialog) | ✅ | src/components/orders/modify-order-dialog.tsx — form volume/price + teks cancel+new; wired di OrdersTable (terminal.tsx) & order-detail.tsx; gated kill-switch/terminal. Fixture-backed via useModifyOrder (kontrak PATCH ordersClient.modifyOrder) |

### E. Committee / AI Reasoning — ⚠️ Partial

| Component | Status | Notes |
|-----------|--------|-------|
| `CommitteeFeed` | ✅ | Filterable by workflow_run_id |
| `AnalystCard` | ❌ | Standalone confidence meter belum ada |
| `DecisionCard` | ❌ | Click → lineage/run detail belum ada |

### F. Risk Components — ⚠️ Partial

| Component | Status | Notes |
|-----------|--------|-------|
| `RiskGauges` | ✅ | Exposure, leverage, drawdown, margin (fixture values) |
| `KillSwitchBanner` | ✅ | src/app/components/kill-switch-banner.tsx |
| Kill-switch toggle | ✅ | CommandPalette membuka KillSwitchConfirmModal (bukan toggle langsung) |
| `KillSwitchConfirmModal` | ✅ | src/app/components/kill-switch-confirm-modal.tsx — dua-langkah konfirmasi + tier selector (global/book/strategy) + reason; release satu-langkah; fixture-backed via useKillSwitch |
| `ExposureSummaryCard` | ❌ | Breakdown per-sektor belum ada |

### G. Workflow & Lineage — ⚠️ Shell Only

| Component | Status | Notes |
|-----------|--------|-------|
| `RunStatusBadge` | ✅ | Inline + di run detail |
| `RunStepper` | ✅ | 12-stage stepper di run-stepper.tsx |
| `LineageViewer` | ✅ | Tree viewer w/ search, copy path |
| `WorkflowRunList` | ❌ | Daftar runs paginated belum ada (hanya detail per-run) |

### H. Journal — ✅ Complete

| Component | Status | Notes |
|-----------|--------|-------|
| `JournalTable` | ✅ | Cursor pagination, expandable rows |
| Journal filters | ✅ | Symbol/portfolio/kind/date di journal.tsx |
| Load-more | ✅ | State machine has_more → load more |

### I. Admin — ✅ Complete

| Component | Status | Notes |
|-----------|--------|-------|
| `ApiKeyTable` | ✅ | Masked keys, scopes, revoke |
| `CreateKeyModal` | ✅ | Scope selection |
| Secret-once dialog | ✅ | Copy-to-clipboard, "not shown again" |
| `RevokeKeyConfirm` | ✅ | Confirmation dialog |

### J. Global Components — ⚠️ Partial

| Component | Status | Notes |
|-----------|--------|-------|
| `TopBar` | ✅ | Kill-switch badge, UTC clock, stream health n/6, ⌘K trigger |
| `CommandPalette` | ✅ | Full nav, symbol select, kill-switch toggle, reset workspace |
| `ActivityLog` | ✅ | Error entries w/ trace_id |
| `PageShell` | ✅ | Layout container |
| Keyboard provider | ✅ | src/app/components/keyboard-provider.tsx |

---

## Feature-by-Feature Gap Table (Verified Remaining)

> Selesai siklus ini: Kill-switch confirm dialog (F-5) dan Order modify UI (D-4) — lihat daftar komponen di atas.

| Feature | Wireframe Ref | Priority | Missing Sub-items |
|---------|---------------|----------|-------------------|
| Stream gap detection | B-3 | High | - GapBanner "data missed during reconnect"<br>- Per-stream StreamStatusDot |
| Workflow run list | W3 | Medium | - WorkflowRunList paginated<br>- Navigasi ke run detail |
| Feature/Signal panel | C-2 | Medium | - FeaturePanel polling `features/{symbol}`<br>- SignalPanel polling `signals/{symbol}` |
| ~~What-if trade simulation~~ | R-2 | ~~Medium~~ | **Dihapus dari roadmap** (keputusan user, 21 Aug 2026) — tidak akan diimplementasikan; backend endpoint tetap ada tapi tanpa UI |
| Analyst/Decision card | W3 | Medium | - AnalystCard confidence meter<br>- DecisionCard → lineage/run navigation |
| Volatility regime badge | W1 | Medium | - POST /api/market/volatility/{symbol}<br>- Low/normal/high color coding |
| Spread alert banner | B-3 | Low | - Threshold config modal<br>- Wide spread (>2x normal) detection |
| Session timezone indicator | W1 | Low | - GET /api/market/session/{symbol}<br>- Next session countdown |
| Exposure summary | W7 | Low | - ExposureSummaryCard per-sektor |
| CSV export transactions | R-9 | Low | - Download blob handler |
| Bundle size analyzer | Health | Low | - Vite plugin output, treemap viz |
| Render profiler per-component | Health | Low | - React Profiler hook wrapper |

---

## Backend Dependencies (Blockers)

Di-verifikasi ulang terhadap source backend (`backend/src/lumine/api/routers/`) dan `backend/src/lumine/api/app.py` pada 2026-08-14. Backend sudah live dengan 9 router di bawah prefix **`/api/v1`** (app.py:144 `app.include_router(router, prefix="/api/v1")`). Temuan kunci: sebagian besar "blocker" lama sudah hilang; gap yang tersisa adalah **mismatch kontrak** (terutama prefix path) + klaster market yang belum ada. Rincian lengkap di `FRONTEND-BACKEND-ROADMAP-CHECKPOINT.md`.

### ⚠️ Critical: Prefix Path Mismatch

Seluruh REST client frontend memanggil `/api/*` (base `http://localhost:8000` + path `/api/...`), sementara backend menyajikan semua route di bawah `/api/v1/*`. Hanya halaman Streams yang sudah memakai `/api/v1` (streams.tsx:26). Tanpa rewire, semua panggilan REST frontend akan 404. Ini pra-syarat integrasi.

### Covered (backend live ✅, frontend siap konsumen)

| Endpoint (path backend sebenarnya di bawah /api/v1) | Status | Frontend Consumer |
|----------|--------|-------------------|
| GET /api/v1/workflows (PaginatedList) | ✅ | WorkflowRunList (belum dibuat) — path berbeda dari wireframe `/workflows/{id}/runs` tapi data run list sudah tersedia |
| GET /api/v1/journal + /journal/{entry_id} | ✅ | JournalTable (sudah siap) |
| GET/POST/DELETE /api/v1/admin/keys | ✅ | ApiKeyTable (sudah siap) |
| GET/POST /api/v1/admin/kill-switch | ✅ | KillSwitchConfirmModal — lihat Mismatch #2 |
| GET /api/v1/portfolio/{summary, positions, positions/{id}, exposure} | ✅ | useExposureData & dashboard — tidak ada `{id}` di path summary; asumsi single-portfolio |
| GET /api/v1/market/bars, /market/signals | ✅ | marketClient getBars/getSignals (belum di-rewire dari fixture) |
| GET /api/v1/lineage, /lineage/{lineage_id} | ✅ | LineageViewer (belum di-rewire) |
| GET /api/v1/streams/* (6 channel SSE) | ✅ | streamStore + TopBar health n/6 — halaman Streams sudah pakai /api/v1 |
| POST /api/v1/rpc/{run-decision-cycle, halt-trading, resume-trading, cancel-order} | ✅ | CommandPalette / run detail (belum di-rewire) |

### ⚠️ Mismatch (backend ada, tapi jalur/kontrak beda dengan frontend)

| # | Backend sajikan | Frontend panggil | Aksi |
|---|-----------------|------------------|------|
| 1 | Prefix `/api/v1/*` | `/api/*` | Samakan prefix (rewire core.ts atau backend) |
| 2 | POST /api/v1/admin/kill-switch `{armed, reason}` | POST /api/rpc/kill-switch `{active, tier, reason}` (hooks.ts:402-411) | Frontend rewire ke `/admin/kill-switch` + drop/piakan tier; atau backend tambah tier |
| 3 | DELETE /api/v1/orders/{order_id} (cancel) | PATCH /api/orders/{id}/cancel (ordersClient.ts:107) | Samakan method/path |
| 4 | GET /api/v1/portfolio/summary (tanpa id) | GET /api/portfolio/{id}/summary (portfolioClient.ts:47) | Frontend drop id |
| 5 | GET /api/v1/market/signals (list global) | SignalPanel butuh per-symbol `/signals/{symbol}` | Backend tambah varian per-symbol |

### Missing (belum ada di backend ❌)

| Endpoint | Frontend Consumer |
|----------|-------------------|
| PATCH /api/v1/orders/{order_id} (order modify) | ModifyOrderDialog — `ordersClient.modifyOrder` siap; orders.py hanya GET/POST/DELETE |
| GET /api/v1/market/quote/{symbol}, /quotes, /ohlcv/{symbol}, /symbol/{symbol}, /symbols | `marketClient` (getQuote, getQuotes, getOHLCV, getSymbolConfig, listSymbols) |
| GET /api/v1/market/volatility/{symbol} | QuotePanel badge |
| GET /api/v1/market/session/{symbol} | PriceChart indicator |
| GET /api/v1/market/features/{symbol} | FeaturePanel (belum dibuat) |
| GET /api/v1/market/correlation, /spread/{symbol} | marketClient (getCorrelation, getSpreadMetrics) |
| POST /api/v1/portfolio/{id}/simulate | What-if flow — `simulateTrade` + `useSimulateTrade` siap |
| POST /api/v1/portfolios, PUT/DELETE /api/v1/portfolio/{id} | portfolioClient CRUD |
| DELETE /api/v1/portfolio/{portfolio_id}/orders (cancel-all) | ordersClient.cancelAllOrders |
| GET /api/v1/orders/{id}/history, /orders/bulk/status | ordersClient (getOrderHistory, bulkGetOrderStatuses) |

---

## Backend → Frontend Alignment — Resolved (2026-08-14, sesi lanjutan)

Seluruh item Mismatch + Missing klaster market/orders/simulate di atas sudah **diselesaikan dan diverifikasi live** (E2E smoke 16/16 terhadap backend berjalan + Redis fakeredis, signature HMAC skema sama persis dengan frontend).

| Item | Status | Bukti |
|------|--------|-------|
| Prefix `/api/v1` (mismatch #1) | ✅ | `core.ts` `normalizeApiPath()` — satu titik normalize untuk semua REST client; test prefix di `api.integration.test.ts` |
| Kill-switch (mismatch #2) | ✅ | Frontend rewire ke `POST /api/v1/admin/kill-switch {armed, reason, tier}`; backend `KillSwitchRequest/Status` + field `tier` persist Redis; modal + test diperbarui |
| Cancel order (mismatch #3) | ✅ | `ordersClient.cancelOrder` → `DELETE /api/v1/orders/{id}` (selaras routers/orders.py) |
| Portfolio drop-id (mismatch #4) | ✅ | `portfolioClient` summary/positions/exposure tanpa `{id}` (single-portfolio) |
| `PATCH /api/v1/orders/{id}` (modify) | ✅ | `ModifyOrderRequest` (min 1 field, validator) + handler di `routers/orders.py`; ModifyOrderDialog ter-rewire + error toast |
| Klaster market (10 endpoint) | ✅ | `quote/{s}`, `quotes`, `ohlcv/{s}`, `symbol/{s}`, `symbols`, `volatility/{s}`, `correlation`, `spread/{s}`, `session/{s}`, `features/{s}` — `routers/market.py` + `demo_data.py` deterministik |
| `POST /api/v1/portfolio/{id}/simulate` | ✅ | `SimulateTradeRequest/Result` + handler `routers/portfolio.py` (404 untuk portfolio tak dikenal) |
| HMAC signing frontend | ✅ | `auth.ts` ditulis ulang sesuai `docs/09-api/auth.md` (payload `METHOD\npath\ntimestamp\nbody_hash`, pacing timestamp anti-replay); diwire ke `core.ts` + `client.ts`; opt-in via `VITE_LUMINE_API_KEY`/`VITE_LUMINE_API_SECRET`; 6 unit test skema |
| Hooks REST-first + mapper | ✅ | `src/api/hooks.ts`: 10 query hooks REST-first (fallback fixture) + 5 mutation REST (create/revoke key, cancel, modify, kill-switch) dengan mapper REST→fixture shape (Decimal string → Number) |

Bug yang ditemukan & diperbaiki selama verifikasi: `orjson` tidak dideklarasikan di pyproject (dipakai market_service/sse); `validation_exception_handler` crash pada model_validator error (`ctx` tidak serializable); `rate_limit_dependency` 500 saat Redis tidak dikonfigurasi (kini degrade); `MT5Bridge.from_url` tidak di-await di lifespan; `generate_openapi.py` menulis CRLF di Windows sehingga contract test byte-identical gagal.

### Masih open (tidak berubah sesi ini)

- Backend: portfolio CRUD (`/portfolios`), `DELETE /portfolio/{id}/orders` (cancel-all), `GET /orders/{id}/history` + `/orders/bulk/status`, signals per-symbol, equity curve.
- UI (backend sudah siap): WorkflowRunList paginated, StreamStatusDot/GapBanner, FeaturePanel/SignalPanel, what-if simulate panel, AnalystCard/DecisionCard, volatility/spread/session indicators, ExposureSummaryCard, CSV export, bundle analyzer.
- Catatan: 52 failure backend suite pre-existing di area llm-gateway/prompt-registry (`Registry.__init__` API mismatch) — bukan regresi sesi ini; contract + openapi (53/53) hijau.

### Quality gate (2026-08-14, sesi lanjutan — fresh)

- Backend: `tests/contract` → **53/53 passed**; ruff bersih pada semua file yang diubah
- Frontend: `npx tsc --noEmit` → **0 errors**; `vitest run` → **35 files / 151 tests passed**; `vite build` → sukses
- E2E live: backend uvicorn + fakeredis → **16/16 checks** (auth 401/401, market 10 endpoint, PATCH order, simulate, kill-switch tier roundtrip, bad-signature 401)

---

## API/SSE Integration Layer — Repaired & Verified (2026-08-14)

Lapisan integrasi frontend→backend (`frontend/src/lib/api/*` + `frontend/src/hooks/api/*`) yang sebelumnya tidak ter-kompilasi (67 error TypeScript) dan crash runtime di `src/lib/metrics.ts` sudah diperbaiki dan terverifikasi. Pekerjaan ini tidak mengubah daftar gap komponen di atas — halaman masih fixture-backed.

| Item | Sebelum | Sesudah | Bukti |
|------|---------|---------|-------|
| `core.ts` envelope contract | `extractEnvelope` double-unwrap → seluruh client mengembalikan `undefined` saat runtime | Full envelope `{ data, metadata }` divalidasi; client unwrap `result.data!.data` | `src/lib/api/core.ts:110-123` |
| `streams.ts` SSE types | error TS `never` narrowing pada closure `let source` | Getter `isConnected`/`isConnecting` dievaluasi saat akses; `SseError` hierarchy dengan `.event` | `src/lib/api/streams.ts:77-` |
| hooks API | error TS6133/TS6192 (unused vars) | `usePortfolio.ts`, `useOrders.ts`, `data-table.tsx`, `src/api/hooks.ts` dibersihkan | — |
| `metrics.ts` | Crash runtime (entry tidak di-init) | `getOrCreateEntry()` membuat entry on-demand | `frontend/src/lib/metrics.ts` |
| Test integrasi API | tidak ada | `api.integration.test.ts` (16 test: HTTP client, error mapping, domain clients, SSE streaming, query keys, edge cases) | `frontend/src/test/api.integration.test.ts` |
| Test lain diperbaiki | `rail.test.tsx`, `landing.test.tsx` gagal | `landing.test.tsx` di-rewrite (redirect stub), `rail.test.tsx` + wrapper `MemoryRouter` | — |

### Quality gate (2026-08-14, fresh)

- `npm run typecheck` → **0 errors**
- `npx vitest run` → **34 files / 140 tests passed**
- `npm run build` → sukses
- Independent verification agent → **PASS** (spot-check ulang konsisten)

> Catatan verifier (pre-existing, bukan regresi): `cancelAllRequests` tidak benar-benar membatalkan request in-flight (Set controller tidak pernah diisi); native `EventSource` auto-reconnect berpotensi double-reconnect saat runtime.

---

## Recommended Implementation Order

**Critical (operational safety):** ✅ selesai — KillSwitchConfirmModal & ModifyOrderDialog sudah diimplementasikan
1. ~~KillSwitchConfirmModal~~ — dua-langkah konfirmasi + tier selector, ganti toggle langsung di CommandPalette
2. ~~ModifyOrderButton~~ — pakai client `modifyOrder` yang sudah ada

**High (realtime observability):**
3. StreamStatusDot per-stream + GapBanner
4. WorkflowRunList paginated

**Medium (analytics):** ✅ selesai 21–22 Aug 2026
5. ~~FeaturePanel + SignalPanel~~ — ✅ SignalPanel sudah live di dashboard (AnalystCard di dalamnya); FeaturePanel baru di terminal (`feature-panel.tsx`, F-06)
6. ~~What-if simulate flow~~ — **dihapus dari roadmap** (21 Aug 2026)
7. ~~AnalystCard + DecisionCard~~ — ✅ sudah live (`analyst-card.tsx`, `decision-card.tsx` dipakai dashboard + AI insight panel)

**Low:** ✅ selesai 22 Aug 2026
8. ~~Volatility badge, spread alert, session indicator~~ — ✅ `MarketConditionBadges` di terminal chart header (threshold VOL/SPR + tooltip)
9. ~~Exposure summary, CSV export~~ — ✅ sudah live (ExposureSummaryCard di dashboard; CSV export di journal)
10. ~~Bundle analyzer + render profiler~~ — ✅ render profiler sudah ada (`usePerformanceMetrics`); bundle analyzer via `pnpm analyze` (rollup-plugin-visualizer → dist/stats.html)

---

## Recommendations

1. **Selaraskan prefix path dulu (blocker #1)** — REST clients frontend memakai `/api/*`, backend menyajikan `/api/v1/*`. Lihat `FRONTEND-BACKEND-ROADMAP-CHECKPOINT.md` bagian Kontrak Mismatch. Tanpa ini semua panggilan REST 404.
2. **Rewire KillSwitchConfirmModal** ke `POST /api/v1/admin/kill-switch {armed, reason}` — backend sudah live; frontend masih fixture di hooks.ts:402-411 (tier selector perlu dipetakan atau di-drop).
3. **Backend tambah PATCH /api/orders/{order_id}** — ModifyOrderDialog satu-satunya UI baru yang masih murni fixture.
4. **Backend lengkapi klaster market** (quote/ohlcv/symbol/symbols/volatility/correlation/spread/session/features) dan POST /portfolio/{id}/simulate — consumer frontend sudah siap semua.
5. **Rewire halaman bertahap** mulai dari backend yang sudah live: Admin Keys → Journal → Order Detail (list/get) → Workflow Run Detail → Lineage → Dashboard (portfolio) → Terminal (positions/orders).
6. **WorkflowRunList** bisa segera dibangun di atas GET /api/v1/workflows.
7. **TanStack Query untuk semua REST**; SSE hanya untuk stream realtime (sudah konsisten).
8. **Tambahkan TypeScript strict** untuk menangkap mismatch kontrak backend-frontend.

---

**End of Document**
