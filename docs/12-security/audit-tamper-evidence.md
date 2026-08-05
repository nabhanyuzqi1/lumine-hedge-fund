# Audit Tamper-Evidence Contract

## Overview

The journal is declared truth (D7-5) and `lineage_records` is the
blocking ACID gate (Phase 3). But "append-only by convention" is not
tamper-proof: an attacker (or operator, or bug) with write access can
UPDATE or DELETE rows and erase evidence. D12-1 explicitly excludes the
insider attacker from V1 scope, but a *bug* or a *compromised
container* can still corrupt the audit trail silently. This document
fixes that with two complementary controls:

1. **Detection** — a hash chain over journal + lineage rows so any
   in-place modification is computationally evident.
2. **Prevention** — WORM-anchored copies of the chain head so a
   database-level attacker cannot rewrite history without leaving a
   gap visible in the external anchor.

Decision **D12-7**: the audit trail is hash-chained and WORM-anchored.
Decision **D12-8**: DB grants are hardened so the application role
cannot UPDATE or DELETE audit tables.

## Decision D12-7 — Hash-chained, WORM-anchored audit trail

### Hash chain

Each append-only audit row carries `prev_hash` and `self_hash`:

- `prev_hash` = SHA-256 of the previous row's canonical JSON.
- `self_hash` = SHA-256 of `prev_hash || canonical_json(self without self_hash)`.

The first row in a chain has `prev_hash = SHA-256("GENESIS")`. Each
table that participates in tamper-evidence maintains its own chain;
chains are independent per table so a write to one does not stall the
other.

Tables in scope of the chain (V1):
- `lineage_records` (the blocking ACID gate).
- the journal table backing D7-5 (physical schema Phase 5).

Canonicalization (deterministic, byte-exact):

```
canonical_json(row) =
  json.dumps(
    {k: row[k] for k in sorted(row.keys()) if k != "self_hash"},
    sort_keys=True,
    separators=(",", ":"),
    default=str             # TIMESTAMPTZ -> ISO 8601 UTC, no whitespace
  ).encode("utf-8")
```

Rules:
- Timestamps serialize as UTC ISO 8601 with `Z` suffix, no fractional
  whitespace, no locale. Naive timestamps are a hard error at write time.
- UUIDs serialize as lowercase canonical text.
- NUMERIC serializes as the plain decimal string with no trailing zeros
  and no scientific notation.
- JSONB nested values are recursively sorted by key.
- NULL serializes as the literal JSON `null`.
- No trailing newline, no BOM, no pretty-printing.

The canonical form is itself versioned (a `canonicalization_version`
field on the row, currently `1`). A future change to canonicalization
bumps this field and re-anchors; it never silently rewrites old rows.

### Anchoring

The chain head (the latest `self_hash`) is anchored externally at the
soonest of:

- every **N = 1000** rows appended to a chained table, or
- every **M = 5 minutes** of wall-clock time, whichever fires first.

An anchor writes the chain head to two sinks:

1. **External WORM sink** — S3 (or B2) Object Lock in **Compliance
   mode** with a retention period of at least 1 year. Once written,
   no identity — including root — can delete or overwrite the object
   until retention expires. Object key includes table name, anchor
   sequence, and the `self_hash` being anchored.
2. **Append-only `audit_anchors` table** in PostgreSQL (see below).

Both sinks receive the same payload. The DB table is the fast-query
copy; the WORM object is the irrefutable copy. A mismatch between them
is itself a tamper signal.

`audit_anchors` (logical; physical DDL is Phase 5):

```sql
CREATE TABLE audit_anchors (
  anchor_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  table_name       TEXT NOT NULL,                 -- 'lineage_records' | journal table
  anchor_seq       BIGINT NOT NULL,               -- monotonic per table
  anchored_hash    TEXT NOT NULL,                 -- the self_hash being anchored
  anchored_row_id  UUID NOT NULL,                 -- PK of the row whose self_hash is anchored
  row_count        BIGINT NOT NULL,               -- rows chained so far for this table
  anchored_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  worm_object_key  TEXT NOT NULL,                 -- S3/B2 Object Lock key
  worm_backend     TEXT NOT NULL,                 -- 's3' | 'b2'
  UNIQUE (table_name, anchor_seq)
);
```

`audit_anchors` is itself chained: `anchored_hash` of anchor *k* must
equal the `self_hash` of the row that anchor *k* claims to anchor, and
the chain of anchors must be gap-free per `table_name`. Anchors are
written by the `audit_writer` role only (see D12-8).

### Detection vs prevention

