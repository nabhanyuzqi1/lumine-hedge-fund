# Architecture Review Board (ARB)

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 180

## Membership
- Chief Architect (chair).
- CIO (or delegate) — for capital/risk implications.
- One representative each from: backend, AI/LLM, data, frontend, devops, QA.
- Rotating seat for a quant researcher.

## Cadence
- Weekly review of open RFCs.
- Async review for time-sensitive items (P0/P1 driven).
- Quarterly review of the ADR registry for stale/superseded entries.

## Decision authority
- The ARB **recommends**; the CIO **approves** for capital-impacting changes.
- Non-capital architectural changes: ARB approves by consensus; recorded as ADR.
- Disagreement escalation: to the CIO; the CIO's decision is final and recorded.

## Quorum
- Chair + ≥3 members, including at least one from a phase NOT primarily
  affected by the RFC (cross-phase sanity check).
