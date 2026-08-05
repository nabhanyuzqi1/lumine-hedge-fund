# ADR-0017 — Hash-chained, WORM-anchored audit journal

- **Status:** Accepted
- **Phase:** 12-security
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

The journal is declared truth (D7-5) and `lineage_records` is the blocking
ACID gate (Phase 3). But "append-only by convention" is not tamper-proof:
a bug or a compromised container with write access can UPDATE or DELETE
rows and erase evidence. D12-1 explicitly excludes the insider attacker
from V1 scope, but a bug or a compromised container can still corrupt the
audit trail silently. Tamper-evidence was asserted (D7-5), not
constructed.

## Decision

The audit trail is hash-chained and WORM-anchored. Each append-only audit
row carries `prev_hash` and `self_hash` (SHA-256 of canonical JSON). The
chain head is anchored externally to an S3/B2 Object Lock in Compliance
mode (retention >= 1 year) every N=1000 rows or M=5 minutes, whichever
fires first. The `audit_writer` role is the only role that may INSERT into
audit tables; `lumine_app` loses UPDATE/DELETE/TRUNCATE on all audit
tables. A daily verification job recomputes the chain and checks the WORM
objects; any mismatch pages the operator and freezes the pipeline.

## Rationale

- Hash chain detects any in-place row modification or deletion.
- WORM anchor prevents rewriting the anchored chain head (Compliance mode
  retention — no identity, including root, can delete).
- DB grant hardening is the primary tamper-prevention control; chain and
  anchors are defense-in-depth for bugs, compromised containers, and
  superuser abuse.
- Both are required: the chain catches tampering inside the anchor lag
  window; the WORM anchor makes anchored history irrefutable.

## Consequences

- Positive: audit trail is tamper-evident and tamper-resistant.
- Positive: a compromised container cannot silently edit history (DB
  rejects UPDATE/DELETE).
- Negative: anchor lag window (up to 5 minutes / 1000 rows) is not
  WORM-protected — covered by the hash chain.
- Reversibility: canonicalization is versioned; chain is append-only.

## Cross-references

- Related ADRs: ADR-0005, ADR-0007, ADR-0014
- Implements principle(s): #4, #10
- Affects phases: 12, 05, 07
- Source document: `../12-security/audit-tamper-evidence.md` (S2)
