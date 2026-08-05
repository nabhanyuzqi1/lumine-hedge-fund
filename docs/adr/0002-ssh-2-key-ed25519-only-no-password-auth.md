# ADR-0002 — SSH: 2-key ed25519-only, no password auth

- **Status:** Accepted
- **Phase:** 12-security
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

The VPS requires remote administration and CI-based deployment. A single
SSH key shared between CI and the operator violates least privilege: a CI
secret leak becomes full root compromise. Password authentication leaves a
brute-force vector open. RSA keys are larger and slower with no benefit over
ed25519 for this deployment.

## Decision

Two SSH keys, both ed25519: (a) CI deploy key, non-root, scoped to
`/srv/lumine/` via `command=` restriction, stored as GitHub Actions secret;
(b) admin key, full sudo, held by operator in password manager. Password
authentication disabled. Root login disabled.

## Rationale

- ed25519 is the modern standard: smaller keys, faster signing, no known
  weaknesses vs RSA.
- Two keys separate concerns — CI cannot escalate to root; operator cannot
  accidentally leak the deploy key through CI.
- `command=` restriction limits blast radius of a compromised CI secret to
  `docker compose` commands in `/srv/lumine/`.
- No password auth eliminates the brute-force vector entirely.
- VPN/WireGuard and bastion host rejected as disproportionate for a single
  node.

## Consequences

- Positive: least privilege enforced at the SSH layer.
- Positive: CI secret compromise cannot root the box.
- Negative: operator must manage two keys and a password manager entry.
- Reversibility: key rotation is straightforward; topology change requires
  a new ADR.

## Cross-references

- Related ADRs: ADR-0001
- Implements principle(s): #10
- Affects phases: 12
- Source document: `../12-security/decisions.md` (D12-2)
