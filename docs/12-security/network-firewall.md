# Network & Firewall

## Overview

Network security architecture per D12-4. Host-level firewall (UFW),
Docker bridge isolation, Caddy-level access control, and CORS policy.
Only three ports are exposed to the public internet.

## UFW rules

```
# Phase 14+ implementation
ufw default deny incoming
ufw default allow outgoing
ufw allow 80/tcp
ufw allow 443/tcp
ufw limit 22/tcp
ufw enable
```

| Rule | Rationale |
|------|-----------|
| `default deny incoming` | Whitelist model — only explicitly allowed traffic |
| `default allow outgoing` | Services need egress (LLM API, MT5, news, backup) |
| `allow 80/tcp` | Caddy HTTP — ACME HTTP-01 challenge + redirect to HTTPS |
| `allow 443/tcp` | Caddy HTTPS — the only public service port |
| `limit 22/tcp` | SSH with rate limiting (6 connections per 30 seconds per IP) |
| All other ports dropped | No PostgreSQL, Redis, Docker API, or any other service exposed |

## Docker network isolation

### Daemon configuration

```
# /etc/docker/daemon.json (Phase 14+)
{
  "iptables": false,
  "userland-proxy": false,
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

Setting `"iptables": false` prevents Docker from creating its own
iptables rules that bypass UFW. All inter-container communication stays
on the internal bridge network.

### Container network

```
# compose.yaml network section (Phase 14+)
networks:
  lumine-net:
    driver: bridge
```

- Standard bridge network — containers can reach external services
  (MT5, LLM API, news, backup via rclone) through the host's `default
  allow outgoing` UFW rule. Egress is controlled at the host firewall
  level, not the Docker network level.
- All inter-service traffic (trade-core → PostgreSQL, trade-core → Redis,
  workers → LLM gateway) stays on this bridge.
- No container publishes ports to the host except Caddy (`80:80`,
  `443:443`).

## Caddy-level hardening

### IP allowlist for Grafana

```
# Caddyfile /grafana/* route (Phase 14+)
handle_path /grafana/* {
    @allowed remote_ip <operator-ip-ranges>
    handle @allowed {
        reverse_proxy grafana:3000
    }
    respond "Forbidden" 403
}
```

Grafana exposes fund state (equity, exposure, positions, agent
decisions) — it must not be world-reachable. Only allowlisted operator
IP ranges can access it.

### Rate limiting

```
# Caddyfile rate_limit directive (Phase 14+)
rate_limit {
    zone api {
        key {remote_host}
        events 60
        window 1m
    }
}
```

60 requests per minute per IP for `/api/*`. This catches brute force
and accidental floods before they reach the application.

### TLS configuration

- Minimum TLS 1.2 (TLS 1.3 preferred where client supports)
- Automatic Let's Encrypt via Caddy's built-in ACME client (D11-2)
- HTTP→HTTPS redirect for all requests

## CORS policy

Configured in Caddy (not in the application) as a single enforcement
point:

```
# Caddyfile CORS (Phase 14+)
header {
    Access-Control-Allow-Origin "https://lumine.vercel.app"
    Access-Control-Allow-Methods "GET POST PUT DELETE OPTIONS"
    Access-Control-Allow-Headers "Content-Type X-Signature X-Timestamp X-API-Key"
    Access-Control-Max-Age "3600"
}
```

| Header | Value | Rationale |
|--------|-------|-----------|
| `Allow-Origin` | `https://lumine.vercel.app` | Production origin only; no wildcard |
| `Allow-Methods` | GET, POST, PUT, DELETE, OPTIONS | Standard CRUD + preflight |
| `Allow-Headers` | Content-Type, X-Signature, X-Timestamp, X-API-Key | HMAC auth headers from Phase 9 |
| `Max-Age` | 3600 | Cache preflight for 1 hour |

Preview deployments (`*.vercel.app`) are explicitly NOT allowlisted.
This means preview builds cannot reach the API — by design (D11-1).

## Network diagram

```
Internet
  │
  ├─ :80  ──► UFW ──► Caddy (HTTP → HTTPS redirect, ACME)
  ├─ :443 ──► UFW ──► Caddy ──► lumine-net (bridge)
  │              ▲         │
  │              │         ├─ /api/* → lumine-trade-core:8000
  │              │         ├─ /streams/* → lumine-trade-core:8000
  │              │         └─ /grafana/* → grafana:3000 (IP allowlist)
  │              │
  ├─ :22  ──► UFW (limit) ──► sshd (ed25519 only)
  │
  └─ all other ports → DROP

No public access to:
  - PostgreSQL (:5432)
  - Redis (:6379)
  - Prometheus (:9090)
  - Loki (:3100)
  - Tempo (:3200)
  - Docker API (:2375/:2376)
```

## What this document does NOT define

- Concrete UFW rule files, Docker daemon.json, Caddyfile (Phase 14+).
- Operator IP range management (Phase 14+ operational policy).
- DDoS mitigation beyond Caddy rate limiting (V1 scope).

## Phase boundary

Network and firewall architecture is fixed here. Configuration files
belong to Phase 14+.