| Control | What it does | What it does not do |
|---------|--------------|---------------------|
| Hash chain | Detects any in-place row modification or deletion (the next row's `prev_hash` no longer matches) | Does not stop the write from happening |
| WORM anchor | Prevents rewriting the anchored chain head (Compliance mode retention) | Does not protect rows written after the last anchor (the "anchor lag" window) |
| `audit_writer` role + REVOKE (D12-8) | Prevents the application role from mutating audit tables at all | Does not stop a DB superuser |

Both are required. The hash chain catches tampering inside the anchor
lag window; the WORM anchor makes the anchored history irrefutable. The
role hardening (D12-8) removes the application's ability to tamper at
all, which is the primary control; the chain and anchors are
defense-in-depth for bugs, compromised containers, and superuser abuse.

## Decision D12-8 — DB grant hardening

The application role (`lumine_app`) used by `trade-core` and the
listener historically had broad DML. For audit tables that must hold:

```sql
REVOKE UPDATE, DELETE ON lineage_records FROM lumine_app;
REVOKE UPDATE, DELETE ON <journal_table> FROM lumine_app;
REVOKE UPDATE, DELETE ON audit_anchors   FROM lumine_app;
REVOKE TRUNCATE ON lineage_records, <journal_table>, audit_anchors FROM lumine_app;

-- Only the dedicated role may write audit rows.
GRANT INSERT ON lineage_records, <journal_table> TO audit_writer;
GRANT INSERT ON audit_anchors TO audit_writer;
-- audit_writer has NO UPDATE, NO DELETE, NO TRUNCATE on these tables.
```

- `lumine_app` retains INSERT on `lineage_records` and the journal so
  the blocking ACID gate still works; it loses UPDATE/DELETE/TRUNCATE
  on all audit tables.
- `audit_writer` is a separate role used only by the anchoring job and
  by the journal/lineage writers. It can INSERT only.
- A migration to add columns/indexes is performed by the `lumine_owner`
  role (operator-only), never by the application.
- `positions` (the derived snapshot) remains mutable by `lumine_app` —
  it is rebuildable from `fills`, not an audit table.

This means a compromised `trade-core` container cannot silently edit
history: the DB rejects the UPDATE/DELETE outright. This is the
primary tamper-prevention control; the chain and WORM anchors are
defense-in-depth.

## Daily chain-verification runbook

A scheduled job (Phase 11 ops) runs daily:

1. For each chained table, read rows in chain order from row 1.
2. Recompute `self_hash` for every row from its canonical JSON.
3. Verify each row's `prev_hash` equals the previous row's `self_hash`.
4. Verify the chain length equals the row count.
5. For each `audit_anchors` row, verify `anchored_hash` matches the
   `self_hash` of the referenced row, and verify the WORM object exists
   and its content hash matches `anchored_hash`.
6. On any mismatch: emit a `security_events` row of type
   `chain_break`, page the operator (D12-6 alerting), and freeze the
   decision pipeline (no new lineage writes) until resolved. Safe state
   by default (principle #10).

The verification job runs with a read-only role. It never writes to the
chain tables. Its own log is shipped to Loki (D12-6).

## Interaction with D7-8 (replay never mutates)

- The chain is append-only. Replay (audit replay or comparative
  re-execution, D7-8) never UPDATEs a chained row.
- Comparative re-execution writes **new** rows with a new
  `workflow_run_id` and a `replay_of` reference to the original. These
  new rows extend the chain; they never overwrite the original.
- A comparison row's `risk_context` / `proposal` carries the
  comparative result plus a `comparison_target` field pointing at the
  original `lineage_id`. The chain simply grows.
- Because the chain only grows, the daily verifier is monotonic: a
  verified prefix stays verified.

## Phase boundary

- Physical DDL for `audit_anchors`, the `prev_hash`/`self_hash` columns
  on `lineage_records` and the journal table, partitioning, and
  retention of `audit_anchors` belong to Phase 5. This document fixes
  the contract and the canonicalization rules.
- The WORM bucket configuration (Object Lock retention, bucket policy)
  belongs to Phase 11 infrastructure.
- The verification job scheduling and alerting wiring belong to Phase
  11/14.
- This document does not redefine the journal's logical fields (D7-5)
  or the lineage schema (Phase 3); it adds the tamper-evidence columns
  and the anchor table on top.

## What this document does NOT define

- Numeric values for anchor retention (Phase 11; minimum 1 year here).
- The WORM backend choice (S3 vs B2) — Phase 11.
- Verification job implementation code — Phase 14+.
- A public transparency log (e.g. Merkle proofs published outside the
  VPS). Not in V1 scope; the WORM anchor is the V1 irrefutable copy.

## Phase boundary

This document fixes the hash-chain contract, the anchoring cadence and
sinks, the DB grant hardening, and the daily verification runbook. It
does not define physical DDL (Phase 5), WORM bucket config (Phase 11),
or code (Phase 14+).
