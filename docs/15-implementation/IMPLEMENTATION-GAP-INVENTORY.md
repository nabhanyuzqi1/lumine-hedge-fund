# Implementation Gap Inventory — Backend · Frontend · General

- **Date:** 2026-08-14 (sesi lanjutan; diverifikasi terhadap source code, bukan klaim docs)
- **Status:** Active — living document; perbarui setiap kali gap ditutup
- **Progress 2026-08-14 (lanjutan):** B-01..B-07 CLOSED (679 backend tests) · W2 F-01..F-12 CLOSED (169 frontend tests) · W3 docker CLOSED · W4 LIVE http://166.88.227.177/ — 9 service: api/caddy/frontend/postgres/redis/bridge (healthy) + 9router/headroom (live, API 401 menunggu key provider) + dozzle (/dozzle, basic auth) + MT5 HFM (wine, noVNC :6901, terminal64 running) · RPC decision cycle LIVE (enqueue→worker→completed) · DR test PASS · bandit 0 High/Medium. Sisa: HTTPS (butuh domain), LLM_GATEWAY_API_KEY (provider mengisi), login akun HFM via noVNC (operasional), CI/CD pipeline (G-08), runbook darurat (G-01), backup otomatis (G-06), seed produksi, B-08 backfill.
- **Scope:** Phase 15/16 — backend (`backend/src/lumine/`), frontend (`frontend/src/`), general (infra/ops/CI)
- **Urutan eksekusi:** [`COMPLETION-WORKFLOW.md`](../COMPLETION-WORKFLOW.md) — backend → frontend → docker+bridge → VPS live, dengan gate per workstream

## Executive Summary

| Area | Status | Catatan |
|------|--------|---------|
| Backend API layer | 🟡 Partial | 9 router live + klaster market + PATCH orders + simulate (sesi ini); RPC stub, data masih demo (belum storage), 3 modul kosong |
| Backend AI pipeline | 🔴 BLOCKED | llm_gateway diimplementasi tapi 52 test pre-existing FAIL (API mismatch `Registry.__init__`) — pipeline belum hijau |
| Frontend | 🟡 Partial | Semua halaman REST-first via hooks (fallback fixture); 5 mutation REST penuh; sisa: panel UI lanjutan + 2 hook fixture-only |
| General (infra/ops) | 🔴 BLOCKED | BLOCK-001..008 Phase 16 checklist — sebagian besar belum dikerjakan (DR test, security audit, untracked services) |

Bukti audit lengkap: `docs/15-implementation/repository-audit-dev-branch.md` (sesi sebelumnya) + dokumen ini.

---

## 1. Backend — Gap

| ID | Item | Evidence | Severity |
|----|------|----------|----------|
| B-01 | Modul `backtest/` — **CLOSED 2026-08-14** | `src/lumine/backtest/engine.py` (deterministic SMA20+volume engine, metrics) | ✅ |
| B-02 | Modul `monitoring/` — **CLOSED 2026-08-14** | `src/lumine/monitoring/metrics.py` + `GET /metrics` Prometheus text | ✅ |
| B-03 | Modul `registry/` — **CLOSED 2026-08-14** | `src/lumine/registry/agents.py` (12 AgentSpec lengkap) | ✅ |
| B-04 | RPC dispatch — **CLOSED 2026-08-14** | Redis Streams producer+worker, 4 handler nyata, `GET /rpc/commands/{id}` | ✅ |
| B-05 | Storage wiring — **CLOSED (sebagian) 2026-08-14** | `DEMO_DATA` flag + OrderRepository/PositionRepository + migrasi 0011; portfolio/journal/workflows/market masih demo | 🟡 |
| B-06 | Endpoint kurang — **CLOSED 2026-08-14** | portfolio CRUD, cancel-all, history, bulk-status, signals/{symbol}, equity — contract 56/56 | ✅ |
| B-07 | 52 test llm-gateway — **CLOSED 2026-08-14** | 679 pass (registry API, migrasi, anchoring, TCA) | ✅ |
| B-08 | Historical data backfill TCA | — | 🟢 LOW |

### Backend — selesai & terverifikasi (sesi 2026-08-14)

- Klaster market 10 endpoint (`quote/quotes/ohlcv/symbol/symbols/volatility/correlation/spread/session/features`) + `POST /portfolio/{id}/simulate` + `PATCH /orders/{id}` — contract tests 53/53, E2E live 16/16
- Kill-switch + tier (persist Redis), rate-limit degrade saat Redis off, envelope validation sanitize, `MT5Bridge.from_url` await fix, `orjson` dependency fix
- `llm_gateway/` diimplementasi (11 file, admission control, model routing, fallback, budget) — **namun lihat B-07**

## 2. Frontend — Gap

