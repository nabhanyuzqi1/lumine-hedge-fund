# Lumine Completion Workflow — Backend → Frontend → VPS Live

- **Date:** 2026-08-14
- **Status:** Active — rencana eksekusi terurut; setiap workstream punya gate verifikasi wajib
- **Progress 2026-08-14 (lanjutan):** W1.1 ✅ (B-07, suite 661 pass) · W2 partial ✅ (F-01 WorkflowRunList, F-02 StreamStatusDot/GapBanner, F-03 WhatIf, F-10 correlation; 161 tests) · W3 ✅ (stack docker 6/6 healthy, E2E 16/16) · W4 v1 ✅ **LIVE http://166.88.227.177/** (Docker 29.7.2, 6 service, key web-frontend, 8/8 smoke; sisa: mt5-wine, 9router, HTTPS, DR, security audit)
- **Source of truth gap:** `docs/15-implementation/IMPLEMENTATION-GAP-INVENTORY.md` (B-01..B-08, F-01..F-12, G-01..G-08)
- **Skills pendukung:** 14 skill kategori `claude-skills` (installed 2026-08-14) — dipetakan per workstream

---

## Executive Summary

Urutan eksekusi: **stabilkan backend → selesaikan frontend → docker + MT5 bridge (WSL lokal) → live VPS**. Tiap workstream ditutup dengan quality gate yang dijalankan (bukan klaim). Blocker kualitas pertama (B-07: 52 test llm-gateway gagal) dikerjakan paling awal karena menghalangi semua gate backend.

```
W1 Backend stabilization ──► W2 Frontend completion ──► W3 Docker+Bridge (WSL) ──► W4 VPS Live
        │ gate: suite hijau         │ gate: typecheck/test/build  │ gate: stack health      │ gate: health+monitoring+DR
        └──────────────► setiap akhir workstream: sync docs (gap inventory + deviation-log)
```

---

## Workstream 1 — Backend Stabilization

**Gate keluar:** `pytest` backend full suite HIJAU (0 failure), contract 53/53 tetap, ruff + mypy bersih pada file yang diubah.

| # | Task | Gap | Detail | Skill |
|---|------|-----|--------|-------|
| 1.1 | Perbaiki 52 test failure llm-gateway/prompt-registry | B-07 | Selaraskan `Registry.__init__` (signature `base_path`), `PromptBundle.model_tier_hint`, `autogen_pipeline/__init__` exports dengan konsumen (`test_prompts_registry.py`, `test_orchestrator.py`, `test_analysts.py`, `tests/system/test_decision_cycle.py`) | code-reviewer, strict-api |
| 1.2 | RPC dispatch nyata | B-04 | Ganti stub `_accept` dengan Redis Streams (listener worker + command handler); `run-decision-cycle` trigger orchestrator sungguhan; kill-switch gate di worker | docker-development (redis), api-test-suite-builder |
| 1.3 | Wire domain routers ke storage | B-05 | Repository layer SQLAlchemy untuk orders/portfolio/journal/workflows/lineage/market (migrasi 0001–0009 sudah ada); flag `DEMO_DATA=true` (default dev) mempertahankan data demo saat storage off | database-schema-designer, strict-api |
| 1.4 | Endpoint REST yang kurang | B-06 | portfolio CRUD (`/portfolios`), `DELETE /portfolio/{id}/orders`, `GET /orders/{id}/history`, `GET /orders/bulk/status`, `GET /market/signals/{symbol}`, equity curve; contract tests menyertai | api-design-reviewer, api-test-suite-builder |
| 1.5 | Modul `backtest/` | B-01 | Implementasi minimal: replay decision-cycle atas data historis (deterministik) + `make backtest` hijau | — |
| 1.6 | Modul `monitoring/` | B-02 | `prometheus_client` metrics (request, LLM cost, execution) + tracing hooks; dipakai W4.4 | observability-designer |
| 1.7 | Agent registry typed | B-03 | `registry/` → `AgentSpec` typed (nama, prompt ref, model tier, failure mode) | — |

**Verifikasi:** jalankan ulang E2E smoke (`backend/e2e_smoke.py`) + contract suite; dokumentasikan hasil di gap inventory.

---

## Workstream 2 — Frontend Completion

**Gate keluar:** `tsc --noEmit` 0 error, `vitest run` hijau, `vite build` sukses, audit a11y (axe) 0 critical.

| # | Task | Gap | Detail | Skill |
|---|------|-----|--------|-------|
| 2.1 | Rewire `useCorrelation` ke `GET /market/correlation` | F-10 | Termurah; backend sudah live | strict-api |
| 2.2 | WorkflowRunList paginated + navigasi run detail | F-01 | Atas `GET /workflows` (PaginatedList) | — |
| 2.3 | StreamStatusDot per-stream + GapBanner | F-02 | Konsumsi 6 channel SSE; gap detection dari `stream_resumed` | — |
| 2.4 | What-if simulate panel | F-03 | `useSimulateTrade` + `POST /portfolio/{id}/simulate`; projected NAV/margin/P&L cards | api-test-suite-builder |
| 2.5 | FeaturePanel + SignalPanel | F-04 | `features/{symbol}` live; signals tunggu W1.4 per-symbol | — |
| 2.6 | AnalystCard + DecisionCard | F-05 | Confidence meter + navigasi lineage/run | — |
| 2.7 | Volatility/spread/session indicators + ExposureSummaryCard | F-06, F-07 | Semua endpoint live | — |
| 2.8 | a11y CommandPalette (7 errors) | F-12 | Axe audit + fix; fokus ring + contrast | a11y-audit |
| 2.9 | Bundle analyzer + render profiler | F-09 | Vite manualChunks (chunk >500 kB saat ini), React Profiler pada chart pane | performance-profiler |

