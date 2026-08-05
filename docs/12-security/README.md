# Phase 12 — Security

## Overview

Phase 12 defines the security architecture for Lumine V1: threat model,
access control, encryption, network firewall, supply chain security, and
audit logging. It builds on Phase 11 infrastructure decisions and Phase 9
auth contracts.

Phase 12 does NOT define: test strategy (Phase 13), implementation
code/manifests (Phase 14+), operational policy details (Phase 14+), or
any service contract (Phases 1–9).

## Documents

| Document | Purpose |
|----------|---------|
| `decisions.md` | Locked decisions D12-1 .. D12-6 with rationale |
| `threat-model.md` | Threat model, attack surface, security boundaries |
| `ssh-access.md` | SSH key architecture, access control matrix |
| `encryption.md` | Three-layer encryption (disk, column, backup) + key management |
| `network-firewall.md` | UFW, Docker network isolation, Caddy hardening, CORS |
| `supply-chain.md` | Dependency scanning, Dependabot, container hardening, artifact integrity |
| `audit-log.md` | Security event log schema, dual logging, alerting, trace_id loop |

## Decisions at a glance

| # | Decision | Choice |
|---|----------|--------|
| D12-1 | Threat model | Realistic V1 — network-layer, replay, brute force. Insider/physical/regulatory/DDoS excluded. |
| D12-2 | SSH access | 2-key ed25519 — CI deploy key (non-root, scoped to `/srv/lumine/`) + admin key (full sudo). No password auth. |
| D12-3 | Encryption | Three layers — LUKS2 (disk) + pgcrypto (column) + rclone crypt (backup). Separate keys, no circular dependency. |
| D12-4 | Firewall | UFW allow 80, 443, 22 only. Docker bridge. Caddy IP allowlist for Grafana. CORS strict. |
| D12-5 | Supply chain | Dependabot + pip-audit + npm audit + docker scout in CI. Critical/high blocks merge. SHA-pinned images. |
| D12-6 | Audit log | PostgreSQL `security_events` (append-only, 90d) + Loki structured logs. Prometheus alerting on security anomalies. |

## Security principles

1. **Least privilege.** Deploy key scoped to `/srv/lumine/`; containers run as non-root; only 3 open ports.
2. **Defense in depth.** Three encryption layers, two audit paths, two SSH keys, two firewall layers.
3. **Fail closed.** Auth failure → reject; CVE critical → block merge; key compromise → rotate.
4. **Immutable evidence.** `security_events` append-only; `trace_id` full correlation from Phase 9 → Phase 11 → Phase 12.
5. **No security by obscurity.** All configurations in repo (encrypted where needed), all rules explicit.

## What this phase does NOT define

- Penetration testing plan and methodology (Phase 13).
- Test gates and CI enforcement details (Phase 13).
- Concrete SSH config, Caddyfile, UFW rules, Dependabot YAML, Dockerfiles,
  security_events migration (Phase 14+).
- Operational policy: who may hold keys, approval workflow, audit cadence,
  operator onboarding/offboarding (Phase 14+).
- Incident response runbook details (Phase 14+).
- Bug bounty program, regulatory compliance, SBOM generation (V2+).

## Phase boundary

Security architecture is fixed here. Implementation, configuration files,
and operational procedures belong to Phase 14+.