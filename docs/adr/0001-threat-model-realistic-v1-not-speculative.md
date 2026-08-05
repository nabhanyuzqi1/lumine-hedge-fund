# ADR-0001 — Threat model: realistic V1, not speculative

- **Status:** Accepted
- **Phase:** 12-security
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

A single-node VPS with one operator has a fundamentally different threat
profile than a multi-tenant SaaS platform. Over-modeling the threat surface
creates security theater — controls that add operational burden without
addressing real attack vectors. The most likely V1 attack vectors
(credential exposure, API replay/brute force, dependency compromise, SSH
brute force) are all addressable with standard controls. Phase 9 HMAC-SHA256
signing already provides request-level authentication and replay protection;
Phase 12 adds the infrastructure layer.

## Decision

Threat model is scoped to what an attacker can actually reach in V1 —
network-layer access, port scanning, replay attacks, brute force attempts.
The following are explicitly NOT threats for V1: insider attack (operator
is the only human), physical access (cloud VPS), regulatory compliance
enforcement, multi-tenant isolation, and sophisticated DDoS.

## Rationale

- A single-node VPS deployment has a narrow, addressable attack surface.
- Full STRIDE/Linddun produces a 50-page catalog where 80% of entries do
  not apply — disproportionate for V1.
- Compliance-first (SOC 2 / ISO 27001) has no V1 requirement and would
  prematurely constrain architecture.
- Phase 9 HMAC-SHA256 already covers request-level auth/replay.

## Consequences

- Positive: security effort concentrates on real V1 vectors (credentials,
  replay, dependencies, SSH).
- Positive: avoids operational burden of controls that do not address real
  threats.
- Negative: threat model must be revisited when scaling beyond single-node.
- Reversibility: re-scope by superseding this ADR when deployment topology
  changes.

## Cross-references

- Related ADRs: ADR-0002, ADR-0018
- Implements principle(s): #10
- Affects phases: 12
- Source document: `../12-security/decisions.md` (D12-1)
