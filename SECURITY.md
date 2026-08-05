# Security Policy

## Reporting a vulnerability

Email security@<redacted> with a description and reproduction. Do not open
a public issue for security vulnerabilities.

We acknowledge within 48 hours and target a fix or mitigation within 30 days
for high-severity issues. Reporters are credited (with consent) in the
release notes.

## Threat model scope

V1 threat model (`docs/12-security/threat-model.md`, ADR-0001) covers
network-layer access, port scanning, replay, brute force, credential
exposure, dependency compromise, and SSH brute force. **Prompt injection**
is an explicit V1 threat (ADR-0018) — it is an application-layer attack via
the system's own data ingestion and falls outside the network-layer model.

Explicitly **out of scope for V1**: insider attack (single operator),
physical access (cloud VPS), regulatory compliance enforcement,
multi-tenant isolation, sophisticated DDoS.

## Hardening posture

- SSH: ed25519-only, 2-key, password auth disabled (ADR-0002).
- Encryption: see `docs/12-security/encryption.md`.
- Network/firewall: see `docs/12-security/network-firewall.md`.
- Supply chain: see `docs/12-security/supply-chain.md` and the CI supply-chain
  enforcement job.
- Audit tamper-evidence: hash-chained, WORM-anchored journal (ADR-0017).
- Secrets: `docs/12-security/secrets-management.md`.

## Supported versions

Only the latest release branch receives security fixes.
