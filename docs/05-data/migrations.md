# Schema Migration Standard

## Overview

Decision **D5-5**: Alembic with linear versioning. Every physical schema
change is a versioned, reviewed, hashed migration file. This keeps the
physical schema auditable and reproducible (principles #6, #10).

## Rules

1. **Alembic, linear history.** One revision per change, chained
   `down_revision`. No branching migration trees.
2. **Every change is a migration.** No ad-hoc `ALTER TABLE` against the
   database. The migration files are the source of truth for physical
   structure.
3. **Explicit upgrade + downgrade.** Each migration defines both;
   rollback must be deliberate, not improvised.
4. **Reviewed like code.** A migration is approved before it runs
   against the system of record.
5. **Hash-audited.** Migration files are content-hashed so the applied
   schema state is verifiable against the repository (consistent with
   the registry `*_hash` audit pattern).

## Append-only constraint at the migration layer

Phase 3 immutability rules bind migrations too:

- Append-only tables (`lineage_records`, `fills`, registry tables) may
  receive additive migrations (new nullable column, new index) but never
  a migration that rewrites or deletes historical rows.
- Retention is always DROP PARTITION (structural), never a DELETE
  migration.

## Naming convention

```
<revision>_<short_slug>.py
e.g. 0007_add_fills_slippage_index.py
```

Slug is imperative and specific. One logical change per migration —
no bundled "misc" migrations.

## Ordering with partition lifecycle

Partition creation/DROP is a runtime lifecycle job (Phase 3
`data-lifecycle.md`), not a migration. Migrations own the *parent* table
structure; the lifecycle job owns rolling partitions. The two never
overlap: a migration never creates a dated partition, and the lifecycle
job never alters parent structure.

## What this document does NOT define

- Alembic environment/config code (Phase 14+).
- Migration CI gate (Phase 11/13).
- The logical schema itself (Phase 3).

## Phase Boundary

This document fixes the migration tool, versioning model, and audit
rules. It does not define config code or the logical schema.
