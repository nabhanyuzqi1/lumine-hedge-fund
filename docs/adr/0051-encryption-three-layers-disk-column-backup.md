# ADR-0051 — Encryption: three layers (disk, column, backup)

- **Status:** Accepted
- **Phase:** 12-security
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

A financial system stores secrets, credentials, and trade data on a cloud VPS.
A single encryption layer is insufficient: disk exfiltration, database dump,
and backup egress are distinct threats requiring independent controls. Three
separate keys with no circular dependency ensure compromising one layer does
not cascade.

## Decision

LUKS2/dm-crypt for full disk, `pgcrypto` for sensitive PostgreSQL columns
(`secret_hash`, `credentials`), `rclone crypt` for backup egress. Three
separate keys with no circular dependency.

## Rationale

- LUKS protects data if the physical disk or VPS volume is exfiltrated (cloud
  provider incident). Passphrase is separate from `.env` — no circular
  dependency during recovery.
- `pgcrypto` encrypts specific columns such that PostgreSQL never sees
  plaintext. Application-layer encrypt/decrypt means a database dump or
  compromised DB connection does not expose secrets.
- `rclone crypt` ensures backup data is encrypted before it leaves the VPS —
  the object storage provider never sees plaintext.
- Three separate keys mean compromising one layer does not cascade.
- HSM rejected: not available on commodity VPS; disproportionate cost and
  complexity for V1.
- PostgreSQL TDE rejected: requires enterprise license; `pgcrypto`
  column-level encryption is sufficient for the specific columns that need
  protection.
- TPM-based auto-unlock for LUKS rejected: cloud VPS typically lacks TPM;
  manual unlock at boot is acceptable for a single-node deployment.

## Consequences

- Positive: three independent encryption layers — no single key compromise
  exposes all data.
- Positive: backup egress is encrypted at source.
- Negative: LUKS manual unlock at boot requires operator presence for VPS
  restart.
- Reversibility: each layer is independently replaceable.

## Cross-references

- Related ADRs: ADR-0001, ADR-0002, ADR-0049
- Implements principle(s): #10
- Affects phases: 12, 05
- Source document: `../12-security/decisions.md` (D12-3)
