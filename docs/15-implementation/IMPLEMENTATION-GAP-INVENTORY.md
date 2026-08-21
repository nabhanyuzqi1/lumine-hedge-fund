# Implementation Gap Inventory — Backend · Frontend · General

- **Date:** 2026-08-16 (sesi lanjutan; diverifikasi terhadap source code, bukan klaim docs)
- **Status:** Active — living document; perbarui setiap kali gap ditutup
- **Progress 2026-08-15/16 (final):** **10 bug user CLOSED** (B1 MT5 positions+deals sync 18 posisi/20 orders live, B2 health count konsisten, B3 spread NaN+stream count, B4 bar garbage+live bars 1m/5m, B5 signals table+persist decision cycle, B6 SSE per-channel HMAC+relative API URL, B7 topbar responsive, B8 mt5_profit broker, B9 NormalizeSymbol+enabled_symbols, B10 LLM routing diagram) · **CI HIJAU**: frontend 170/170 vitest + TSC 0 + build, backend 574 unit + 57 contract + ruff clean, **auto-deploy VPS via GitHub Actions verified** (health 200) · **G1 PR #2 merged dev→main (0 gap)** · **G2 decision cycle scheduler otomatis** (5 menit, lock Redis) · **G3 journal pipeline** (log_step hash chain) · **G4 correlation jujur** (hanya symbol dengan data) · **G5 Autogen Studio asset routing fixed** (Gatsby absolut paths → autogenstudio; css/js 200) · **AUTH-01 CLOSED** (internal session auth) · **G-11..G-14 CLOSED** · **B-05/B-08 CLOSED** (portfolio live PostgreSQL + positions/deals MT5 sync)
- **Scope:** Phase 15/16 — backend (`backend/src/lumine/`), frontend (`frontend/src/`), general (infra/ops/CI)
- **Urutan eksekusi:** [`COMPLETION-WORKFLOW.md`](../COMPLETION-WORKFLOW.md) — backend → frontend → docker+bridge → VPS live, dengan gate per workstream

## Executive Summary (2026-08-16)

| Area | Status | Catatan |
|------|--------|---------|
| Backend API layer | 🟢 LIVE | 9 router + market cluster + RPC worker hardening + positions/deals sync MT5 real + signals persisted + decision scheduler |
| Backend AI pipeline | 🟢 HIJAU | 574 unit + 57 contract PASS; LLM decision cycle real via 9router (analyst + IC forum → signals/journal) |
| Frontend | 🟢 HIJAU | 170/170 vitest + TSC 0 + build; semua halaman zero-demo (fixture fallback nonaktif); committee streams live |
| General (infra/ops) | 🟢 HIJAU | CI 4/4 green + auto-deploy VPS; Autogen Studio UI fixed; 11/13 services healthy (2 orphan non-runtime) |

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
| B-08 | Historical data backfill TCA — **CLOSED 2026-08-22** | `trade_core/tca_backfill.py`: `backfill_missing_tca()` — outer join fills↔tca_records (idempoten), benchmark arrival dari tick store (missing = honest skip), provenance `regime_id="backfill"` + `benchmark_source="backfill:*"`, per-row isolation; test 4/4 (`test_tca_backfill.py`) | ✅ |

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
| F-09 | Bundle size analyzer + render profiler — **CLOSED 2026-08-22** | `pnpm analyze` → dist/stats.html (rollup-plugin-visualizer, gzip+brotli); profiler sudah ada (`usePerformanceMetrics` FPS/vitals/long-task) — lihat FRONTEND-IMPLEMENTATION-GAP.md item 10 | ✅ |
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
| G-03 | BLOCK-005 Security audit — **CLOSED 2026-08-22** | gitleaks full-history 541 commit + working tree 542MB = no leaks; pip-audit backend = no known vulns; npm audit (prod) = 0 vulns; CI job `secret-scan` (gitleaks-action@v2, gate deploy); dependabot.yml (pip/npm/actions weekly) | ✅ |
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


> NOTE (18 Aug 2026): AutoGen Studio TIDAK dipakai — pipeline AutoGen langsung (backend) sudah menggantikannya. Referensi di atas historis saja.