| ID | Item | Evidence | Severity |
|----|------|----------|----------|
| F-01 | WorkflowRunList — **CLOSED 2026-08-14** | `/workflows` page paginated + nav detail | ✅ |
| F-02 | StreamStatusDot + GapBanner — **CLOSED 2026-08-14** | `components/streams/*` + TopBar/PageShell wiring | ✅ |
| F-03 | WhatIfPanel — **CLOSED 2026-08-14** | `components/terminal/what-if-panel.tsx` + hook | ✅ |
| F-04 | MarketIndicatorsPanel (features) + SignalPanel — **CLOSED 2026-08-14** | live endpoints, fallback fixture | ✅ |
| F-05 | AnalystCard + DecisionCard — **CLOSED 2026-08-14** | `components/dashboard/` | ✅ |
| F-06 | Volatility/spread/session indicator — **CLOSED 2026-08-14** | `useMarketIndicators` live | ✅ |
| F-07 | ExposureSummaryCard — **CLOSED 2026-08-14** | live exposure | ✅ |
| F-08 | CSV export — **CLOSED 2026-08-14** | `lib/csv.ts` + tombol Export CSV di Journal | ✅ |
| F-09 | Bundle size analyzer + render profiler | f-sprint-6 items | 🟢 LOW (tooling; build warning chunk size ada) |
| F-10 | `useCorrelation` — **CLOSED 2026-08-14** | rewire ke `GET /market/correlation` | ✅ |
| F-11 | `useEquityCurve` — **CLOSED 2026-08-14** | rewire ke `GET /portfolio/{id}/equity` | ✅ |
| F-12 | CommandPalette a11y — **CLOSED 2026-08-14** | combobox pattern (aria-expanded/controls/activedescendant), eslint 0 | ✅ |

### Frontend — selesai & terverifikasi (sesi 2026-08-14)

- Prefix `/api/v1` (normalizeApiPath di core.ts), HMAC signing (`auth.ts` sesuai auth.md, pacing anti-replay) di kedua fetch layer
- 10 query hook REST-first (fallback fixture) + 5 mutation REST (create/revoke key, cancel, modify, kill-switch) + mapper REST→fixture
- Semua 10 halaman konsumsi hooks (import fixture di halaman hanya type-only) — **klaim "halaman fixture-backed" sudah tidak akurat**
- Quality gate: typecheck 0 error, 35 files / 151 tests, build OK

## 3. General — Gap

| ID | Item | Evidence | Severity |
|----|------|----------|----------|
| G-01 | BLOCK-002 Emergency access procedures — runbook belum ditulis | `phases-15-completion-checklist.md` | 🔴 CRITICAL (Phase 16) |
| G-02 | BLOCK-003 DR restore test — **CLOSED 2026-08-14** (dump→restore 32 tabel PASS di VPS) | verifikasi sesi ini | ✅ |
| G-03 | BLOCK-005 Security audit — **sebagian**: bandit 0 High/0 Medium (2026-08-14); audit penuh (gitleaks, dependensi, config) belum | verifikasi sesi ini | 🟡 |
| G-04 | BLOCK-001 Untracked services: 9router (butuh API key), headroom, dozzle — compose belum | `phases-15-completion-checklist.md` Gap 1 | 🟠 HIGH |
| G-05 | BLOCK-004 Secrets management partial (Authelia session/storage keys tidak terdokumentasi) | `phases-15-completion-checklist.md` Gap 2 | 🟠 HIGH |
| G-06 | BLOCK-006 Landing page sync belum automated; BLOCK-007 backup manual only; BLOCK-008 health monitoring none | `phases-15-completion-checklist.md` | 🟠 HIGH |
| G-07 | VPS↔repo alignment 75% (env template, emergency docs, CI/CD partial) | `phase-16-readiness-roadmap.md` | 🟠 HIGH |
| G-08 | CI partial — docs.yml, supply-chain.yml ada; deployment pipeline belum terverifikasi end-to-end | `docs/15-implementation/README.md:19` | 🟡 MEDIUM |

## 4. Knowledge sync — item yang sudah dikoreksi (2026-08-14)

Dokumen berikut diperbarui agar sinkron dengan realitas kode:

| Doc | Koreksi |
|-----|---------|
| `FRONTEND-IMPLEMENTATION-GAP.md` | Section "Backend → Frontend Alignment — Resolved" (sesi sebelumnya) + sesi ini |
| `FRONTEND-BACKEND-ROADMAP-CHECKPOINT.md` | Progress Update urutan kerja #1–#4 |
| `FRONTEND-API-SPECS.md` | Tabel rekonsiliasi vs backend live → semua item resolved |
| `docs/09-api/rest-api.md` | Section "Implemented Surface Reconciliation" — drift kontrak didokumentasikan |
| `docs/15-implementation/README.md` | Status table: llm_gateway/mt5 bukan scaffold lagi; test counts baru; outstanding items dikoreksi |
| `docs/15-implementation/spec-reconciliation.md` | Baris LLM gateway → implemented |
| `f-sprint-4-charts.md`, `f-sprint-5-surfaces.md` | Catatan status backend live |
| `CLAUDE.md` | Baris tabel Phase 15 disinkronkan |
| `deviation-log.md` | Baris deviasi API surface (market path, rpc, pagination) |

---

**End of Document**
