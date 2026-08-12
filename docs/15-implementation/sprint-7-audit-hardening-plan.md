# Sprint 7 — Audit Hardening Plan: Hash Chain, WORM Anchor, Reasoning Traces, TCA

**Status:** Final — decisions resolved; awaiting approval gate (ADR-0042: no coding before plan approval)
**Date:** 2026-08-12
**Sprint:** 7 (Audit hardening) of Phase 15 — Implementation
**Owner:** backend
**Prior sprints:** Sprint 1–5 Done (full gate PASS); F-Sprint 1–6 Done; evidence in `sprint-evidence/`

---

## 1. Sprint Goal

Close the audit-hardening gap between the approved ADRs (0017, 0029,
0040) and the current codebase. Three of the four scope items are
greenfield (no `prev_hash`/`self_hash`/`audit_anchors`/`tca_records`
anywhere in `backend/src/lumine/**`); reasoning traces exist in part
(migration 0006 + `autogen_pipeline/traces.py`) and need gap-closure
and hardening. Everything runs locally without Docker/VPS — the WORM
sink is emulated on the local filesystem (the S3/B2 Object Lock
configuration is a Phase 11 operator action, out of scope here).

**Exit criteria (this plan's items):**
- **J1 Hash chain core** — `backend/src/lumine/security/hashchain.py`
  implements canonical JSON (per ADR-0017 rules), `prev_hash`/
  `self_hash` computation, and chain append for two chained tables:
  `lineage_records` and `workflow_journal`. The chain is per-table,
  append-only, and the first row's `prev_hash = SHA-256("GENESIS")`.
- **J2 Chain columns + audit_anchors migration** — `alembic` migration
  `0007` adds `prev_hash`, `self_hash`, `canonicalization_version`
  (NOT NULL, DEFAULT 1) to `lineage_records` + `workflow_journal`, and
  creates `audit_anchors` (per ADR-0017 logical DDL). Backfill for
  existing rows is a one-time script; the migration is idempotent.
- **J3 Chain writer integration** — `write_lineage` (`data/lineage.py`)
  and `log_step` (`autogen_pipeline/journal.py`) compute and store
  `prev_hash`/`self_hash` inside their existing transactions; a chain
  integrity failure (mismatch) fails the write (safe state by default).
- **J4 WORM anchor (local emulation)** — `security/anchoring.py`
  implements the anchor cadence (every N=1000 rows or M=5 minutes,
  whichever first), writes the chain head to `audit_anchors` and to a
  local file-based WORM sink (append-only directory with hashed
  filenames — no overwrite/delete from the app role). The S3/B2
  Object Lock sink is stubbed behind an interface; the stub documents
  the Phase 11 wiring.
- **J5 Chain verification job** — `scripts/verify_chain.py` (or
  `security/verifier.py`) recomputes the full chain per table, checks
  every `prev_hash` link, verifies each `audit_anchors` row against the
  anchored row + the local WORM copy; on mismatch it emits a
  `security_events` row of type `chain_break` and exits non-zero
  (freeze semantics are an ops action; the exit code + event is the
  contract). `make verify-chain` target.
- **J6 DB grant hardening (SQL only, documented)** — migration `0007`
  includes the `audit_writer` role + `REVOKE UPDATE/DELETE/TRUNCATE`
  for `lumine_app` on `lineage_records`, `workflow_journal`,
  `audit_anchors` (per ADR-0017 D12-8). Local dev DB runs as a
  superuser so grants are documented + test-asserted, not enforced
  locally; enforcement is a Phase 11/VPS operator action.
- **J7 TCA records** — migration `0007` creates `tca_records`
  (1:1 with `fills`, per ADR-0040); `trade_core/tca.py` computes
  arrival-mid benchmark from the feature store (point-in-time),
  session-clamp to next-open mid, slippage in bps + cost in account
  currency, and writes the record inside the fill transaction;
  `execution_router.py` calls it. `regime_id` from
  `RegimeVersion`/risk assessor output.
- **J8 TCA rollups + alerts** — materialized views
  `tca_daily_strategy/broker/symbol/regime/session` (per ADR-0040);
  `security/` or `monitoring/` breach detection: per-fill
  `slippage_breach` alert + cluster page (`slippage_cluster`), fed
  from the rollups. Thresholds are policy-driven (per-symbol,
  per-regime) with defaults (5 bps normal, 10 bps high_vol on XAUUSD).
- **J9 Reasoning traces gap-closure** — traces already write
  `prompt_hash`/`response_hash`; close the remaining spec gaps:
  `lineage_records.proposal` gains `reasoning_trace_ids` array on
  write, `_reasoning_gap` flag on parsed_output where the provider
  exposes no reasoning tokens, and traces are added to the hash chain
  (chained table, same canonicalization) — keeping the D7-11 replay
  integrity contract.
- **J10 Tests** — unit tests for canonicalization + chain append +
  verification (including tamper detection: modify a row mid-chain →
  verifier fails), integration tests for migration 0007 on the
  container DB (chain columns, audit_anchors, tca_records),
  TCA benchmark math (arrival mid + session clamp), and the trace
  gap-closure; contract test for the anchor payload shape.
- **J11 Evidence + docs** — `sprint-evidence/sprint-7-audit-hardening.md`
  with the full gate table; update `docs/15-implementation/README.md`
  Sprint 7 row; add the `verify-chain` runbook reference.

**Out of scope (deferred):**
- S3/B2 Object Lock bucket creation + retention policy (Phase 11
  operator action; the local file sink is the dev-time emulation).
- `audit_writer` role enforcement in local dev (superuser dev DB).
- Public transparency log / Merkle proofs (explicitly not in V1 per
  ADR-0017).
- Spec-gap closures unrelated to audit (feature_provider,
  prompts/registry, agent registry, LLM gateway) — separate plan.
- Frontend changes; TCA dashboards are Phase 10/15-frontend follow-up.

---

## 2. Current-state inventory (what exists today)

| Area | Status | Evidence |
|------|--------|----------|
| Hash chain columns | Not present | `models.py` has no `prev_hash`/`self_hash`; grep across `src/lumine` returns nothing |
| `audit_anchors` table | Not present | Alembic 0001–0006 list; no anchor table |
| WORM anchor code | Not present | `data/lineage.py` has no anchor logic |
| Reasoning traces | Partial | Migration 0006 + `ReasoningTrace` model + `write_trace()` + integration tests; NO chain linkage, NO `reasoning_trace_ids` in proposal, NO `_reasoning_gap` flag |
| TCA | Not present | `Fill.slippage` raw column only; no `tca_records`, no benchmark, no rollups, no alerts |
| DB roles/grants | Not enforced | `docs/90-governance-and-operations/93-standards/db-standards.md:39` documents the intent; no migration grants |

---

## 3. Implementation notes

- **Canonicalization** follows ADR-0017 byte-exact rules (sorted keys,
  `separators=(",", ":")`, `default=str` for TIMESTAMPTZ → ISO 8601
  UTC `Z`, UUID lowercase, NUMERIC plain decimal, JSONB recursively
  sorted, NULL literal, no trailing newline).
- **Chain model**: per-table chains; `prev_hash` = SHA-256 of previous
  row's canonical JSON; `self_hash` = SHA-256 of
  `prev_hash || canonical(self without self_hash)`. First row
  `prev_hash = SHA-256("GENESIS")`.
- **Anchor cadence**: every 1000 rows or 5 minutes, whichever fires
  first; both sinks receive the same payload (DB + local WORM file).
- **Reasoning traces**: keep existing `write_trace` contract (it is
  load-bearing for replay); add chain columns + proposal linkage.
- **TCA**: benchmark is arrival mid from the feature store at
  `decision_ts` (DB-authoritative); session-clamp to next-open mid
  when `calendar.is_closed`; `benchmark_source: "arrival_mid"` or
  `"session_open"` recorded.
- **Local-first**: no Docker/VPS dependency; the WORM sink is a local
  append-only directory. CI exercises the same code path with a temp
  dir.
- **Grants**: D12-8 SQL is shipped in the migration but the local
  dev/test DB runs as superuser; a test asserts the role statements
  are syntactically valid against the container DB where feasible.

---

## 4. Quality gates (must pass before evidence is filed)

| Gate | Command |
|------|---------|
| Lint | `uv run ruff check src/ tests/ scripts/` |
| Format | `uv run ruff format --check src/ tests/ scripts/` |
| Types | `uv run mypy src/ scripts/` |
| Unit + contract | `uv run pytest tests/unit/ tests/contract/` |
| Integration (J2/J7/J10) | `uv run pytest tests/integration/` (container DB; includes migration 0007) |
| Coverage gate | `uv run pytest tests/unit/ tests/contract/ --cov --cov-fail-under=80` |
| Chain verify self-check | `make verify-chain` on a seeded DB — PASS |
| Security | `make security` (bandit -ll, gitleaks, pip-audit) |
| OpenAPI drift | `make openapi && git diff --exit-code` (no API surface change expected) |
| Independent verification agent | Required before reporting done |

---

## 5. Risks & mitigations

- **Canonicalization drift** (e.g. Decimal serialization variance) →
  lock rules in unit tests against ADR-0017 examples; byte-identity
  test in CI.
- **Backfill of existing rows** (0001–0006 data) → one-time script
  computes the chain over historical rows in `created_at` order;
  verified by J5 before/after hash equality.
- **TCA benchmark data gaps** (feature store lacks mid at
  `decision_ts`) → session-clamp path with `benchmark_source` marker;
  alert on gap rate.
- **Anchor lag window** (rows after last anchor unprotected) → the
  daily verifier + chain break detection covers the lag window; this
  is the ADR-0017-accepted residual risk.
- **Testcontainers flakiness** (integration suite) → session-scoped
  containers already in place; migration 0007 is idempotent.

---

## 6. Resolved decisions (best practice — 2026-08-12)

1. **WORM emulation: local file sink approved** — the dev-time stand-in
   for S3/B2 Object Lock is an append-only local directory; the
   interface stays the same so Phase 11 wires the real backend with
   zero code change.
2. **Reasoning traces join the hash chain** — traces are a chained
   table (same canonicalization as lineage/journal). `response_hash`
   remains a fingerprint (ADR-0029 contract unchanged); the chain
   columns add tamper-evidence at negligible cost.
3. **TCA alert thresholds: 5 bps normal / 10 bps high_vol on XAUUSD** —
   institutional-standard defaults, overridable via policy (per-symbol,
   per-regime).

Implementation starts only after this plan is approved.
