# Frontend → Backend Roadmap Checkpoint

**Document Date:** 2026-08-14  
**Status:** Active — status snapshot dari source code frontend (`frontend/src/lib/api/`, `frontend/src/api/hooks.ts`) dan backend (`backend/src/lumine/api/routers/*`, `app.py`)  
**Scope:** Roadmap integrasi frontend→backend Phase 15/16

---

## Executive Summary

Frontend sudah memiliki **semua 10 halaman utama** (fixture-backed) + lapisan API client yang lengkap dan ter-verifikasi (0 error TS, 140 test pass). Backend sekarang sudah live dengan **9 router** di bawah prefix **`/api/v1`** — admin (keys + kill-switch), journal, lineage, market (bars/signals), orders (CRUD, no PATCH), portfolio (summary/positions/exposure), rpc (4 commands), streams (6 SSE), workflows.

Gap terbesar yang tersisa bukan lagi "backend belum ada", melainkan **ketidakselarasan kontrak** antara apa yang frontend panggil dan apa yang backend sajikan:

1. **Prefix path mismatch:** seluruh REST client frontend memanggil `/api/*` (`http://localhost:8000/api/orders`), sementara backend menyajikan di `/api/v1/*`. Hanya halaman Streams (`streams.tsx:26`) yang sudah memakai `/api/v1`. Tanpa proxy rewrite atau `VITE_API_URL` yang diarahkan ke `/api/v1`, semua panggilan REST frontend akan 404.
2. **Kill-switch contract mismatch:** frontend menunggu `POST /api/rpc/kill-switch {active, tier, reason}`; backend punya `POST /api/admin/kill-switch {armed, reason}` (tanpa tier).
3. **Order cancel mismatch:** frontend `PATCH /api/orders/{id}/cancel`; backend `DELETE /api/orders/{order_id}`.
4. **Order modify masih belum ada di backend** (`PATCH /api/orders/{id}`) — satu-satunya UI baru (ModifyOrderDialog) yang masih murni fixture.
5. **Klaster market hampir seluruhnya belum ada** di backend (quote/quotes/ohlcv/symbol/symbols/volatility/correlation/spread/session) — hanya `/market/bars` dan `/market/signals`.

---

## Progress Update (2026-08-14, sesi lanjutan)

Urutan kerja #1–#4 dari "Recommended Next Steps" **selesai dan terverifikasi live** (E2E 16/16, contract backend 53/53, frontend 0 error TS / 151 test / build OK):

1. **Prefix `/api/v1`** — `core.ts:normalizeApiPath()` (single point, semua REST client). ✅
2. **Kill-switch** — frontend rewire ke `POST /api/v1/admin/kill-switch {armed, reason, tier}`; backend + field `tier` (persist Redis, roundtrip). ✅
3. **PATCH `/api/v1/orders/{id}`** — backend live; ModifyOrderDialog ter-rewire. ✅
4. **Klaster market (10 endpoint)** — quote/quotes/ohlcv/symbol/symbols/volatility/correlation/spread/session/features + `POST /portfolio/{id}/simulate`. ✅
5. **Rewire halaman** — sebagian: semua query hook di `src/api/hooks.ts` kini REST-first (fallback fixture), mutation (create/revoke key, cancel, modify, kill-switch) REST penuh. ⏳ halaman lanjutan (WorkflowRunList, Feature/SignalPanel, what-if UI, dsb.) tetap pending.
6. ~~What-if simulate flow~~ — **dihapus dari roadmap** (keputusan user, 21 Aug 2026): tidak akan dibuatkan UI. Backend `POST /api/v1/portfolio/{id}/simulate` tetap live untuk pemakaian internal/testing.
7. Bonus: HMAC signing frontend (`auth.ts` sesuai auth.md) diwire ke kedua fetch layer — integrasi end-to-end sekarang fungsional bila env kredensial diisi.

Detail: `docs/15-implementation/sprint-evidence/FRONTEND-IMPLEMENTATION-GAP.md` → section "Backend → Frontend Alignment — Resolved".

---

## 1. Frontend — Selesai ✅

