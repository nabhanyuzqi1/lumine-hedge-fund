# ADR-0023 — Lineage partitioning + write-aside safety gate

- **Status:** Accepted
- **Phase:** 05-data
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

The blocking ACID lineage write is a single-table hotspot. The V1 estimate
(~100K rows/year, single symbol) is correct for V1 but explicitly V1-only.
Multi-asset target is ~10,000+ decisions/day, ~2.6M rows/year. At that
rate, write contention on the hot tail and vacuum pressure on the
append-only insert path become measurable problems. The blocking-gate
safety contract must be preserved without making the analytical hot table a
write bottleneck.

## Decision

`lineage_records` is partitioned by `decision_ts` MONTHLY, preemptively.
The blocking ACID gate writes to `lineage_pending` (small, hot,
monthly-partitioned); async promotion to `lineage_records` (analytical)
within 5s. Partition maintenance via pg_partman: pre-create 3 months
ahead, detach oldest to cold storage (S3/Parquet) after 2 years. Local
indexes per partition. Blocking-gate latency budget: p99 < 10ms on
`lineage_pending`. The V1 "no partitioning needed" claim in
`physical-erd.md` is corrected and superseded.

## Rationale

- `lineage_records` is append-only and time-range queried — the ideal
  partition candidate.
- Write-aside preserves the safety contract: a durable record exists before
  dispatch (in `lineage_pending`), equally durable (same PostgreSQL, same
  WAL, same backup).
- p99 < 10ms is achievable: small per-partition size, UUID PK (no sequence
  contention), no FK enforcement on write path.
- Cold storage via foreign table means audit replay of old decisions works
  without a restore.

## Consequences

- Positive: blocking-gate write latency is bounded at multi-asset scale.
- Positive: analytical queries use partition pruning for time-bounded
  ranges.
- Negative: the analytical table may lag by seconds (async promotion);
  a reconciliation worker re-promotes stragglers.
- Reversibility: partition scheme is physical (Phase 5); the safety
  contract is unchanged.

## Cross-references

- Related ADRs: ADR-0014, ADR-0005
- Implements principle(s): #6, #10
- Affects phases: 05, 03
- Source document: `../05-data/lineage-scale-and-partitioning.md` (S6)
