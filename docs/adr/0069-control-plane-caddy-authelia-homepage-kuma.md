# ADR-0069 — Control plane: Caddy + Authelia + Homepage + Uptime Kuma, GUI services behind auth

- **Status:** Accepted
- **Phase:** 11-infrastructure
- **Date:** 2026-08-07
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

The VPS `166.88.227.177` hosts Hermes (messaging gateway), the Lumine
backend, the MT5 container (noVNC), and the 9router LLM gateway, each
exposed to the Internet on its own port:

- `backend-api` binds `0.0.0.0:8000` — public REST API **without TLS**.
- `lumine-mt5` binds `0.0.0.0:5900` (VNC) and `0.0.0.0:6901` (noVNC) —
  anyone can view/control the MT5 terminal.
- `9router` binds `0.0.0.0:20128` — the LLM gateway holding API keys.
- Hermes dashboard binds `127.0.0.1:9119` — loopback-only, reachable only
  via SSH tunnel (operational friction: the operator must tunnel each
  time).

D11-2 already locked Caddy as the single public entrypoint, but it was
never deployed. The operator's vision requires: every service in Docker
with a dashboard, centralized admin login, and per-service VNC where a GUI
exists. During 2026-08-07 the control plane was deployed and the three
unprotected public ports were closed.

## Decision

Deploy a `control-plane` Docker Compose stack on the VPS:

| Service | Image | Role |
|---|---|---|
| Caddy | `caddy:2` | Reverse proxy + TLS, `network_mode: host` |
| Authelia | `authelia/authelia` | Auth gateway (login + TOTP), basepath `/auth` |
| Homepage | `gethomepage/homepage` | Landing portal (service grid + live status) |
| Uptime Kuma | `louislam/uptime-kuma` | Health checks UI (uptime, latency, notifications) |
| Landing | `nginx:alpine` | Marketing page; bridge network `127.0.0.1:8080:80`, read-only mount of `/var/www/lumine` (2026-08-09) |

Caddy is the **only** public listener (`:80/:443`, UFW default-deny).
Every route except `/auth`, `/` and `/site*` passes `forward_auth` to Authelia
before reaching its upstream. TLS uses `tls internal` (self-signed) until
a domain is configured, then flips to automatic Let's Encrypt.

Routes (all on `166.88.227.177`):

| Path | Upstream (loopback) | Auth |
|---|---|---|
| `/auth*` | Authelia `127.0.0.1:9091` | no (login endpoint) |
| `/` | Landing page (nginx container) `127.0.0.1:8080` | **no — public** |
| `/site*` | Alias landing page `127.0.0.1:8080` — legacy path, tetap publik | **no — public** |
| `/portal*` | Homepage hub `127.0.0.1:3000` — auth dulu, strip `/portal` via `route{}` | yes |
| `/hermes*` | Hermes dashboard `127.0.0.1:9119` | yes |
| `/mt5/*` | noVNC `127.0.0.1:6901` | yes |
| `/websockify*` | noVNC websockify `127.0.0.1:6901` — client noVNC memakai path absolut `/websockify`, bukan `/mt5/websockify` (insiden 2026-08-08) | yes |
| `/status*` | Uptime Kuma `127.0.0.1:3001` — auth SEBELUM strip via `route{}`; Kuma redirects root → `/dashboard` | yes |
| `/dashboard*` | Uptime Kuma `127.0.0.1:3001` — landing target of Kuma's root redirect, NO strip | yes |
| `/assets*`, `/socket.io` | Uptime Kuma `127.0.0.1:3001` | yes |
| `/api/badge*`, `/api/entry-page*`, `/api/push*`, `/api/status-page*` | Uptime Kuma `127.0.0.1:3001` — only the 4 absolute `/api` paths the Kuma frontend uses | yes |
| `/api*` (everything else) | Homepage `127.0.0.1:3000` — service-grid hydration calls | yes |
| `/_next*` | Homepage `127.0.0.1:3000` — Next.js assets (`/_next/static/*`); without this route the portal renders with no CSS (incident 2026-08-08) | yes |
| `/favicon.svg`, `/assets/*` (dari halaman `/` atau `/site/`) | Landing `127.0.0.1:8080` — split via named matcher `header_regexp Referer ^https?://[^/]*/(site/)?$`, ditaruh sebelum handle `/assets*` Kuma (insiden 2026-08-09) | **no — public** |
| (catch-all) | 404 "Not Found" | — |

Hermes' frontend additionally calls absolute paths (`/assets/*`,
`/api/*`, `/socket.io/*`, `/favicon.ico`) shared with Kuma/Homepage
routes — a named matcher with `header_regexp Referer
^https?://[^/]*/hermes(/|$)` sends those to `9119` when the request
originates from a `/hermes/` page, otherwise they fall through to
Kuma/Homepage (incident 2026-08-08: Hermes rendered blank).
| `/backend*` | Lumine backend `127.0.0.1:8000` | yes |

The marketing landing page is the one **content** route exempt from
auth and lives at the root (`/`, frontend at `https://166.88.227.177/`).
`/site*` remains as a public alias for legacy bookmarks. Both are auth
exceptions only — the upstream nginx container still binds loopback
`127.0.0.1:8080`, so the port is not externally reachable and Caddy
remains the single public entrypoint. The landing's absolute assets
(`/assets/*`, `/favicon.svg`) are split out by a named matcher on the
`Referer` header (page origin `/` or `/site/`) to the landing container,
placed BEFORE the Kuma `/assets*` handler — without this the landing
renders blank (incident 2026-08-09).

