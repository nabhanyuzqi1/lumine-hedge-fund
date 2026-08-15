# Phase 16 Execution Log — Day 3

**Date:** 2026-08-15
**Sprint:** 16.x — Production Hardening: MT5 EA Stability, LLM Gateway, Committee Feed
**Branch:** dev (semua commit + push ke GitHub, sync local ↔ VPS)

## Actions Taken Today

### ✓ EA v3 Super-Stabil (MT5 Bridge)
- **Watchdog OnTimer(2s)**: auto-reconnect, self-healing, never ExpertRemove
  - `scripts/deploy/mt5/LumineEA.mq5` (47,904 bytes compiled)
- **Retry exponential backoff** (1→2→5→10→30s) untuk sendTick/pollCommands
  (fix http_code=1003 yang tadinya menghentikan EA)
- **Ring buffer log** (100 entry) → log penuh tanpa spam console
- **REASON_CHARTCHANGE survival**: EA tetap jalan meski TF/symbol berubah
- **Verified live**: EA v3 running, ticks E2E → Redis → MarketService → API quote
  - `docker exec lumine-mt5` → "LumineEA v3 ready (HTTP polling, self-healing)"
  - POST /mt5-proxy/ticks → 200 OK → quote API bid real

### ✓ Backend Zero-Demo + Multi-TF OHLCV
- `/api/v1/market/quotes` batch (Record<symbol, quote>) — `backend/src/lumine/api/routers/market.py`
- `/api/v1/market/ohlcv` 5m/15m/4h/1h/1d live:
  - 5m: 802 bar, 4h: 1,317 bar (data riwayat real dari DB)
  - Aggregasi: `backend/scripts/aggregate_bars.sql`
- **Market calendar**: SSE `market_closed` saat libur (weekend bid=0 tidak kirim tick sampah)
- Quality gate: contract tests **57/57 PASS**, unit **574/574 PASS**

### ✓ Frontend Health Probes Fix
- Path benar: `/health` root (tanpa /api/v1), `/market/quotes?symbols=XAUUSD`, `/journal`
- `frontend/src/app/pages/health.tsx` + test mock Record shape
- Deployed live

### ✓ Superadmin System-Info — Docker API Socket
- Mount `/var/run/docker.sock:ro` ke service api (`backend/docker-compose.vps.yml:78`)
- User `lumine` → group docker GID 988 (`backend/Dockerfile:33`)
- `docker` SDK (7.2.0) + `load_model_versions` — `backend/src/lumine/api/routers/admin.py`
- **Verified: 13 containers detected** (api/caddy/frontend/postgres/redis/mt5-bridge/dozzle/9router/...)

### ✓ 9router LLM Gateway — LLM Pipeline UNBLOCKED
- **Root cause committee feed**: default model `deepseek-v4` tidak ada di 9router
- Fix: `LLM_DEFAULT_MODEL=oc/deepseek-v4-flash-free` (noAuth provider, gratis)
  - `.env` VPS + `backend/docker-compose.vps.yml` env pass-through
- **Accept: application/json** header — 9router append `data: [DONE]` SSE marker
  tanpa header itu → JSON parse error (`backend/src/lumine/llm_gateway/client.py:74`)
- model_versions DB: tier valid + `oc/deepseek-v4-flash-free`
  (`backend/scripts/seed_production.py:58`)

### ✓ RPC Worker Hardening
- Satu message malformed tidak crash worker loop (KeyError fix)
  - `backend/src/lumine/rpc/worker.py` — skip + XACK + try/except per message
- **Verified**: worker proses command + publish SSE + result completed

### ✓ SSE Stream Relay Fix (Committee Feed Bug)
- `_event_stream` HANYA kirim heartbeat — TIDAK pernah subscribe publisher queue
  → event dari worker tidak pernah sampai client (`backend/src/lumine/api/routers/streams.py:235`)
- Fix: subscribe SSEPublisher queue + relay event sesuai channel
- **Verified E2E**: subscribe ic-decisions → trigger → event `ic_decision` sampai client

### ✓ Frontend Committee Streams
- `frontend/src/hooks/useCommitteeStreams.ts`: connect 4 SSE channel
  (analyst-outputs, ic-decisions, cio-proposals, risk-assessments) → committeeStore
- `frontend/src/app/pages/terminal.tsx` panggil hook → CommitteeFeed LIVE

### ✓ Committee Feed — LLM REAL (Decision Cycle)
- `run_decision_cycle` RPC: demo → LLM real
  - Load bars_5m dari DB → indikator (atr_14/ema/rsi via `lumine.features.indicators`)
  - Technical Analyst (LLM via 9router) → IC Forum → verdict
  - Publish SSE `analyst_output` + `ic_decision`
- `Gateway.complete_async` + `run_chain_async` (event-loop safe —
  `asyncio.run` crash di worker loop)
