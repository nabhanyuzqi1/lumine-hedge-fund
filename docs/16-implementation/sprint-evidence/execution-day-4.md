# Phase 16 Execution Log — Day 4

**Date:** 2026-08-16
**Sprint:** 16.x — 10 Bug User + CI Hijau + Auto-Deploy + Gap Closure
**Branch:** dev (semua commit + push, sync local ↔ GitHub ↔ VPS)

## 1. B1 — MT5 Positions & Deals Sync (prioritas tertinggi user)

### Root cause
- `PositionSyncWorker._fetch_positions()` return `[]` — placeholder ("TODO: Implement MT5 connection"); EA juga tidak pernah kirim snapshot posisi → DB/website tidak pernah sinkron dengan MT5 (banyak posisi open di MT5, website hanya 1 fixture).

### Fix
- **EA v3.10** (`scripts/deploy/mt5/LumineEA.mq5`): `SendPositionsSnapshot()` (tiap 10s) + `SendDealsSnapshot()` (tiap 30s, HistorySelect 30 hari) → POST `/mt5-proxy/positions` + `/deals` → Redis `mt5:positions` / `mt5:deals`
- Proxy (`backend/scripts/redis_http_proxy.py`): routes `/positions` + `/deals`
- Migrasi `c02228f00013` (positions.mt5_ticket) + `c02228f00014` (fills.mt5_ticket)
- `PositionSyncWorker` rewrite: upsert real (strategy_id deterministik per ticket — fix UniqueViolation `ix_positions_open` untuk banyak posisi XAUUSD), close posisi yang tidak ada di snapshot
- `_deals_worker` (app.py): consume `mt5:deals` → upsert `orders` (trade journal; fix `order_id=uuid4()` — PK tanpa default)
- B9 normalize symbol: `XAUUSDc`/`XAUUSD.stp` → `XAUUSD` (EA `NormalizeSymbol` + backend `_normalize_symbol`)

### Verified (VPS live)
- `SELECT COUNT(*) FROM positions WHERE status='open'` → **18 posisi**, total 0.23 lots (ticket MT5 real, entry 4372-4380)
- API `/portfolio/positions` → 18 posisi dengan mt5 ticket; `/orders` → 20 orders filled dari deals
- Log api: `[DEALS] +20 orders (filled) dari snapshot MT5`

## 2. B2 — Services health mismatch (11/13 vs 8/13)

- OverviewTab hitung `health === "healthy"` saja (8) vs ServicesTab termasuk `running && !health` (11) → **sama-kan logic** (`frontend/src/app/pages/superadmin.tsx`)
- Backend exclude one-shot `backend-migrate-1` (`admin.py` — bukan service runtime)
- Autogen Studio healthcheck `curl` → **python urllib** (slim image tanpa curl) (`docker-compose.autogenstudio.yml`)

## 3. B3 — Spread NaN + header "1/6"

- `quote-panel.tsx`: guard `Number.isFinite` + bid/ask > 0 → "—" saat market closed
- `useCommitteeStreams` register status ke streamStore (sebelumnya committee 4 channel tidak terhitung → "1/6" padahal 5 stream jalan); `TOTAL_STREAMS` 6→5
- **BUG PRODUKSI TERSEMBUNYI**: `channelHeaders = headersByChannel[...] ?? {}` — objek baru tiap render → `useSSE` effect deps `headers` berubah → connect loop → **"Maximum update depth exceeded" → UI blank** (infinite render loop!). Fix: `EMPTY_HEADERS` constant ref.

## 4. B4 — Candle 5m/15m kotor (harga 4305 vs real 4374)

- Bar test garbage `2026-08-14 12:00` (open 4300/high 4310/low 4299/close 4305, volume 100 — harga bulat) di bars_1m + bars_5m → **DELETE** (2 rows) → min close 5m bersih 4312.29
- **Live bars**: `_bar_builder` + `_bar_flush_worker` (app.py) — ticks EA → bar 1m in-memory (bucket per menit UTC) → flush tiap 60s ke bars_1m (ON CONFLICT upsert) + agregasi 5m (bucket 900s) — bars sekarang LIVE, bukan hanya seed history

## 5. B5 — Dashboard kosong (equity/drawdown/signals/confidence/decision)

- **Tabel `signals`** (migrasi `c02228f00015`) + persist di `_handle_run_decision_cycle` (worker.py): Technical Analyst + Investment Committee (direction dari recommendation/action, confidence, rationale) — dipersist SETIAP cycle
- Endpoint `/market/signals` + `/market/signals/{symbol}` serve dari DB (sebelumnya SELALU `items: []`)
- Equity curve: hapus fallback fiktif deterministik (`_DEMO_NAV` drift 6% + drawdown sintetis) → zero-demo: DB down → kosong
- **Verified**: spread 0.96, session off (weekend), features last_price 4374.21, equity nav 3.70, exposure XAUUSD 3653.70, summary margin 20.13, signals 2 rows LLM real

## 6. B6 — What-if Mixed Content + SSE 401 + equity 400