Protected upstreams are loopback-bound (`8000`, `5900`, `6901` via
docker-proxy; `9119` Hermes; `9091` Authelia app-level; `3000` Homepage
and `3001` Uptime Kuma via `HOSTNAME`/`UPTIME_KUMA_HOST`). Explicit UFW
DENY rules for `3000/tcp` and `3001/tcp` remain as defense-in-depth,
keeping Caddy the only externally reachable listener.

### Explicit exception: 9router `20128` stays public

`9router` keeps its `0.0.0.0:20128` binding. External AI agents (including
this one) reach the gateway directly by IP; closing the port takes every
external agent offline — this was observed on 2026-08-07 and reversed
immediately. The port is a deliberate, documented exception to the
single-entrypoint rule.

- Compensating controls: Uptime Kuma monitors `:20128`; the gateway's own
  admission control and key handling are unchanged (D6 / S5).
- Open risk: the port remains Internet-reachable and carries LLM keys.
  Accepted for now because the business function (external agents) has no
  alternative path. Revisit with mTLS or IP allowlisting when a domain is
  in place.

### VNC classification

| Service | VNC? | Reason |
|---|---|---|
| MT5 (`lumine-mt5`) | **Yes** | Windows GUI via Wine; noVNC `:6901` now behind Authelia |
| Hermes dashboard | No | Web-native; proxy + auth suffices |
| Lumine backend | No | Web-native (FastAPI) |
| Browser agent (Playwright) | Optional, slot | Useful to watch a bot browse; add container + route when needed |
| AutoGen / runner | No | Headless orchestration |
| Obsidian | Optional, slot | Desktop app; dedicated GUI container "later" |

The architecture supports N GUI services: each GUI container owns its
noVNC port, registered in Caddy + Homepage (see
`docs/11-infrastructure/control-plane.md`).

## Alternatives rejected

- **Traefik** (label-based routing): excels in dynamic container
  environments; our topology is static (same rationale as D11-2).
- **Authentik**: full identity provider with its own Postgres + Redis —
  too heavy for the 8 GB VPS alongside Lumine's own Postgres/Redis.
- **oauth2-proxy**: lightweight but no TOTP/2FA workflow and no user
  management UI out of the box; Authelia ships both.
- **Nginx + auth_request**: equivalent capability, but TLS cert
  management is manual (no `tls internal`/Let's Encrypt automation).
- **Grafana/Prometheus as the health UI**: deep observability is a
  separate concern already locked in D11-4; Kuma covers quick service
  health with notifications at lower operational cost.

## Consequences

- Only `:80/:443` reach the Internet (plus the documented `:20128`
  exception). UFW is default-deny with those ports allowed.
- Every service (including MT5 VNC) requires Authelia login; Hermes and
  the backend are reachable at their public paths without SSH tunneling.
- Homepage shows live per-service status via the Docker socket widget;
  Uptime Kuma monitors all seven endpoints and persists to its own SQLite
  volume.
- **Single login (2026-08-08):** Kuma runs with `disableAuth=1` (setting
  row in its SQLite DB) so its internal password prompt is off — Authelia
  is the only login. Uptime Kuma's auth is then exactly as strong as
  Authelia's; anyone with an Authelia session reaches the health UI.
  Accepted: the dashboard is operational, not trading-critical.
- **Kuma routing final (2026-08-08, two incidents):** (1) a `header`
  override of Kuma's root redirect ADDED a second `Location` header;
  Safari/WebKit refuses multi-Location redirects ("can't reach server,
  or busy"). (2) Browser URLs like `/status/dashboard` are matched by
  Kuma's Vue route `/status/:slug` → empty status page = "blank
  dashboard". Final shape: `/status*` → Kuma via `route{}` (forward_auth
  → `uri strip_prefix` → proxy — the Caddyfile adapter reorders strip
  ahead of auth, breaking Authelia `rd=`); `/dashboard*` → Kuma WITHOUT
  strip (strip → upstream "/" → Kuma 302 → infinite loop). Browser must
  land on `/dashboard`, Kuma's native Vue route.
- **Landing containerized (2026-08-09):** the landing page (at `/`) is
  served by `control-landing` (nginx:alpine, bridge network,
  `127.0.0.1:8080:80`, read-only bind of `/var/www/lumine`); the host
  nginx is disabled (`systemctl disable`). Every service in the public
  path is now a container (11/11). UFW `8080` stays closed.
- **Portal hub + logout (2026-08-09):** Homepage moved to `/portal`
  (strip via `route{}`) as the post-login hub; a Logout button in the
  Homepage header links to `/auth/logout?rd=...` (Authelia session
  destroy); Authelia themed `dark` with Lumine branding CSS (custom
  themes arrive in Authelia ≥ 4.40).
- **`route{}` for all stripped routes (2026-08-09):** the
  `forward_auth` → `uri strip_prefix` → `reverse_proxy` raw block that
  fixed `/status` now covers `/portal`, `/hermes`, `/mt5`, `/backend`
  too — a plain `handle_path` reorders strip before auth, so Authelia
  builds `rd=` from the stripped path and post-login lands on `/`
  (incident 2026-08-09, fixed and re-verified per route).
- Self-signed TLS until a domain is configured; browser warning accepted
  for now (one-line change to switch to Let's Encrypt).
- Compose binds in `backend/docker-compose.prod.yml` are synced to
  loopback, with a comment on the `9router` line warning against closing
  it (2026-08-07 incident).
