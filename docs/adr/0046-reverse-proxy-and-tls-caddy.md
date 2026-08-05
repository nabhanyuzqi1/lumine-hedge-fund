# ADR-0046 — Reverse proxy and TLS: Caddy

- **Status:** Accepted
- **Phase:** 11-infrastructure
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

The backend Docker Compose stack needs a reverse proxy for TLS termination,
routing, and path-based forwarding. The V1 topology is static — a fixed set
of services with fixed routes. SSE long-lived connections must be proxied
without special tuning.

## Decision

Caddy runs as a single container in front of Docker Compose with automatic
Let's Encrypt issuance and renewal. It routes REST + SSE to
`lumine-trade-core` and `/grafana/*` to Grafana behind an IP allowlist.

## Rationale

- ~10 lines of config for the entire V1 topology; TLS renewal is automatic
  with no certbot hooks.
- SSE long-lived connections are proxied without special tuning.
- Nginx + Certbot offers more knobs but V1 does not need them.
- Traefik's label-based routing excels in dynamic container environments;
  our topology is static, so the dynamic routing advantage is unused.

## Consequences

- Positive: zero-touch TLS; minimal configuration; no certbot maintenance.
- Positive: SSE proxying works out of the box.
- Negative: Caddy is a less common choice than Nginx — smaller knowledge
  base for edge-case troubleshooting.
- Reversibility: swap to Nginx + Certbot with equivalent routing config.

## Cross-references

- Related ADRs: ADR-0045, ADR-0052
- Implements principle(s): #3
- Affects phases: 11
- Source document: `../11-infrastructure/decisions.md` (D11-2)