| Area | Status | Bukti |
|------|--------|-------|
| 10 halaman utama (Landing, Terminal, Dashboard, Streams, Health, Order Detail, Workflow Run Detail, Lineage Detail, Journal, Admin Keys) | ✅ | Semua route live, fixture-backed, SSR/lazy-loaded |
| Design system primitives (Button, Badge, Dialog, Card, DataTable, Toast, Tooltip, Skeleton, NumericText) | ✅ | `src/components/ui/*` |
| Charts (candlestick, equity, drawdown, P&L sparkline, allocation, correlation, confidence) | ✅ | `src/components/charts/*` |
| Stream infrastructure (useSSE + exponential backoff, TopBar health n/6) | ✅ | `src/hooks/useSSE.ts`, `top-bar.tsx:36` |
| KillSwitchConfirmModal (dua-langkah + tier selector + reason) | ✅ | `src/app/components/kill-switch-confirm-modal.tsx` |
| ModifyOrderDialog (volume/price, cancel+new, gating kill-switch) | ✅ | `src/components/orders/modify-order-dialog.tsx` |
| API integration layer (envelope, domain clients, error mapping, query keys) | ✅ | 0 error TS; 140 test pass; `api.integration.test.ts` |
| ToastProvider di root (fix runtime crash) | ✅ | `src/main.tsx` |
| Kualitas: typecheck / vitest / build | ✅ | 0 error / 140 pass / sukses |

## 2. Frontend — Belum Selesai ❌

| Item | Prioritas | Catatan |
|------|-----------|---------|
| Rewire halaman dari fixture → REST/SSE nyata | **Critical** | Semua halaman masih fixture-backed; client sudah siap |
| Fix prefix `/api/v1` di REST clients | **Critical** | `core.ts:147` pakai `VITE_API_URL || localhost:8000` + path `/api/*` |
| WorkflowRunList paginated + navigasi run detail | High | Backend `GET /api/workflows` sudah ada |
| StreamStatusDot per-stream + GapBanner | High | Hanya agregat n/6 di TopBar |
| FeaturePanel + SignalPanel | Medium | Backend cuma punya `/signals` (global), belum per-symbol |
| What-if simulate flow | Medium | `simulateTrade` siap; backend belum ada |
| AnalystCard + DecisionCard | Medium | — |
| Volatility badge, spread alert, session indicator | Low | Backend belum ada |
| ExposureSummaryCard per-sektor | Low | Backend exposure sudah ada (global) |
| CSV export transactions | Low | — |
| Bundle size analyzer + render profiler | Low | — |
| CommandPalette a11y (7 errors) + useExhaustiveDependencies | Pre-existing | Dikenal, bukan regresi |

## 3. Backend — Live ✅ (di bawah `/api/v1`)

| Router | Endpoint | Status |
|--------|----------|--------|
| admin | GET/POST/DELETE `/admin/keys`, GET/POST `/admin/kill-switch` | ✅ |
| journal | GET `/journal`, GET `/journal/{entry_id}` | ✅ |
| lineage | GET `/lineage`, GET `/lineage/{lineage_id}` | ✅ |
| market | GET `/market/bars`, GET `/market/signals` | ⚠️ parsial |
| orders | GET `/orders`, GET `/orders/{order_id}`, POST `/orders`, DELETE `/orders/{order_id}` | ⚠️ tanpa PATCH |
| portfolio | GET `/portfolio/summary`, `/positions`, `/positions/{position_id}`, `/exposure` | ⚠️ tanpa simulate |
| rpc | POST `/rpc/run-decision-cycle`, `/halt-trading`, `/resume-trading`, `/cancel-order` | ✅ |
| streams | 6 SSE: market-data, analyst-outputs, ic-decisions, cio-proposals, risk-assessments, execution-orders | ✅ |
| workflows | GET `/workflows`, GET `/workflows/{run_id}`, POST `/workflows` | ✅ |

## 4. Backend — Belum Ada / Blocker ❌

| Endpoint yang dibutuhkan frontend | Frontend Consumer | Status Backend |
|-----------------------------------|-------------------|----------------|
| `PATCH /api/orders/{order_id}` (order modify) | `ordersClient.modifyOrder`, `useModifyOrder`, ModifyOrderDialog | ❌ tidak ada |
| `GET /api/market/quote/{symbol}`, `/quotes`, `/ohlcv/{symbol}`, `/symbol/{symbol}`, `/symbols` | `marketClient` (getQuote, getQuotes, getOHLCV, getSymbolConfig, listSymbols) | ❌ |
| `GET /api/market/volatility/{symbol}` | QuotePanel badge | ❌ |
| `GET /api/market/session/{symbol}` | PriceChart indicator | ❌ |
| `GET /api/market/features/{symbol}` | FeaturePanel (belum dibuat) | ❌ |
| `GET /api/market/correlation`, `/spread/{symbol}` | `marketClient` (getCorrelation, getSpreadMetrics) | ❌ |
| `POST /api/portfolio/{id}/simulate` | `simulateTrade`, `useSimulateTrade` | ❌ |
| `POST /api/portfolios`, `PUT/DELETE /api/portfolio/{id}` | `portfolioClient` CRUD | ❌ |
| `DELETE /api/portfolio/{portfolio_id}/orders` (cancel-all) | `ordersClient.cancelAllOrders` | ❌ |
| `GET /api/orders/{id}/history`, `/orders/bulk/status` | `ordersClient` (getOrderHistory, bulkGetOrderStatuses) | ❌ |