**Verifikasi:** gate di atas + smoke manual via browser (halaman utama dengan backend lokal hidup).

---

## Workstream 3 — Docker + MT5 Bridge (Lokal, WSL)

**Gate keluar:** `docker compose up` dari nol → semua service healthy → `/health` + 1 endpoint domain → migrasi alembic sukses → smoke E2E di dalam container.

| # | Task | Detail | Skill |
|---|------|--------|-------|
| 3.1 | Validasi `backend/docker-compose.yml` (postgres, redis, caddy, api) | Jalankan; perbaiki Dockerfile (multi-stage, non-root, layer caching); tambah healthcheck frontend | docker-development |
| 3.2 | Dockerfile frontend + service `frontend` | Vite build → nginx/caddy serve; env `VITE_API_URL` via compose | docker-development |
| 3.3 | Service `mt5-bridge` | Container untuk `trading/mt5_bridge.py` + `position_sync.py` + `MarketService`; publish tick ke Redis → API/SSE; koneksi MT5 di-gate (demo mode saat tidak ada terminal MT5) | docker-development, observability-designer |
| 3.4 | Migrasi + seed | `alembic upgrade head` sebagai step entrypoint; seed portfolio default | database-schema-designer |
| 3.5 | E2E container | Jalankan `backend/e2e_smoke.py` terhadap service `api` dalam compose (auth HMAC via env) | api-test-suite-builder |

**Catatan WSL:** Docker Desktop 4.86 + WSL2 Ubuntu AKTIF — compose lokal berjalan langsung di Windows.

---

## Workstream 4 — VPS Live (Phase 16 handoff)

**Gate keluar:** semua BLOCK-001..008 tertutup; deploy blue-green sukses; DR restore teruji; security scan (trivy/gitleaks/bandit) bersih; monitoring ≥95% jalur kritis.

| # | Task | Gap | Detail | Skill |
|---|------|-----|--------|-------|
| 4.1 | Tutup blocker infra | G-01..G-08 | Emergency runbook, DR restore test, security audit internal (pertama kali), Authelia secrets, .env template lengkap | ai-security, cloud-security |
| 4.2 | Compose prod lengkap | G-04 | `docker-compose.prod.yml` + service 9router (port 20128), headroom (8787), dozzle (/logs/), mt5-bridge; Caddy TLS | docker-development, senior-devops |
| 4.3 | CI/CD | G-08 | GitHub Actions: build → test → scan → deploy staging → blue-green prod + rollback <5 mnt | ci-cd-pipeline-builder, senior-devops |
| 4.4 | Observability prod | G-06 | Prometheus + Grafana (sistem, trade, LLM cost) + Loki + Alertmanager; dead man's switch | observability-designer |
| 4.5 | Deployment & verifikasi live | — | Deploy ke VPS (per `docs/16-implementation/`); health checks, TLS, rate limit live, kill-switch drill | senior-devops |

**Handoff:** hasil W4 masuk ke `docs/16-implementation/phase-16-tracking-checklist.md` (centang per item).

---

## Risiko & Keputusan

| Keputusan | Opsi | Pilihan | Alasan |
|-----------|------|---------|--------|
| RPC queue | Celery vs Redis Streams | **Redis Streams** | Tanpa infra baru; Redis sudah wajib; worker ringan dalam proses API |
| Data demo vs storage | Flag `DEMO_DATA` | **Flag env, default true di dev** | Router tetap hidup tanpa Postgres; W1.3 migrasi bertahap per domain |
| Portfolio multi vs single | — | **Single (default) tetap V1** | Backend + frontend sudah selaras; CRUD W1.4 menambah `{id}` tanpa mengubah perilaku default |
| MT5 bridge live vs demo | Gate koneksi | **Demo-mode saat terminal MT5 tidak tersedia** | Integritas pipeline terjaga; fill synthetic berlabel jelas di journal |
| Deploy strategy | blue-green vs rolling | **Blue-green** (sesuai checklist Phase 16) | Rollback cepat <5 mnt; auditability |

## Disiplin Doc Sync (setiap akhir workstream)

1. Update `IMPLEMENTATION-GAP-INVENTORY.md` — tandai gap tertutup (✅ + bukti gate).
2. Update `docs/15-implementation/README.md` status table + `spec-reconciliation.md` bila klaim berubah.
3. `deviation-log.md` — hanya jika ada deviasi baru dari spec.
4. `docs/09-api/openapi.yaml` — regenerasi + contract test setelah perubahan router (W1.4).
5. Verifikasi independen per CLAUDE.md rule 8: code-reviewer/adversarial-reviewer pada PR besar.

---

**End of Document**
