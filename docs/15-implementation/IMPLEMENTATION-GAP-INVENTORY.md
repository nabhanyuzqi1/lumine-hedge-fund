# Implementation Gap Inventory — Backend · Frontend · General

- **Date:** 2026-08-14 (sesi lanjutan; diverifikasi terhadap source code, bukan klaim docs)
- **Status:** Active — living document; perbarui setiap kali gap ditutup
- **Progress 2026-08-14 (lanjutan):** B-01..B-07 CLOSED (679 backend tests) · W2 F-01..F-12 CLOSED (169 frontend tests) · W3 docker CLOSED · W4 v1 LIVE http://166.88.227.177/ (8/8 smoke) + DR test PASS + bandit 0 High/Medium + mt5-wine build in progress. Sisa: W4 (HTTPS butuh domain, 9router butuh API key, login MT5 via noVNC operasional), seed script produksi, historical backfill TCA (B-08), CI/CD pipeline (G-08).
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
| B-01 | Modul `backtest/` kosong (scaffold, 0 file selain `__init__.py`) | `backend/src/lumine/backtest/` | 🟡 MEDIUM — roadmap punya `make backtest` (Makefile:110) yang akan gagal |
| B-02 | Modul `monitoring/` kosong — metrics aggregation (Prometheus) + distributed tracing belum ada | `backend/src/lumine/monitoring/`; README outstanding #5 | 🟡 MEDIUM (Phase 16 observability) |
| B-03 | Modul `registry/` kosong — agent registry typed spec belum (README outstanding #3) | `backend/src/lumine/registry/` | 🟢 LOW |
| B-04 | RPC = stub: 4 command (`run-decision-cycle`, `halt-trading`, `resume-trading`, `cancel-order`) hanya balas `accepted`, tidak dispatch ke worker/queue | `routers/rpc.py:43-90` | 🟠 HIGH — kontrol operasional tidak melakukan apa-apa di balik receipt |
| B-05 | Semua router domain masih demo-data in-memory (kecuali admin keys/kill-switch/rate-limit yang pakai Redis) — belum baca dari PostgreSQL | `routers/orders.py:25` dst. | 🟠 HIGH — data tidak persisten; Phase 5 storage belum diwire |
| B-06 | Endpoint yang belum ada (frontend sudah siap): portfolio CRUD (`GET/POST /portfolios`, `PUT/DELETE /portfolio/{id}`), `DELETE /portfolio/{id}/orders` (cancel-all), `GET /orders/{id}/history`, `GET /orders/bulk/status`, signals per-symbol (saat ini global), equity curve | `portfolioClient.ts`, `ordersClient.ts`, `hooks.ts:useSignals` | 🟡 MEDIUM |
| B-07 | 52 test failure pre-existing di area llm-gateway/prompt-registry (`Registry.__init__() unexpected kwarg base_path`, `PromptBundle.model_tier_hint` hilang) — refactor in-flight belum konsisten | `tests/unit/test_prompts_registry.py`, `test_orchestrator.py`, `test_analysts.py`, `tests/system/test_decision_cycle.py` | 🔴 CRITICAL — quality gate backend tidak hijau |
| B-08 | Historical data backfill untuk TCA belum (README outstanding #4) | — | 🟢 LOW |

### Backend — selesai & terverifikasi (sesi 2026-08-14)

- Klaster market 10 endpoint (`quote/quotes/ohlcv/symbol/symbols/volatility/correlation/spread/session/features`) + `POST /portfolio/{id}/simulate` + `PATCH /orders/{id}` — contract tests 53/53, E2E live 16/16
- Kill-switch + tier (persist Redis), rate-limit degrade saat Redis off, envelope validation sanitize, `MT5Bridge.from_url` await fix, `orjson` dependency fix
- `llm_gateway/` diimplementasi (11 file, admission control, model routing, fallback, budget) — **namun lihat B-07**

## 2. Frontend — Gap

| ID | Item | Evidence | Severity |
|----|------|----------|----------|
| F-01 | WorkflowRunList paginated + navigasi run detail | backend `GET /workflows` live; UI belum | 🟠 HIGH |
| F-02 | StreamStatusDot per-stream + GapBanner (saat ini hanya agregat n/6 di TopBar) | `top-bar.tsx:36` | 🟠 HIGH |
| F-03 | What-if simulate panel (backend `POST /portfolio/{id}/simulate` live; `useSimulateTrade` siap; UI belum) | `usePortfolio.ts:useSimulateTrade` | 🟡 MEDIUM |
| F-04 | FeaturePanel (`features/{symbol}` live) + SignalPanel (backend masih global, bukan per-symbol) | `hooks.ts:useSignals` | 🟡 MEDIUM |
| F-05 | AnalystCard + DecisionCard | — | 🟡 MEDIUM |
| F-06 | Volatility badge, spread alert, session indicator (backend live semua) | `marketClient` getVolatility/getSpreadMetrics/getSessionData | 🟢 LOW |
| F-07 | ExposureSummaryCard per-sektor (backend exposure live) | — | 🟢 LOW |
| F-08 | CSV export transactions (backend endpoint juga belum ada) | `portfolioClient.exportTransactions` | 🟢 LOW |
| F-09 | Bundle size analyzer + render profiler | f-sprint-6 items | 🟢 LOW |
| F-10 | `useCorrelation` masih fixture-only — backend `GET /market/correlation` SUDAH live; hook bisa di-rewire | `hooks.ts:useCorrelation` | 🟡 MEDIUM |
| F-11 | `useEquityCurve` fixture-only — backend equity endpoint belum ada (lihat B-06) | `hooks.ts:useEquityCurve` | 🟢 LOW |
| F-12 | CommandPalette a11y (7 errors) + useExhaustiveDependencies | pre-existing, bukan regresi | 🟢 LOW |

### Frontend — selesai & terverifikasi (sesi 2026-08-14)

- Prefix `/api/v1` (normalizeApiPath di core.ts), HMAC signing (`auth.ts` sesuai auth.md, pacing anti-replay) di kedua fetch layer
- 10 query hook REST-first (fallback fixture) + 5 mutation REST (create/revoke key, cancel, modify, kill-switch) + mapper REST→fixture
- Semua 10 halaman konsumsi hooks (import fixture di halaman hanya type-only) — **klaim "halaman fixture-backed" sudah tidak akurat**
- Quality gate: typecheck 0 error, 35 files / 151 tests, build OK

## 3. General — Gap

| ID | Item | Evidence | Severity |
|----|------|----------|----------|
| G-01 | BLOCK-002 Emergency access procedures — missing | `phases-15-completion-checklist.md` | 🔴 CRITICAL (Phase 16) |
| G-02 | BLOCK-003 DR restore test — never performed | `phases-15-completion-checklist.md` | 🔴 CRITICAL (Phase 16) |
| G-03 | BLOCK-005 Security audit — never performed | `phases-15-completion-checklist.md` | 🔴 CRITICAL (Phase 16) |
| G-04 | BLOCK-001 Untracked services: 9router, headroom, dozzle — tidak ada compose file di repo | `phases-15-completion-checklist.md` Gap 1 | 🟠 HIGH |
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