## 5. Kontrak Mismatch (harus diselaraskan)

| # | Frontend panggil | Backend sajikan | Aksi |
|---|------------------|-----------------|------|
| 1 | `/api/*` (semua REST client) | `/api/v1/*` | Samakan prefix (rewire core.ts atau backend) |
| 2 | `POST /api/rpc/kill-switch {active, tier, reason}` | `POST /api/admin/kill-switch {armed, reason}` | Frontend rewire ke `/admin/kill-switch` + drop tier; atau backend tambah tier |
| 3 | `PATCH /api/orders/{id}/cancel` | `DELETE /api/orders/{order_id}` | Samakan method/path |
| 4 | `GET /api/portfolio/{id}/summary` (dengan id) | `GET /api/portfolio/summary` (tanpa id, single-portfolio) | Frontend drop id |
| 5 | `GET /api/workflows` → daftar runs | `GET /api/workflows` (PaginatedList[WorkflowRun]) | Frontend sesuaikan tipe/halaman |

## 6. Recommended Next Steps

1. **Selaraskan prefix path** — keputusan tercepat: ubah REST clients agar memakai `/api/v1` (streams page sudah jadi contoh yang benar), atau tambahkan proxy rewrite. Ini pra-syarat semua integrasi lain.
2. **Rewire KillSwitchConfirmModal** ke `POST /api/admin/kill-switch {armed, reason}` — release single-step sudah cocok; arm perlu peta tier→armed atau konfirmasi ulang.
3. **Backend tambah `PATCH /api/orders/{order_id}`** — ModifyOrderDialog satu-satunya UI baru yang masih fixture.
4. **Backend lengkapi klaster market** (quote/ohlcv/symbols/volatility/session/features/correlation/spread) — paling banyak consumer frontend siap.
5. **Rewire halaman satu per satu** mulai dari yang backend-nya sudah live: Admin Keys → Journal → Order Detail (list/get) → Workflow Run Detail → Lineage → Dashboard (portfolio) → Terminal (positions/orders).
6. **WorkflowRunList** bisa segera dibangun di atas `GET /api/workflows`.

---

## Lampiran: Frontend Client Path Inventory (verified 2026-08-14)

### `ordersClient.ts`
- `POST /api/orders` — placeOrder
- `GET /api/orders/{id}` — getOrder
- `GET /api/orders?{filters}` — listOrders
- `PATCH /api/orders/{id}/cancel` — cancelOrder
- `PATCH /api/orders/{id}` — modifyOrder
- `DELETE /api/portfolio/{portfolioId}/orders` — cancelAllOrders
- `GET /api/orders/{id}/history` — getOrderHistory
- `GET /api/orders/bulk/status` — bulkGetOrderStatuses

### `marketClient.ts`
- `GET /api/market/quote/{symbol}`
- `GET /api/market/quotes`
- `GET /api/market/ohlcv/{symbol}`
- `GET /api/market/symbol/{symbol}`
- `GET /api/market/symbols`
- `GET /api/market/volatility/{symbol}`
- `GET /api/market/correlation`
- `GET /api/market/spread/{symbol}`
- `GET /api/market/session/{symbol}`

### `portfolioClient.ts`
- `GET /api/portfolio/{id}/summary`
- `GET /api/portfolio/{id}/positions`
- `GET /api/portfolio/{id}/positions/{positionId}`
- `GET /api/portfolio/{id}/exposure`
- `POST /api/portfolio/{id}/simulate`
- `POST /api/portfolios`
- `PUT /api/portfolio/{id}`
- `DELETE /api/portfolio/{id}`

### SSE
- `/api/v1/streams/{market-data|analyst-outputs|ic-decisions|cio-proposals|risk-assessments|execution-orders}` — halaman Streams sudah memakai prefix v1 (streams.tsx:26)

### Hooks (fixture-backed)
- `useModifyOrder` → PATCH `/api/orders/:id` (hooks.ts:356)
- `useKillSwitch` → POST `/api/rpc/kill-switch {active, tier, reason}` (hooks.ts:402-411, TODO phase-9)

---

**End of Document**
