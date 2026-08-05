# ADR-0052 — Firewall: UFW, 3 ports only, Docker bridge

- **Status:** Accepted
- **Phase:** 12-security
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

A single-node VPS needs a host-level firewall with the minimal achievable
attack surface. Docker's default iptables manipulation can bypass UFW rules.
Operational dashboards (Grafana) must not be world-reachable. CORS must be
strict to prevent unauthorized origins from reaching the API.

## Decision

UFW allow 80 (Caddy HTTP/ACME), 443 (Caddy HTTPS), and 22 (SSH) only; all
other inbound dropped. Docker daemon with `--iptables=false`; all
inter-service traffic on internal bridge network. Caddy-level IP allowlist
for `/grafana/*`. CORS strict — only Vercel production origin.

## Rationale

- Three open ports (80, 443, 22) is the minimal attack surface achievable for
  a web service with remote administration. Every additional port is a
  potential vector.
- Docker's default iptables manipulation can bypass UFW rules; setting
  `--iptables=false` and managing rules explicitly prevents this.
- Grafana behind IP allowlist means operational dashboards are not
  world-reachable — consistent with the principle that fund state must not be
  publicly visible.
- Rate limiting on SSH (`ufw limit 22`) adds a second layer even though
  password auth is already disabled.
- Cloud firewall (security groups) only rejected: defense in depth —
  host-level firewall catches misconfigured cloud rules.
- IDS/IPS (Snort/Suricata) rejected: high operational overhead for a
  single-node deployment; the alerting pipeline already catches anomalous
  patterns.
- WAF (Cloudflare/mod_security) rejected: Caddy rate limiting + CORS strict +
  HMAC auth is sufficient for the V1 API surface; WAF adds latency and
  another external dependency.

## Consequences

- Positive: minimal attack surface; Docker cannot bypass host firewall.
- Positive: operational dashboards are IP-restricted.
- Negative: `--iptables=false` requires explicit inter-service network
  management.
- Reversibility: re-enable Docker iptables management by changing daemon
  config and UFW rules.

## Cross-references

- Related ADRs: ADR-0001, ADR-0002, ADR-0046
- Implements principle(s): #10
- Affects phases: 12, 11
- Source document: `../12-security/decisions.md` (D12-4)
