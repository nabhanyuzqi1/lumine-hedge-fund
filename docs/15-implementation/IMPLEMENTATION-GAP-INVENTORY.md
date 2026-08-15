# Implementation Gap Inventory — Backend · Frontend · General

- **Date:** 2026-08-14 (sesi lanjutan; diverifikasi terhadap source code, bukan klaim docs)
- **Status:** Active — living document; perbarui setiap kali gap ditutup
- **Progress 2026-08-14 (final):** B-01..B-07 CLOSED (679 backend tests) · W2 F-01..F-12 CLOSED (172 frontend tests) · W3 docker CLOSED · W4 LIVE https://lumine.biz.id (Cloudflare Flexible SSL, domain aktif) · G-01 CLOSED (EMERGENCY-RUNBOOK.md 11 seksi) · G-06 CLOSED (backup-postgres+health-check+resource-watchdog cron) · G-08 CLOSED (.github/workflows/ci.yml + GitHub secrets VPS_HOST+VPS_SSH_KEY, CI 4/4 green termasuk Deploy→VPS) · G-07 CLOSED (DNS router.lumine.biz.id accessible) · **AUTH-01 CLOSED — internal session auth**: users table (0012), PBKDF2, cookie Secure, Caddy forward_auth, backend 698 pass · **G-11..G-14 CLOSED** (auth router, landing Linear+shadcn, terminal Bloomberg SSE, superadmin rebuild) · **G-05 CLOSED — secrets rotated** (password produksi baru di .env VPS, rotate_users.py, old pw 401 verified) · **LLM_GATEWAY_API_KEY SET** (9router v0.5.55+ updated, key sk-fc79… live, /v1/models 200) · **B-05 portfolio CLOSED** (summary+equity dari live PostgreSQL, fallback deterministic saat DB down) · **UI/UX overhaul** (terminal tanpa header duplikat + responsive, dashboard bounded scroll, health rebuild probes+SSE, journal header mono, rail role-gated tooltip, vite base '/', nginx cache headers, dozzle DOZZLE_BASE, noVNC single-login WS autoconnect) · **G-03 partial → gitleaks 0 leak (149 commits) + ruff 851→0 + bandit 0H/0M** · **B-09 MT5 EA bridge COMPLETE**: LumineEA.mq5 HTTP transport (WebRequest → Caddy /mt5-proxy → redis-http-proxy → Redis), OrderSend OPEN/CLOSE/MODIFY, ticks → mt5:ticks, EA auto-attach persist (backup workspace .chr + restore entrypoint), **E2E order flow FULLY WORKING** (POST /orders → bridge → EA → MT5 FILLED → DB sync status+volume+ticket; DEMO_DATA=0 production) · **SEED COMPLETE**: EA InpSeedHistory CopyRates M1/H1 5000 bars → seed_worker → bars_1m/1h; /market/bars+ohlcv DB-backed (fallback demo) · **B-08 TCA backfill CLOSED**: seed_production.py (registry versions + brokers/accounts + 5 fills/tca/lineage, benchmark arrival_mid, fill_price sync) · **CI VERIFIED 4/4 green** (backend lint/test, frontend build, Deploy→VPS) · **SECURITY AUDIT**: npm 0 vuln, pip-audit clean, bandit 0H/0M, Caddy HSTS+Permissions-Policy deployed · Sisa minor: bars_1d kosong (EA err 4401 — history D1 tidak ada di cache MT5), useDemoStreams cleanup, bundle code-split.
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
|| B-05 | Storage wiring — **CLOSED (portfolio) 2026-08-14** | `DEMO_DATA` flag + OrderRepository/PositionRepository + migrasi 0011; orders+positions DB-backed; **portfolio summary+equity live dari PostgreSQL** (`_real_summary`/`_real_equity_series`, fallback deterministic saat DB down); sisa: B-08 backfill TCA + realized pnl attribution | 🟡 |
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
| G-01 | BLOCK-002 Emergency access procedures — **CLOSED 2026-08-14** | `docs/15-implementation/EMERGENCY-RUNBOOK.md` (11 seksi: SSH, kill-switch, rollback, DR, secrets recovery) | ✅ |
| G-02 | BLOCK-003 DR restore test — **CLOSED 2026-08-14** (dump→restore 32 tabel PASS di VPS) | verifikasi sesi ini | ✅ |
| G-03 | BLOCK-005 Security audit — **sebagian**: bandit 0 High/0 Medium (2026-08-14); audit penuh (gitleaks, dependensi, config) belum | verifikasi sesi ini | 🟡 |
| G-04 | BLOCK-001 Untracked services — **CLOSED**: 9router+headroom di docker-compose.prod.yml; dozzle di vps.yml; semua terdokumentasi | compose files + EMERGENCY-RUNBOOK.md | ✅ |
|| G-05 | BLOCK-004 Secrets management — **CLOSED 2026-08-14** | Password bootstrap produksi di-rotate (`scripts/rotate_users.py` + env di compose api/migrate; old password 401, new 200 — verified); gitleaks 0 leak (149 commits); `GITHUB-SECRETS-SETUP.md` ada | ✅ |
||| G-15 | LLM gateway key — **CLOSED 2026-08-14** | `LLM_GATEWAY_API_KEY` terisi di `.env` VPS (sk-fc79…), 9router updated (v0.5.55+, image baru), `/v1/models` dengan key → 200 | ✅ |
||| G-16 | UI/UX overhaul — **CLOSED 2026-08-14** | terminal: header duplikat dihapus (CommandBar jadi header) + responsive + keyboard; dashboard: grid bounded-height + signal panel max-h (scroll internal); health: rebuild (API probes latency + SSE status); journal: header Bloomberg mono + tabel bounded; rail: tooltip + role-gated superadmin + label mobile | ✅ |
| G-06 | BLOCK-006/007/008 Backup+health monitoring — **CLOSED 2026-08-14** | `backend/scripts/`: backup-postgres.sh (pg_dump daily retensi 7h), health-check.sh (9 container+4 HTTP, throttled alerts), resource-watchdog.sh (disk/mem/backup freshness), cron aktif VPS all-checks-passed | ✅ |
|| G-07 | VPS↔repo alignment — **CLOSED 2026-08-14** | env template, CI/CD pipeline, emergency docs, GitHub secrets VPS_HOST+VPS_SSH_KEY configured, DNS `router.lumine.biz.id` accessible; sisa: runner CI belum verified (manual test OK) | `GITHUB-SECRETS-SETUP.md` | ✅ |
|| G-08 | CI/CD pipeline — **CLOSED 2026-08-14** | `.github/workflows/ci.yml` (backend-test+lint, frontend-test+build, deploy SSH ke VPS on push dev) + GitHub secrets VPS_HOST+VPS_SSH_KEY configured | ✅ |
||| G-09 | ~~Keycloak SSO~~ — **SUPERSEDED 2026-08-14** | Diganti AUTH-01 internal session auth; Keycloak + Authelia dihapus dari VPS (compose, env, config dir, containers) | ✅ |
||| G-10 | Logout UI — **CLOSED 2026-08-14** | TopBar logout button + username display; `useAuth()` + `logout()` → POST /api/auth/logout (cookie clear) + redirect `/login`; tests 169/169 pass | ✅ |
||| G-11 | **AUTH-01 internal session auth — CLOSED 2026-08-14** | `backend/src/lumine/api/routers/auth.py` (POST /login, POST /logout, GET /me, GET /verify role-gated) · `users` table migrasi 0012 · PBKDF2-HMAC-SHA256 + salt per user · seed bootstrap superadmin/admin/trader idempotent (lifespan) · fallback env saat DB down · cookie `lumine_session` HttpOnly HMAC-signed · Caddy `forward_auth` → `/api/auth/verify?role=…` melindungi /superadmin, /novnc, /dozzle (401 → redirect /login) · 17 test baru (`tests/unit/test_auth.py`) · contract 57/57 | ✅ |
||| G-12 | Landing page rebuild — **CLOSED 2026-08-14** | `frontend/src/app/pages/landing-public.tsx` (Linear design system: luminance-stacked dark canvas, translucent borders, compressed display tracking) di atas ui kit shadcn (Button/Badge/Card) — hero + terminal mock + stats + features + agent hierarchy + security + CTA + footer | ✅ |
||| G-13 | Bloomberg terminal rebuild — **CLOSED 2026-08-14** | `frontend/src/app/pages/terminal.tsx` — command bar + keyboard shortcuts (`/` focus symbol, 5/15/60/240 timeframe) + ticker tape + live SSE market-data (HMAC-signed fetch, `useSSE`) menggantikan `useDemoStreams`; teks demo dihapus; hook positions/orders tidak lagi fallback fixture saat API return empty | ✅ |
||| G-14 | Superadmin rebuild — **CLOSED 2026-08-14** | `frontend/src/app/pages/superadmin.tsx` — AutheliaGuard dihapus, demo fallback system-info dihapus (error banner real), `useUpdateConfig` diperbaiki dari GET mock → `PUT /admin/system-config` (fungsi `put` baru di `api/client.ts`), link 9router → `router.lumine.biz.id` | ✅ |

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
