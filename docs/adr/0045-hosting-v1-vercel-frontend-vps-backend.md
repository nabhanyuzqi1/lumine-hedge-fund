# ADR-0045 — Hosting V1: Vercel frontend + VPS backend

- **Status:** Accepted
- **Phase:** 11-infrastructure
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

The frontend SPA (React + Vite, Phase 10 D10-1) needs a hosting target and
the backend remains Docker Compose on a single Linux VPS per Phase 1
`deployment-topology.md`. The SPA is a static bundle; SSE cross-origin works
with standard EventSource; HMAC request signing (Phase 9 `auth.md`) is
computed client-side, so no cookie/session coupling exists. The trade-critical
path (trading, risk, kill-switch) must not depend on the frontend host.

## Decision

Frontend SPA deployed to Vercel, production domain only. Backend remains
Docker Compose on a single Linux VPS. Caddy CORS allowlists only the Vercel
production origin. Preview deployments are deliberately NOT CORS-allowlisted
— only the production origin can reach the API.

## Rationale

- Vercel deployment is trivial for a static bundle; preview builds and global
  CDN come free.
- CORS origin allowlisting is sufficient — HMAC signing has no cookie/session
  coupling.
- The trade-critical path never depends on Vercel: if Vercel is down, the
  dashboard is unavailable but trading, risk, and kill-switch operation via
  direct API/CLI against the VPS continue unaffected.
- All-in-VPS static serving via Caddy rejected: zero third-party dependency
  but frontend build/deploy becomes our own operational burden; acceptable
  fallback, not the default.
- Managed Postgres/Redis outside the VPS rejected: violates Phase 1
  minimal-egress and organic-first principles for V1.

## Consequences

- Positive: frontend hosting is zero-operational-burden; CDN and preview
  builds are free.
- Positive: API attack surface is fixed to one origin.
- Negative: depends on Vercel availability for dashboard access (mitigated:
  trading path is independent).
- Reversibility: fall back to Caddy static serving on the VPS.

## Cross-references

- Related ADRs: ADR-0046, ADR-0047
- Implements principle(s): #5
- Affects phases: 11, 10
- Source document: `../11-infrastructure/decisions.md` (D11-1)