- `core.ts`: `VITE_API_URL` kosong → relative path (resolve origin halaman; Caddy proxy /api/v1) — mixed content fixed
- **SSE 401 root cause**: HMAC signature dibangun untuk path `analyst-outputs` SAJA tapi dipakai semua 4 channel → `useCommitteeStreams` build headers **per-channel** (`useSSE` per stream)
- `DEFAULT_PORTFOLIO_ID` "portfolio-demo" → **"default"** (equity 400 fixed)
- `system-info` timeout: transient (test dalam VPS 1.75s OK)

## 7. B7 — Mobile responsive

- `top-bar.tsx`: username hidden sm, Kill standby badge hidden md, UTC clock hidden sm, gap 2→3

## 8. B8 — P&L akurat dari MT5

- Migrasi `c02228f00016`: `positions.mt5_profit` (Numeric 20,2) — profit REAL broker (contract spec + spread aktual) disimpan tiap snapshot
- API positions/get_position/summary: pakai `mt5_profit` bila ada; fallback mark-to-market
- Fix bug side: `_real_summary` cek `"SHORT"` tapi sync simpan `"sell"` lowercase → short P&L tidak dibalik; handle keduanya

## 9. B9 — Multicurrency: EA prefix + superadmin toggle

- EA `NormalizeSymbol()`: `XAUUSDc`/`XAUUSD.stp`/`XAUUSDm` → `XAUUSD` (SendTick + SendPositionsSnapshot + SendDealsSnapshot)
- Backend `_normalize_symbol` (defense in depth)
- `SystemConfigUpdate.enabled_symbols` + `SystemInfo.enabled_symbols` (Redis `lumine:system_config`) + superadmin ConfigTab **Active Symbols toggle** (6 kandidat, XAUUSD default)

## 10. B10 — LLM Routing Diagram Live (superadmin)

- Backend `GET /admin/llm-usage`: recent LLM calls real dari tabel `llm_usage` (role, tier, model post-fallback, tokens, cost, fallback_hops)
- Frontend `LLMRoutingTab` (`frontend/src/components/superadmin/llm-routing-tab.tsx`): diagram nodes 9router → Gateway → 8 stage agents → SSE channels; node aktif <60s dapat **border glow/pulse**; verbose table (time/stage/model/tokens/cost/state); polling 5s; tab "LLM Routing"

## 11. CI Hijau + Auto-Deploy VPS

### Root causes 20 frontend test failures
- `vi.stubGlobal('import.meta')` tidak bekerja di Vitest → `vi.stubEnv`
- Mock response butuh envelope lengkap `{meta:{status:'ok'},data,error}` (`throwOnError` baca `meta.status`)
- **BUG PRODUKSI**: `toJournalEntry` tidak memetakan `symbol` → kolom journal selalu "-" & filter kosong
- **BUG PRODUKSI**: `portfolioClient.getPositionList/getExposureData` expect array, backend return PaginatedList `{items}` → **RiskGauges crash**
- **BUG PRODUKSI**: `DataTable` className prop diabaikan
- Landing: stub `IntersectionObserver` (framer-motion `whileInView`)
- Terminal: mock module `@/api/client` via `vi.hoisted` (deterministik)

### Quality gates (final)
- Frontend: **170/170 vitest PASS** (40 files) · TSC 0 · production build OK
- Backend: **574/574 unit + 57/57 contract PASS** · ruff clean
- GitHub Actions `.github/workflows/ci.yml`: `build --no-cache api frontend migrate` + `up -d --force-recreate` + **caddy reload** + health check (Host header) → **Deploy job PASS (1m30s)**
- **Verified auto-deploy**: push → CI → VPS health 200, api/frontend healthy (58s uptime setelah CI deploy)

## 12. Gap Closure (G1–G7)

| Gap | Fix | Verified |
|-----|-----|----------|
| G1 PR ke main | PR #1 + #2 merged (dev→main 0 gap) | `git log origin/main..origin/dev` = 0 |
| G2 Decision cycle otomatis | `_decision_scheduler` (app.py): tiap 5 menit saat market open, lock Redis nx 240s, `enqueue_command("run_decision_cycle")` | 631 tests PASS |
| G3 Journal pipeline | `log_step` (hash chain ADR-0017) — technical_analyst + ic_forum tiap cycle | worker.py |
| G4 Correlation jujur | Backend hanya sertakan symbol dengan data; frontend symbols dari response | heatmap bersih 1×1 saat 1 stream |
| G5 Autogen Studio UI rusak | **Gatsby tanpa pathPrefix → asset absolut di root** → Caddy route `/static/* /page-data/* /styles.* /app-* /framework* /webpack-runtime* ...` → autogenstudio | css 200 text/css, js 200 text/javascript |
| G6 Docs | File ini (execution-day-4.md) | — |
| G7 Gap inventory | IMPLEMENTATION-GAP-INVENTORY.md di-update (bawah) | — |

## Commit hashes (branch dev, 2026-08-15/16)

`f52b559 → 33acad9 → dcbbb6c → 1ea16de → c5f868f → 3fa498f → d03a651 → 77d2794 → 18a150d → 3642e23 → adfa508 → fb6e91b → 2880410` (+ lainnya) — semua push + deploy via CI auto-deploy.
