# Runtime Topology

## Overview

Phase 11 operationalizes the Phase 1 `deployment-topology.md` contract. The
11 Phase 1 services are unchanged; Phase 11 adds 4 infrastructure components
(Caddy, observability stack, OTel collector, backup sidecar) and one
external runtime dependency (Vercel, frontend only).

## Full runtime layout (V1)

```
Internet
  │
  ├─ HTTPS :443 ──► Caddy (TLS termination, reverse proxy)
  │                   ├─ /api/*      → lumine-trade-core (REST, Phase 9)
  │                   ├─ /streams/*  → lumine-trade-core (SSE, Phase 9)
  │                   └─ /grafana/*  → grafana (IP allowlist, operator only)
  │
  ├─ MT5 server ◄── lumine-mt5-bridge            (egress, Phase 1 unchanged)
  ├─ 9router/LLM ◄── lumine-llm-gateway          (egress, Phase 1 unchanged)
  ├─ Public news ◄── lumine-news-adapter         (egress, Phase 1 unchanged)
  └─ Backup ◄── backup-sidecar → rclone(crypt) → B2/S3   (egress NEW, D11-5)

VPS (single Linux node, Docker Compose v2)
├─ caddy                    (Zone 5, edge — the only public ports :80/:443)
├─ lumine-trade-core        (Zone 1, critical path — 1 instance)
├─ lumine-mt5-bridge        (Zone 2, isolated — 1 instance)
├─ lumine-research-worker   (Zone 3, async)
├─ lumine-review-worker     (Zone 3, async)
├─ lumine-sandbox-worker    (Zone 3, async)
├─ lumine-scheduler         (Zone 5, deterministic)
├─ lumine-llm-gateway       (Zone 4)
├─ lumine-news-adapter      (Zone 5)
├─ postgres                 (Zone 5, volume: pgdata)
├─ redis                    (Zone 5, volume: redis-aof)
├─ prometheus               (Zone 5, volume: prom-data)
├─ loki                     (Zone 5, volume: loki-data)
├─ tempo                    (Zone 5, volume: tempo-data)
├─ otel-collector           (Zone 5)
├─ grafana                  (Zone 5, volume: grafana-data)
└─ backup-sidecar           (Zone 5, cron container)

Frontend (outside VPS)
└─ Vercel — production domain only
   Browser → HTTPS → Caddy → lumine-trade-core
   CORS allowlist: Vercel production origin (D11-1)
```

## Deployed services (ground truth 2026-08-12)

13 containers across 3 compose roots (label `com.docker.compose.project.config_files`
is the source of truth):

| Compose root | Services |
|---|---|
| `/srv/control-plane/` | caddy, authelia, homepage, uptime-kuma, landing, dozzle (6) |
| `/opt/lumine/backend/` | postgres, redis, api, mt5, headroom, 9router (6) |
| `/opt/hermes/hermes-agent/` | hermes (1) |

Backup (see `../infrastructure/` + `scripts/deploy/backup.sh`): daily at
02:00 WIB via cron `/usr/local/bin/lumine-backup.sh`, retention 7 days.
Covers Postgres dump, Redis RDB, 9router volume, hermes `/root/.hermes`
(cache excluded), authelia TOTP db + users_database.yml, uptime-kuma
kuma.db, caddy certs. MT5 is recreate-only (no data backup, 2026-08-12).

## Deployed control plane (2026-08-07 → diperbarui 2026-08-09, ADR-0069 / D11-7)

Interim state before the V1 services above land: the VPS runs the
already-deployed Sprint services (Hermes, Lumine backend, MT5, 9router)
behind one `control-plane` Compose stack:

```
Internet :80/:443  ← satu-satunya entry publik (plus pengecualian :20128)
  └─ Caddy (host network, tls internal → Let's Encrypt saat domain ada)
       ├─ /           → landing page nginx CONTAINER 127.0.0.1:8080  (PUBLIK — marketing)
       ├─ /site*      → alias landing page 127.0.0.1:8080  (PUBLIK — legacy)
       ├─ /auth*      → Authelia 127.0.0.1:9091      (login + TOTP, bebas auth)
       ├─ /portal*    → Homepage 127.0.0.1:3000      (hub pasca-login; strip /portal via route{})
       ├─ /hermes*    → 127.0.0.1:9119               (Hermes dashboard)
       ├─ /mt5/*      → 127.0.0.1:6901               (noVNC MT5)
       ├─ /websockify* → 127.0.0.1:6901              (WS noVNC — path absolut client)
       ├─ /backend*   → 127.0.0.1:8000               (Lumine API)
       ├─ /status* → 127.0.0.1:3001 (Kuma; auth sebelum strip — route{})
       ├─ /dashboard* → 127.0.0.1:3001 (redirect root Kuma → /dashboard, TANPA strip)
       ├─ /assets*, /socket.io → 127.0.0.1:3001 (Uptime Kuma)
       ├─ /api/badge*, /api/entry-page*, /api/push*, /api/status-page*
       │     → 127.0.0.1:3001 (4 path frontend Kuma)
       ├─ /api* lainnya → 127.0.0.1:3000 (Homepage — hydration grid)
       ├─ /_next* → 127.0.0.1:3000 (asset Next.js Homepage — JS/CSS
       │     portal; tanpa route ini portal tampil tanpa CSS)
       ├─ @landing → 127.0.0.1:8080 (PUBLIK — /assets/*, /favicon.svg
       │     + Referer dari halaman / atau /site/; split via named matcher)
       └─ catch-all → 404 "Not Found"
  Asset absolut Hermes (/assets/*, /api/*, /socket.io/*, /favicon.ico)
  dipisahkan via named matcher Referer (header_regexp dari halaman
  /hermes/ → 9119; tanpa Referer → Kuma/Homepage) — insiden 2026-08-08
  dashboard blank, lihat docs/11-infrastructure/control-plane.md.
  Asset landing (/assets/*, /favicon.svg) dipisahkan serupa — Referer
  dari halaman / atau /site/ → 8080 sebelum handle /assets* Kuma,
  tanpa ini landing tampil tanpa CSS (insiden 2026-08-09).
  Semua route (kecuali /auth*, / dan /site* — halaman publik) →
  forward_auth → Authelia
  Login tunggal: Uptime Kuma disableAuth=1 (auth internal mati) —
  cukup login Authelia sekali untuk semua dashboard (2026-08-08).
  Route dengan strip prefix (/portal*, /hermes*, /mt5*, /backend*,
  /status*) pakai route{} supaya forward_auth jalan SEBELUM strip —
  adapter Caddy meng-reorder strip lebih dulu pada handle biasa →
  rd= Authelia salah (insiden 2026-08-09). Kuma redirect root
  "/" → /dashboard (Location tunggal — jangan override, Safari tolak
  redirect ganda; /dashboard* tanpa strip → infinite loop) — insiden
  2026-08-08, lihat control-plane.md.
  Landing container (2026-08-09): control-landing nginx:alpine bridge
  127.0.0.1:8080:80 ro-mount /var/www/lumine; host nginx dinonaktifkan
  — semua service di jalur publik kini container (11/11). Logout:
  header portal → /auth/logout?rd=... (session Authelia berakhir).
```

