# Threat Model & Attack Surface

## Overview

Security model for Lumine V1 — a single-node Docker Compose deployment on
a Linux VPS, with a Vercel-hosted frontend SPA and one human operator. This
document defines what is and is not a threat, maps the attack surface, and
establishes the security boundaries that subsequent documents enforce.

## V1 threat profile

### What an attacker can reach

| Vector | Accessible? | Attack types |
|--------|-------------|--------------|
| Public internet → Caddy :80 | Yes | HTTP→HTTPS redirect, ACME HTTP-01 challenge |
| Public internet → Caddy :443 | Yes | API replay, brute force, scope escalation, malformed requests |
| Public internet → VPS :22 | Yes | SSH brute force, key enumeration |
| Vercel frontend | Yes (public URL) | XSS (if injected), dependency exploit |
| Docker bridge network | No (internal) | — |
| PostgreSQL / Redis | No (internal, no public ports) | — |
| Physical VPS / hypervisor | No (cloud provider) | — |

### What is explicitly NOT a threat for V1

| Excluded threat | Reason |
|-----------------|--------|
| Insider attack (malicious operator) | Operator is the only human; controls all keys and infrastructure. No technical control can prevent a determined insider with root access. |
| Physical access / data center breach | Cloud VPS; physical security is the provider's responsibility. LUKS encryption provides defense-in-depth for volume exfiltration scenarios. |
| Multi-tenant isolation escape | Single-node, single-tenant deployment. No other workloads share the VPS. |
| Regulatory compliance (SOC 2, ISO 27001, GDPR) | V1 has no compliance obligations. Architecture is designed to be compliance-ready, not compliance-burdened. |
| Sophisticated DDoS (volumetric) | Single static VPS is not a high-value DDoS target. Caddy rate limiting handles application-layer floods. |
| Supply chain attack on Vercel CDN | Vercel outage removes the dashboard only; trading, risk, and kill-switch remain operable via direct API/CLI (D11-1). |
| Zero-day in Docker engine | Acceptable residual risk. Containers run as non-root; host firewall limits exposure. |

## Attack surface detail

### 1. REST API (`/api/*` via Caddy :443)

| Attack | Vector | Mitigation | Phase |
|--------|--------|------------|-------|
| Replay attack | Capture valid signed request, re-send | HMAC-SHA256 with timestamp + nonce (Phase 9 `auth.md`) | 9 |
| Brute force API keys | Repeated auth attempts | Rate limiting at Caddy level; security event alerting after 5 failures in 5 min | 11, 12 |
| Scope escalation | Valid key used for unauthorized endpoint | Scope validation per endpoint (Phase 9 `auth.md`) | 9 |
| Malformed payload | Crafted JSON to exploit parser | FastAPI + Pydantic validation; no eval/exec | 9, 14 |
| Unauthorized origin | Request from non-production domain | CORS strict: only `https://lumine.vercel.app` | 11 |

### 2. SSE stream (`/streams/*` via Caddy :443)

| Attack | Vector | Mitigation |
|--------|--------|------------|
| Unauthorized subscription | Connect to SSE without valid key | Auth required on SSE handshake; same HMAC as REST |
| Connection exhaustion | Open many SSE connections | Caddy connection limits; single-origin CORS |

### 3. SSH (:22)

| Attack | Vector | Mitigation |
|--------|--------|------------|
| Brute force | Password guessing | `PasswordAuthentication no` — no passwords exist |
| Key enumeration | Try many public keys | `PubkeyAuthentication` only; `AllowUsers` restrict; `ufw limit 22` |
| Deploy key compromise | GitHub Actions secret leak | Key scoped to `/srv/lumine/` via `command=`; non-root; no sudo |

### 4. Secrets at rest

