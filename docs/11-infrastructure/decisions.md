# Phase 11 — Locked Decisions

## D11-1 — Hosting V1: Vercel frontend + VPS backend

> **ADR:** [ADR-0045](../../adr/INDEX.md#adr-0045) — Hosting V1: Vercel frontend + VPS backend

**Choice:** Frontend SPA (React + Vite, Phase 10 D10-1) deployed to Vercel,
production domain only. Backend remains Docker Compose on a single Linux VPS
per Phase 1 `deployment-topology.md`. Caddy CORS allowlists only the Vercel
production origin.

**Rationale:**
- The SPA is a static bundle — Vercel deployment is trivial, preview builds
  and global CDN come free.
- SSE cross-origin works with standard EventSource; HMAC request signing
  (Phase 9 `auth.md`) is computed client-side, so no cookie/session
  coupling exists — CORS origin allowlisting is sufficient.
- The trade-critical path never depends on Vercel: if Vercel is down, the
  dashboard is unavailable but trading, risk, and kill-switch operation
  (via direct API/CLI against the VPS) continue unaffected.
- Preview deployments are deliberately NOT CORS-allowlisted: only the
  production origin can reach the API. This keeps the API attack surface
  fixed to one origin.

**Alternatives rejected:**
- All-in-VPS static serving via Caddy: zero third-party dependency, but
  frontend build/deploy becomes our own operational burden; acceptable
  fallback, not the default.
- Managed Postgres/Redis outside the VPS: violates Phase 1 minimal-egress
  and organic-first principles for V1; cost and complexity rise sharply.

## D11-2 — Reverse proxy & TLS: Caddy

> **ADR:** [ADR-0046](../../adr/INDEX.md#adr-0046) — Reverse proxy and TLS: Caddy

**Choice:** Caddy single container in front of Docker Compose; automatic
Let's Encrypt issuance and renewal; routes REST + SSE to `lumine-trade-core`
and `/grafana/*` to Grafana behind an IP allowlist.

**Rationale:** ~10 lines of config for the entire V1 topology; TLS renewal
is automatic with no certbot hooks; SSE long-lived connections are proxied
without special tuning. Nginx+Certbot offers more knobs but V1 does not need
them. Traefik's label-based routing excels in dynamic container
environments; our topology is static.

## D11-3 — CI/CD: GitHub Actions + GHCR + SSH deploy; Vercel Git integration

> **ADR:** [ADR-0047](../../adr/INDEX.md#adr-0047) — CI/CD: GitHub Actions + GHCR + SSH deploy; Vercel Git integration

**Choice:** Backend pipeline: GitHub Actions builds one immutable image per
service per SHA, pushes to GHCR, then SSHs to the VPS to `docker compose
pull && up -d`. Frontend: Vercel Git integration auto-deploys on push.

**Rationale:** zero additional infrastructure (no self-hosted CI runner to
maintain); GHCR is free for private repos and sits next to the code; SSH
deploy to a single static VPS is the simplest correct mechanism at this
scale. Docker Hub rejected over pull rate limits. Self-hosted CI rejected as
an extra stateful service to operate.

## D11-4 — Observability: Prometheus + Grafana + Loki + Tempo, self-hosted

> **ADR:** [ADR-0048](../../adr/INDEX.md#adr-0048) — Observability: Prometheus + Grafana + Loki + Tempo, self-hosted

**Choice:** All telemetry stays on the VPS: Prometheus (metrics), Loki +
Promtail (logs), Tempo via OTel collector (traces), Grafana (dashboards),
Alertmanager (alerts to operator).

**Rationale:** operational data of a trading fund does not leave the node —
consistent with Phase 1 minimal-egress; zero license cost. The `trace_id`
flowing through logs and spans is the same key Phase 9 `error-contract.md`
returns to clients, closing the loop between frontend ActivityLog and
backend traces. Grafana Cloud rejected because it exfiltrates operational
data. Sentry rejected to avoid another external dependency (error data is
already captured by structured logs + traces).

## D11-5 — Backup & DR: scheduled dumps to encrypted object storage

> **ADR:** [ADR-0049](../../adr/INDEX.md#adr-0049) — Backup and DR: scheduled dumps to encrypted object storage

**Choice:** Daily `pg_dump` (custom format) + continuous WAL archiving +
Redis AOF + volume sync, shipped via `rclone` (crypt remote, encrypted) to
Backblaze B2 / S3. Monthly automated restore test. RPO ≤ 24h (dump) / ≤ 5
min (WAL); RTO hours via documented manual runbook.

**Rationale:** this is the only new egress approved, and it is explicit and
encrypted. Local-only backup rejected — VPS loss would mean data loss, which
is unacceptable for a financial system. Hot-standby replication rejected for
V1: it doubles VPS cost and adds replication-lag operational complexity the
current scale does not justify.

## D11-6 — Secrets injection: SOPS + age, env-var injection

> **ADR:** [ADR-0050](../../adr/INDEX.md#adr-0050) — Secrets injection: SOPS + age, env-var injection

**Choice:** One encrypted `.env.enc` (SOPS + age) in the private repo. CI
decrypts at deploy time and writes `/srv/lumine/.env` over SSH; containers
receive values as environment variables at `compose up`. The age private key
lives in a GitHub Actions secret (deploy) and the operator's password
manager (local).

**Rationale:** secrets are versioned and auditable in Git without ever being
plaintext; no additional service to run. Docker secrets (`/run/secrets`)
rejected: marginally safer against `/proc` inspection, but many libraries
read env vars only and would need shims. Self-hosted Vault rejected: a
stateful cluster plus operational burden far beyond V1 needs. Rotation =
edit, commit, deploy. Access policy details (who may hold the age key,
audit) belong to Phase 12.

## D11-7 — Control plane: Caddy + Authelia + Homepage + Uptime Kuma

> **ADR:** [ADR-0069](../../adr/INDEX.md#adr-0069) — Control plane: Caddy + Authelia + Homepage + Uptime Kuma, GUI services behind auth

**Choice:** On the production VPS, one `control-plane` Compose stack sits
in front of the deployed services: Caddy (already D11-2) as the only
public listener `:80/:443`, Authelia (basepath `/auth`) as the central
login with TOTP via `forward_auth`, Homepage as the post-login hub at
`/portal`, and Uptime Kuma as the interactive health dashboard. The
marketing landing page lives at `/` (public, container `nginx:alpine`,
bridge network, read-only mount of `/var/www/lumine`; host nginx
disabled — 11/11 services containerized). Protected routes:
`/portal*` → Homepage hub (auth → strip `/portal` via `route{}`),
`/hermes*` → Hermes dashboard, `/mt5/*` + `/websockify*` → noVNC
(websocket client noVNC memakai path absolut `/websockify`), `/backend*` →
Lumine API, `/assets*` + `/socket.io` + 4 path `/api` frontend Kuma
(`/api/badge*`,
`/api/entry-page*`, `/api/push*`, `/api/status-page*`) → Kuma,
sisa `/api*` (hydration Homepage) + `/_next*` (Next.js assets) →
Homepage, `/dashboard*` → Kuma (TANPA strip — Kuma redirect root →
`/dashboard`). `/` and `/site*` (legacy alias) are the only content
routes exempt from auth (public marketing page); their upstream stays
loopback-bound. All other upstream services are loopback-bound. TLS is
`tls internal` (self-signed) until a domain is configured.

**Rationale:**
- Every service — including the MT5 VNC previously world-exposed on
  `:5900/:6901` — now sits behind one admin login with TOTP.
- Hermes dashboard (loopback-only, SSH-tunnel friction) becomes reachable
  at a public path with auth.
- Topology is static, so label-based proxying (Traefik) adds nothing;
  Authentik was rejected for its own Postgres+Redis weight on an 8 GB
  VPS (see ADR-0069 alternatives).
- Kuma monitors all seven endpoints from inside the same host; failures
  are visible without opening the observability stack (D11-4).

**Explicit exception:** `9router` on `:20128` stays public
(`0.0.0.0`) — external AI agents connect by IP and closing the port
takes them all offline (observed 2026-08-07). This is the only public
port beyond `:80/:443`. See ADR-0069 for compensating controls and the
mTLS/allowlist follow-up.

**Alternatives rejected:** Traefik (dynamic routing for a static
topology), Authentik (own Postgres+Redis, too heavy), oauth2-proxy (no
TOTP/user UI), nginx+auth_request (manual TLS), Grafana/Prometheus as
health UI (deep observability stays D11-4).

**Updated consequences (2026-08-09):**
- Landing page containerized: `control-landing` (nginx:alpine, bridge,
  `127.0.0.1:8080:80`, read-only bind of `/var/www/lumine`); host nginx
  disabled — 11/11 services in the public path are now Docker containers.
- Homepage moved to `/portal` as the post-login hub; a Logout button in
  the header links to `/auth/logout?rd=…` (Authelia session destroy).
- Authelia upgraded to 4.39, theme `dark`; custom CSS file deployed for
  future Authelia ≥4.40 (custom themes not yet in stable release).
- Kuma runs with `disableAuth=1` (single login — Authelia is the only
  auth gate).
- `route{}` raw-routing block used for ALL stripped routes
  (`/portal`, `/hermes`, `/mt5`, `/backend`, `/status`) — the Caddyfile
  adapter reorders `uri strip_prefix` before `forward_auth` on plain
  `handle`/`handle_path`, breaking Authelia `rd=` post-login redirect.
- Landing assets (`/assets/*`, `/favicon.svg`) split from Kuma assets
  via named matcher `@landing` with `header_regexp Referer` — placed
  BEFORE Kuma's `/assets*` handler (first-match).
- `deploy-site.sh` rewritten: in-place copy (`find … -delete && cp -a`)
  preserves the bind-mount inode; health check targets container
  `127.0.0.1:8080`.
- `nginx-lumine-site.conf` marked SUPERSEDED — retained as documentation
  of the old host-level config, never to be deployed.
- Kuma redirect root → `/dashboard` uses a single `Location` header
  (never override — Safari/WebKit rejects multi-Location redirects).

## Principles honored

- Phase 1 minimal-egress: only one new egress added (backup), explicitly.
- Phase 1 single-writer/single-instance invariants: untouched.
- Fail-visible-not-silent: restore tests and deploy verification are
  alerting obligations, not optional checks.
- No service contracts changed: Phases 1–9 documents remain authoritative.

## Phase boundary

Decisions D11-1..D11-6 are locked. Security policy (Phase 12), test gates
(Phase 13), and concrete manifests (Phase 14+) build on these without
reopening them.
