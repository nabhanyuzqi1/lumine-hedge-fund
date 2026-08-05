# Runbook — Restore Test (Monthly DR Drill)

- **Status:** active · **Drilled:** no
- **Owner:** devops / cio
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

## Objective
Backups without restore tests = no backups. This runbook is drilled
**monthly** to prove RTO/RPO are achievable (`docs/11-infrastructure/backup-dr.md`).

## RTO / RPO targets
| Surface | RTO | RPO |
|---------|-----|-----|
| Critical path (trading) | 15 min | 1 min |
| Analytics (lineage/fills) | 4 h | 5 min |
| Audit (journal/WORM) | 1 h | 0 (append-only, WORM) |

## Drill steps
1. Spin up an isolated restore environment (not production).
2. Restore Postgres from the latest backup; restore Redis; restore S3 WORM.
3. Verify the hash chain (ADR-0017) end-to-end on the restored data.
4. Run a comparative re-execution (D7-8) against restored lineage — pins
   must resolve and outputs must match.
5. Measure elapsed time vs RTO; measure data loss vs RPO.
6. Record results in `sprint-evidence/drill-YYYY-MM.md`.
7. If RTO/RPO missed → P1 incident; resize infra or adjust targets via ADR.

## Pass criteria
- Restore completes within RTO.
- No data loss beyond RPO.
- Hash chain verifies.
- Comparative re-execution matches.
