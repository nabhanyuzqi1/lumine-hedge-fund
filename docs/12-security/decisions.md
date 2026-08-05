# Phase 12 — Locked Decisions

## D12-1 — Threat model: realistic V1, not speculative

> **ADR:** [ADR-0001](../../adr/INDEX.md#adr-0001) — Threat model: realistic V1, not speculative

**Choice:** Threat model scoped to what an attacker can actually reach in
V1 — network-layer access, port scanning, replay attacks, brute force
attempts. The following are explicitly NOT threats for V1: insider attack
(operator is the only human), physical access (cloud VPS), regulatory
compliance enforcement, multi-tenant isolation, and sophisticated DDoS.

**Rationale:**
- A single-node VPS with one operator has a fundamentally different threat
  profile than a multi-tenant SaaS platform. Over-modeling the threat
  creates security theater — controls that add operational burden without
  addressing real attack vectors.
- The most likely attack vectors for V1 are: credential exposure, API
  replay/brute force, dependency compromise, and SSH brute force. These
  are all addressable with standard controls.
- Phase 9 HMAC-SHA256 signing already provides request-level
  authentication and replay protection; Phase 12 adds the infrastructure
  layer.

**Alternatives rejected:**
- Full STRIDE/Linddun model: produces a 50-page threat catalog where 80%
  of entries don't apply to a single-node deployment. Rejected as
  disproportionate.
- Compliance-first model (SOC 2 / ISO 27001): V1 has no compliance
  requirement; baking it in prematurely constrains architecture without
  benefit.

## D12-2 — SSH: 2-key ed25519-only, no password auth

> **ADR:** [ADR-0002](../../adr/INDEX.md#adr-0002) — SSH: 2-key ed25519-only, no password auth

**Choice:** Two SSH keys — (a) CI deploy key, non-root, scoped to
`/srv/lumine/` via `command=` restriction, stored as GitHub Actions
secret; (b) admin key, full sudo, held by operator in password manager.
Both ed25519. Password authentication disabled. Root login disabled.

**Rationale:**
- ed25519 is the modern standard: smaller keys, faster signing, no known
  weaknesses vs RSA. Two keys separate concerns — CI cannot escalate to
  root, operator cannot accidentally leak the deploy key through CI.
- `command=` restriction on the deploy key means even if the GH Actions
  secret is compromised, the attacker can only run docker compose
  commands in `/srv/lumine/` — not install packages, read other users'
  data, or modify system configuration.
- No password auth eliminates the brute-force vector entirely.

**Alternatives rejected:**
- Single key for both CI and admin: violates least privilege; a CI
  secret leak becomes a full root compromise.
- VPN/WireGuard tunnel: adds operational complexity (key distribution,
  tunnel maintenance) disproportionate to the single-node V1 threat
  model.
- Bastion host: requires a second server; unnecessary when there is only
  one node and no internal multi-tier network.

## D12-3 — Encryption: three layers (disk, column, backup)

> **ADR:** [ADR-0051](../../adr/INDEX.md#adr-0051) — Encryption: three layers (disk, column, backup)

**Choice:** LUKS2/dm-crypt for full disk, `pgcrypto` for sensitive
PostgreSQL columns, `rclone crypt` for backup egress. Three separate
keys with no circular dependency.

**Rationale:**
- LUKS protects data if the physical disk or VPS volume is
  exfiltrated (cloud provider incident). Passphrase is separate from
  `.env` — no circular dependency during recovery.
- `pgcrypto` encrypts specific columns (`secret_hash`, `credentials`)
  such that PostgreSQL never sees plaintext. Application-layer
  encrypt/decrypt means a database dump or compromised DB connection
  does not expose secrets.
- `rclone crypt` ensures backup data is encrypted before it leaves the
  VPS — the object storage provider never sees plaintext.
- Three separate keys mean compromising one layer does not cascade.

**Alternatives rejected:**
- HSM / hardware security module: not available on commodity VPS;
  disproportionate cost and complexity for V1.
- PostgreSQL TDE (Transparent Data Encryption): requires enterprise
  license; `pgcrypto` column-level encryption is sufficient for the
  specific columns that need protection.
- TPM-based auto-unlock for LUKS: cloud VPS typically lacks TPM; manual
  unlock at boot is acceptable for a single-node deployment.

## D12-4 — Firewall: UFW, 3 ports only, Docker bridge

> **ADR:** [ADR-0052](../../adr/INDEX.md#adr-0052) — Firewall: UFW, 3 ports only, Docker bridge

**Choice:** UFW allow 80 (Caddy HTTP/ACME), 443 (Caddy HTTPS), and 22
(SSH) only; all other inbound dropped. Docker daemon with
`--iptables=false`; all inter-service traffic on internal bridge
network. Caddy-level IP allowlist for `/grafana/*`. CORS strict — only
Vercel production origin.

**Rationale:**
- Three open ports (80, 443, 22) is the minimal attack surface achievable for a web
  service with remote administration. Every additional port is a
  potential vector.
- Docker's default iptables manipulation can bypass UFW rules; setting
  `--iptables=false` and managing rules explicitly prevents this.
- Grafana behind IP allowlist means operational dashboards are not
  world-reachable — consistent with the principle that fund state must
  not be publicly visible.
- Rate limiting on SSH (`ufw limit 22`) adds a second layer even though
  password auth is already disabled.

**Alternatives rejected:**
- Cloud firewall (security groups) only: defense in depth — host-level
  firewall catches misconfigured cloud rules.
- IDS/IPS (Snort/Suricata): high operational overhead for a single-node
  deployment; the alerting pipeline in observability.md already catches
  anomalous patterns.
- WAF (Cloudflare/mod_security): Caddy rate limiting + CORS strict +
  HMAC auth is sufficient for the V1 API surface; WAF adds latency and
  another external dependency.

## D12-5 — Supply chain: Dependabot + pip-audit + CI gate

> **ADR:** [ADR-0053](../../adr/INDEX.md#adr-0053) — Supply chain: Dependabot + pip-audit + CI gate

**Choice:** GitHub-native Dependabot for Python, Docker, and GitHub
Actions dependencies. `pip-audit` and `npm audit` in CI pipeline.
Critical/high CVE findings block merge. Container images built from
`python:3.12-slim`, no root user, SHA-pinned in production compose.

**Rationale:**
- Dependabot is free, integrated with GitHub, and requires zero
  operational overhead. `pip-audit` and `npm audit` are standard tools
  with minimal false-positive rates when configured correctly.
- Blocking merge on critical/high CVE prevents vulnerable code from
  reaching production — the CI gate is the enforcement point.
- `python:3.12-slim` provides glibc (needed by some quant libraries)
  while keeping the image small. No root user in containers limits the
  blast radius of a container escape.
- SHA-pinned images in production compose mean rollback is deterministic
  and `latest` cannot accidentally pull a compromised image.

**Alternatives rejected:**
- SBOM generation (SPDX/CycloneDX): adds compliance value but no
  security improvement for V1; can be added later.
- Container signing (Cosign/Notary): requires key management
  infrastructure; the threat of a compromised GHCR image is low and
  SHA-pinning already prevents tag-mutation attacks.
- Private PyPI mirror / artifact registry: pip-audit gates catch known
  vulnerabilities; a private mirror adds operational burden without
  changing the security outcome.

## D12-6 — Audit: security event log + Loki structured logs

> **ADR:** [ADR-0054](../../adr/INDEX.md#adr-0054) — Audit: security event log + Loki structured logs

**Choice:** PostgreSQL `security_events` table (append-only, 90-day
retention) for structured security events: auth attempts, kill-switch
toggles, order cancellations, proposal overrides, key rotations, deploy
events, and config changes. Loki + Promtail for all structured logs
with `security=true` label and `trace_id` correlation. Prometheus
alerting on security anomalies.

**Rationale:**
- Two complementary logging paths: PostgreSQL for queryable, structured
  audit trail; Loki for operational log correlation via `trace_id`.
- Append-only table with no DELETE permission means the audit trail
  cannot be tampered with by the application. Only direct SQL by the
  operator can modify or archive records.
- 90-day retention for security events (vs 30-day for operational logs)
  gives a longer investigation window for security incidents.
- Alerting on patterns (brute force, kill-switch, overrides) means the
  operator is notified of security-relevant events, not just system
  health events.

**Alternatives rejected:**
- SIEM integration (Splunk/ELK Cloud): self-hosted Loki + PostgreSQL
  is sufficient for a single-node deployment; SIEM adds cost and an
  external dependency.
- Blockchain/tamper-proof log: the threat model does not include an
  attacker with database root access; PostgreSQL access control +
  append-only policy is sufficient.
- Real-time anomaly detection ML: rules-based alerting catches the
  known patterns; ML adds complexity without clear benefit at V1 scale.

## Principles honored

- Phase 1 minimal-egress: no new egress added for security — all tools
  are self-hosted or GitHub-native.
- Defense in depth: three encryption layers, two audit paths, two SSH
  keys, two firewall layers (host + Caddy-level).
- Least privilege: deploy key scoped to `/srv/lumine/`, containers run
  as non-root, only 3 open ports.
- Fail closed: auth failure → reject; CVE critical → block merge;
  key compromise → rotate.
- Immutable evidence: `security_events` append-only; `trace_id` full
  correlation from Phase 9 through Phase 11.

## Phase boundary

Decisions D12-1..D12-6 are locked. Concrete SSH config, Caddyfile
security directives, UFW rules, Dependabot YAML, and `security_events`
migration belong to Phase 14+.