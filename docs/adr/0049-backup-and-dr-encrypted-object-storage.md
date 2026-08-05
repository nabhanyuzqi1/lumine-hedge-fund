# ADR-0049 — Backup and DR: scheduled dumps to encrypted object storage

- **Status:** Accepted
- **Phase:** 11-infrastructure
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

A financial system cannot accept data loss from VPS failure. Local-only
backup is insufficient — VPS loss would mean data loss. Hot-standby
replication doubles VPS cost and adds replication-lag operational complexity
the current scale does not justify. Any backup egress must be explicit and
encrypted.

## Decision

Daily `pg_dump` (custom format) + continuous WAL archiving + Redis AOF +
volume sync, shipped via `rclone` (crypt remote, encrypted) to Backblaze B2 /
S3. Monthly automated restore test. RPO <= 24h (dump) / <= 5 min (WAL); RTO
hours via documented manual runbook.

## Rationale

- This is the only new egress approved, and it is explicit and encrypted.
- Local-only backup rejected — VPS loss would mean data loss, which is
  unacceptable for a financial system.
- Hot-standby replication rejected for V1: it doubles VPS cost and adds
  replication-lag operational complexity the current scale does not justify.
- Monthly restore test ensures the backup is verifiable, not just written.

## Consequences

- Positive: RPO <= 5 min via WAL; RTO hours via documented runbook.
- Positive: backup data is encrypted before leaving the VPS.
- Negative: one approved egress (encrypted, to object storage).
- Negative: restore is a manual runbook, not automated failover.
- Reversibility: upgrade to hot-standby replication by superseding this ADR.

## Cross-references

- Related ADRs: ADR-0050, ADR-0051
- Implements principle(s): #5, #7
- Affects phases: 11, 05
- Source document: `../11-infrastructure/decisions.md` (D11-5)
