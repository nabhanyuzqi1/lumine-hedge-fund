# Hermes Agent — Deployment Spec

Ground truth deployment of the Hermes messaging agent (upstream:
NousResearch) on the Lumine VPS. Registered 2026-08-12 as part of the
repo-vs-server parity audit.

## Runtime

| Field | Value |
|-------|-------|
| Container | `hermes` (1 instance) |
| Image | `hermes-agent` (built locally from `docker-compose.yml` in this dir) |
| Compose project | `hermes-agent` |
| Compose file | `/opt/hermes/hermes-agent/docker-compose.yml` |
| Root | `/opt/hermes/hermes-agent/` |
| Restart | `unless-stopped` |
| Network | `host` (gateway + dashboard bind loopback) |
| Dashboard | `127.0.0.1:9119` → Caddy `/hermes*` (behind Authelia) |
| State | bind mount `~/.hermes:/opt/data` (host `/root/.hermes`) |

The image is built in-place from the cloned upstream repo
(`/opt/hermes/hermes-agent/`), not pulled from a registry. The compose
file below is the canonical copy; the repo root dir also contains the
unmodified upstream `docker-compose.yml`.

## Environment

| Variable | Value / source |
|----------|----------------|
| `HERMES_UID` / `HERMES_GID` | host uid/gid of `~/.hermes` owner (`10000`/`10000`) |
| `HERMES_DASHBOARD` | `1` (dashboard inside gateway container) |
| `HERMES_DASHBOARD_HOST` / `_PORT` | `127.0.0.1` / `9119` (loopback-only; auth gate off) |
| `API_SERVER_HOST` | `0.0.0.0` (OpenAI-compatible API server enabled) |
| `API_SERVER_KEY` | from `/opt/hermes/hermes-agent/.env` (`hms_...`) — **not in repo** |
| `NINEROUTER_API_KEY` | from `/opt/hermes/hermes-agent/.env` (`sk-...`) — **not in repo** |

Secrets live in `/opt/hermes/hermes-agent/.env` on the VPS. The off-server
source of truth is `scripts/deploy/secrets.env` (SOPS + age, D11-6).
Restore: decrypt with `sops -d scripts/deploy/secrets.env > /opt/hermes/hermes-agent/.env`.

## Mounts

- `~/.hermes:/opt/data` — all agent state (state.db, kanban.db, auth.json,
  pairing/, memories/, config.yaml, cache). This is the data that the
  backup script preserves (`/root/.hermes`, cache excluded).
- `./gateway/platforms/api_server.py:/opt/hermes/gateway/platforms/api_server.py:ro`
  — local patch of the API server (kept in the clone; diff vs upstream is
  tracked locally).

## Restore procedure (new VPS / after server death)

1. `git clone https://github.com/NousResearch/hermes /opt/hermes/hermes-agent`
   (or restore the repo copy if it ever diverges from upstream).
2. Re-apply the `api_server.py` patch (file is in the repo `gateway/` dir).
3. Restore `/root/.hermes` from backup (backup tar contains it, cache excluded).
4. Decrypt `scripts/deploy/secrets.env` (SOPS + age) to
   `/opt/hermes/hermes-agent/.env` (API_SERVER_KEY, NINEROUTER_API_KEY).
5. `HERMES_UID=$(id -u) HERMES_GID=$(id -g) docker compose up -d`
6. Verify: dashboard on `127.0.0.1:9119`; Caddy `/hermes*` route; pairing
   still valid (auth.json + pairing/ restored).

## Notes

- Hermes state is the single largest backup payload (~455 MB on disk;
  ~143 MB compressed with cache excluded).
- The upstream compose pins the `gateway` service via `build: .` —
  there is no published image tag; the clone must be present to rebuild.
- If the server dies, the clone itself is lost with it; the repo copy of
  the compose + patch is what allows a clean rebuild, while `/root/.hermes`
  backup restores identity (pairing, memories, credentials).