- Upstream loopback: `8000`, `5900`, `6901`, `9119`, `9091`, `3000`
  (Homepage), `3001` (Uptime Kuma). UFW `3000/tcp` dan `3001/tcp`
  tetap DENY sebagai defense-in-depth. Hanya Caddy yang terjangkau
  eksternal.
- **Pengecualian tersurat (HARD INVARIANT):** `9router` adalah satu-
  satunya service selain Caddy yang bind host port publik: `0.0.0.0:20128`
  (plain HTTP). Agent eksternal connect langsung via IP
  `http://166.88.227.177:20128`. **Tidak boleh ada service lain yang bind
  `*:20128`.** Caddy menyediakan endpoint HTTPS alternatif di
  `https://166.88.227.177:8443/v1` (reverse-proxy ke internal
  Docker IP `9router`), yang tidak boleh dipindah ke `:20128`. Lihat
  `control-plane.md` untuk rincian insiden port ownership 2026-08-07 dan
  2026-08-10.
- Kompatibilitas ke depan: ketika V1 service Phase 15 masuk, Caddy cukup
  menambah route `/api/*`, `/streams/*` → `lumine-trade-core` dan
  `/grafana/*` (allowlist IP) — struktur control plane tidak berubah.
- Detail arsitektur, klasifikasi VNC per service, dan panduan menambah
  service GUI baru: `docs/11-infrastructure/control-plane.md`.

## Binding rules

1. **Single public entrypoint.** Only Caddy binds public `:80/:443`. No
   other container publishes ports to the host's public interface. All
   inter-service traffic stays on the private Docker bridge network
   (Phase 1 contract). — *Explicit exception (2026-08-07, ADR-0069):
   `9router` binds `0.0.0.0:20128`; external AI agents connect by IP and
   depend on it. Revisit with mTLS/IP allowlist when a domain lands.*
2. **Grafana is not public.** `/grafana/*` is served only to allowlisted
   operator IPs — operational dashboards expose fund state and must not be
   world-reachable.
3. **Instance invariants preserved.** `lumine-trade-core` and
   `lumine-mt5-bridge` remain single-instance (Phase 1: lineage
   single-writer + MT5 single-connection constraints). Compose declares
   them with the highest CPU/memory priority; workers may be throttled.
4. **Resource limits declared per service** in the compose file (Phase 1
   policy). V1 sizing baseline: 4 vCPU / 8 GB RAM / 160 GB SSD — an
   estimate to be tuned after real-load profiling; not a contract.
5. **Restart policies unchanged from Phase 1:** `unless-stopped` for
   infrastructure, `on-failure` for workers. Trade-core restart resumes
   from PostgreSQL state; open orders always carry broker-side SL/TP.
6. **Failure semantics unchanged from Phase 1:** Postgres or Redis
   unavailability halts new trading decisions (no lineage, no trade);
   bridge crash → safe state, existing positions managed via broker-side
   SL/TP.
7. **Vercel failure isolation.** Vercel outage removes the dashboard only.
   Trading, risk, and the kill switch remain operable via direct API/CLI
   against the VPS. This is the explicit reason the third-party dependency
   is confined to the read/visualization path.

## Scaling path (unchanged from Phase 1, restated for infra)

| Stage | Change | Infra implication |
|-------|--------|-------------------|
| V1 | Single VPS, one instance per service | Current release |
| V2 | Replicated async workers | compose replicas + Redis consumer groups; Caddy/pipeline unchanged |
| V3–V4 | trade-core / bridge stay single | Architectural invariant, not a tuning parameter |
| V5 | Multi-broker bridges | One bridge container per broker; no Caddy or pipeline change |
| V6 | Multi-account trade-cores | Sharding accounts; observability moves to federation/Mimir if multi-node |

## What this document does NOT define

- Concrete compose YAML, Dockerfiles, firewall rules (Phase 14+).
- SSH/user hardening and network ACL policy (Phase 12).
- Backup schedule internals and runbook steps (`backup-dr.md`).

## Phase boundary

The runtime layout and binding rules are fixed here. Concrete manifests
belong to Phase 14+.
