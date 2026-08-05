# ADR-0053 — Supply chain: Dependabot + pip-audit + CI gate

- **Status:** Accepted
- **Phase:** 12-security
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

Dependency compromise is one of the most likely V1 attack vectors
(ADR-0001). Vulnerable dependencies must be caught at CI time, not after
deployment. Container images must be deterministic and non-root to limit
blast radius of a container escape.

## Decision

GitHub-native Dependabot for Python, Docker, and GitHub Actions dependencies.
`pip-audit` and `npm audit` in CI pipeline. Critical/high CVE findings block
merge. Container images built from `python:3.12-slim`, no root user,
SHA-pinned in production compose.

## Rationale

- Dependabot is free, integrated with GitHub, and requires zero operational
  overhead. `pip-audit` and `npm audit` are standard tools with minimal
  false-positive rates when configured correctly.
- Blocking merge on critical/high CVE prevents vulnerable code from reaching
  production — the CI gate is the enforcement point.
- `python:3.12-slim` provides glibc (needed by some quant libraries) while
  keeping the image small. No root user in containers limits the blast radius
  of a container escape.
- SHA-pinned images in production compose mean rollback is deterministic and
  `latest` cannot accidentally pull a compromised image.
- SBOM generation (SPDX/CycloneDX) rejected: adds compliance value but no
  security improvement for V1; can be added later.
- Container signing (Cosign/Notary) rejected: requires key management
  infrastructure; the threat of a compromised GHCR image is low and
  SHA-pinning already prevents tag-mutation attacks.
- Private PyPI mirror rejected: pip-audit gates catch known vulnerabilities;
  a private mirror adds operational burden without changing the security
  outcome.

## Consequences

- Positive: vulnerable dependencies are blocked at CI before reaching
  production.
- Positive: container images are deterministic and non-root.
- Negative: critical/high CVE blocks can delay urgent deploys (mitigated:
  operator can override with documented reason).
- Reversibility: CI gate policy is configurable; SBOM and signing can be
  added later.

## Cross-references

- Related ADRs: ADR-0001, ADR-0047
- Implements principle(s): #10
- Affects phases: 12, 14
- Source document: `../12-security/decisions.md` (D12-5)