| Attack | Vector | Mitigation |
|--------|--------|------------|
| `.env.enc` in repo exposed | GitHub repository compromise | SOPS + age encrypted; private key not in repo |
| `.env` plaintext on VPS | VPS filesystem access | Requires SSH (key auth) or container escape (non-root user) |
| `/proc/<pid>/environ` read | Container escape or same-user process | Containers run as dedicated non-root users; no shared accounts |
| Age private key leak | GH Actions secret or password manager compromise | Rotate key; audit log captures deploy events |

### 5. Containers

| Attack | Vector | Mitigation |
|--------|--------|------------|
| Container escape | Kernel exploit from inside container | Non-root user; minimal base image; no privileged mode |
| Malicious image | Compromised base image or dependency | SHA-pinned images; `docker scout`/Trivy in CI; Dependabot |
| Inter-container sniffing | Docker bridge network | All sensitive traffic is internal; no secrets on wire between containers |

### 6. Dependencies

| Attack | Vector | Mitigation |
|--------|--------|------------|
| Known CVE in Python package | pip install vulnerable version | `pip-audit` in CI; critical/high blocks merge; Dependabot weekly |
| Known CVE in npm package | npm install vulnerable version | `npm audit` in CI; critical/high blocks merge |
| Base image CVE | Vulnerable system library in `python:3.12-slim` | Dependabot + Docker scout; weekly rebuild |

### 7. Backup egress (rclone → B2/S3)

| Attack | Vector | Mitigation |
|--------|--------|------------|
| Backup data intercepted in transit | MITM on egress path | rclone TLS (HTTPS to B2/S3); no plaintext HTTP |
| Backup data exposed at provider | B2/S3 bucket misconfiguration | rclone crypt — data encrypted client-side before upload |
| Backup key compromise | `RCLONE_CRYPT_PASSWORD` leak | Separate key from other secrets; in `.env` (SOPS-encrypted) |

### 8. Supply chain (GHCR)

| Attack | Vector | Mitigation |
|--------|--------|------------|
| Tag mutation | Attacker pushes new image with same `latest` tag | Production compose pins SHA tags; `latest` is pointer only |
| GHCR credential leak | GitHub token compromise | Standard GitHub token scoping; deploy key is separate from GHCR access |

### 9. Vercel frontend

| Attack | Vector | Mitigation |
|--------|--------|------------|
| XSS in dashboard | Injected script in frontend | React's built-in XSS protection; Content-Security-Policy header |
| Dependency exploit | Compromised npm package in frontend | `npm audit` in CI; Vercel auto-deploys only from main |
| Preview deployment reaches API | CORS bypass via preview URL | CORS allowlist = production origin only; preview deployments cannot reach API |

## Security boundaries

```
┌─────────────────────────────────────────────────┐
│  Internet                                        │
│  ├─ :80  ──► Caddy (HTTP → HTTPS redirect, ACME) │
│  ├─ :443 ──► Caddy (TLS termination, rate limit) │
│  │            ├─ CORS check (origin)              │
│  │            ├─ IP allowlist (/grafana/*)       │
│  │            └─ route to trade-core              │
│  └─ :22  ──► SSH (ed25519 only, no passwords)    │
│                                                  │
│  ┌── VPS boundary ───────────────────────────┐   │
│  │  UFW: allow 80, 443, 22; drop all else     │   │
│  │  LUKS2: full disk encryption               │   │
│  │  Docker bridge (internal, no public ports) │   │
│  │  pgcrypto: column-level encryption          │   │
│  │  rclone crypt: backup encryption           │   │
│  └────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

## What this document does NOT define

- Specific rate-limit values, Caddyfile directives, UFW rule files
  (Phase 14+).
- Penetration testing methodology (Phase 13).
- Incident response procedures (Phase 14+ operations runbook).
- Access policy: who may hold keys, approval workflow (Phase 14+
  operational policy).

## Phase boundary

The threat model, attack surface, and security boundaries are fixed here.
Concrete configurations and enforcement code belong to Phase 14+.