- Prompt registry COPY ke image (`backend/Dockerfile:44` + `backend/docs/prompts/`)
- **Verified E2E**: `{"action": "HOLD", "confidence": 0.55}` → SSE ic_decision → frontend

### ✓ What-if Simulation Fix
- **Root cause**: `VITE_API_URL=http://localhost:8000` default — request browser
  user ke localhost (tidak ada) / `http://166.88.227.177` (HTTP dari halaman HTTPS
  = mixed content blocked) → "Network request failed"
- Fix: `VITE_API_URL` default relatif (origin halaman via Caddy)
  (`frontend/src/lib/api/core.ts:165`, `frontend/Dockerfile`, `docker-compose.vps.yml`)
- Backend: fallback `_last_close` (bars_1h) saat market closed — simulate tetap
  berguna weekend, harga real bukan fiktif (`backend/src/lumine/api/routers/portfolio.py:59`)
- **Verified**: `POST /portfolio/default/simulate` → projected_nav 1980.13 (fallback last close)

### ✓ Terminal Positions — Real Data dari MT5
- `/portfolio/positions` sebelumnya HARDCODED fixture (XAUUSD 1.50 @ 2420.30)
- Fix: `PositionRepository.list_open()` dari tabel positions (data MT5 real)
  - Mark-to-market: live MarketService → fallback last_close bars_1h → avg_entry
  - `unrealized_pnl = (current - avg_entry) * size`
- **Verified**: `{"symbol": "XAUUSD", "direction": "long", "volume": "0.0500",
  "entry_price": "4302.50", "current_price": "4376.43" (LIVE tick EA), "unrealized_pnl": "3.70"}`
- Orders sudah DB-backed (19 filled orders, mt5_ticket real)

### ✓ Risk Gauges — Zero-Demo Real
- Sebelumnya fixture hardcoded (Exposure 8.2%, Leverage 2.1x, dll)
- Fix: `usePortfolioSummary` + `usePositionList` (backend real)
  - Exposure % = gross notional / NAV
  - Leverage = notional / NAV
  - Margin used = margin_used / NAV
  - Net P&L session = open_pnl + closed_pnl
- Data tidak tersedia → tampil "—" (bukan angka fiktif)
- (`frontend/src/components/terminal/risk-gauges.tsx`)

### ✓ Frontend Zero-Demo — Semua Hooks Buang Fixture Fallback
- `useEquityCurve`/`useExposure`/`useSignals`: return [] saat API kosong
  (sebelumnya generateEquity/generateExposure/generateSignals fiktif)
- `useOrder`/`useRun`/`useLineage`: throw NotFoundError (bukan generate)
- `useJournal`/`useJournalPage`: return empty page
- `useApiKeys`: return [] / `useCorrelation`: matrix kosong
- (`frontend/src/api/hooks.ts`)

## Issues Encountered & Resolved

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| SSE stream cuma heartbeat | `_event_stream` tidak subscribe publisher queue | subscribe + relay events |
| LLM call invalid JSON | 9router append `data: [DONE]` tanpa Accept json | `Accept: application/json` |
| `asyncio.run` crash di worker | run_chain sync dipanggil di event loop | `run_chain_async` + `Gateway.complete_async` |
| `Decimal - float` | bars float vs indicators Decimal | bars konsisten Decimal |
| `tier='primary'` invalid | seed pakai tier lama | `cost-efficient` |
| `unknown model_version_id` | ModelRegistry kosong | `load_model_versions(session)` |
| RPC worker crash | message malformed (field `cmd` bukan `command`) | hardening skip + XACK |
| Prompt registry tidak ada di image | Dockerfile tidak COPY docs/prompts | COPY + sync backend/docs/prompts |
| "Network request failed" what-if | VITE_API_URL localhost/IP HTTP | relatif origin |
| system-info `[unknown]` | docker CLI tidak ada + socket permission | Docker SDK + GID 988 + ImageNotFound fix |

## Next Steps

1. **Terminal positions/orders** — real qty/status/P&L dari MT5 fills (DB sudah sync)
2. **Risk gauges** — session limits + net P&L real
3. **Dashboard** — buang sisa demo data (charts, exposure, correlation)
4. **Journal** — verifikasi real vs demo
5. **Autogen Studio** — Caddy route `/autogen-studio` (akses via domain)
6. **9router** — setup provider credentials berbayar (opsional; free tier sudah jalan)

---

**Evidence pointers:**
- EA v3: `scripts/deploy/mt5/LumineEA.mq5`
- SSE relay: `backend/src/lumine/api/routers/streams.py:235-250`
- Decision cycle LLM: `backend/src/lumine/rpc/worker.py:33-215`
- Gateway async: `backend/src/lumine/llm_gateway/gateway.py:134-183`
- Committee streams: `frontend/src/hooks/useCommitteeStreams.ts`
- What-if fix: `frontend/src/lib/api/core.ts:159-167`
- Commits: `9e6730a` (latest) — 24 commits hari ini ke branch `dev`

Last Updated: 2026-08-15
