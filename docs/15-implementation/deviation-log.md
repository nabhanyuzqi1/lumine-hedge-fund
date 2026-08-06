# Deviation Log — Phase 14 → Phase 15

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-06
- **Review-cadence:** 30

Every departure from the Phase 14 implementation plan is recorded here with
an ADR. No silent deviations. CLAUDE.md rule 4: architecture changes
update docs first.

## Deviations

| Date | Area | Deviation | Rationale | ADR | PR |
|------|------|-----------|-----------|-----|----|
| 2026-08-02 | Risk engine | LLM `risk_adjustment` continuous multiplier removed; replaced with deterministic regime/band lookup | Non-deterministic input on critical path violated reproducibility (#6) | ADR-0016 | — |
| 2026-08-02 | Audit | Journal gained hash-chain + WORM anchor | Tamper-evidence was asserted (D7-5) not constructed | ADR-0017 | — |
| 2026-08-02 | Security | Prompt injection added as explicit V1 threat | Network-layer threat model excluded application-layer injection via news ingestion | ADR-0018 | — |
| 2026-08-02 | Data | `lineage_records` partitioned monthly; write-aside `lineage_pending` for safety gate | V1 "no partitioning needed" claim was single-symbol-scoped; multi-asset growth re-estimated | ADR-0023 | — |
| 2026-08-02 | Trading | Schema made multi-broker-ready (accounts, brokers, BrokerRiskAdapter) | Single-broker schema is hard to reverse; CLAUDE.md goal is multi-broker | ADR-0024 | — |
| 2026-08-02 | AI | Memory architecture spec'd with four tiers and governed deferral triggers | Stateless V1 had no unblock path; capped system at "clever V1" | ADR-0027 | — |
| 2026-08-02 | Prompts | Promotion requires machine-enforced eval gate (`eval_pass_hash`) | Rule 10 satisfied "auditable" not "evaluated" | ADR-0028 | — |
| 2026-08-02 | Audit | `reasoning_traces` table stores full prompt + response, not just output | lineage stored "what", not "why"; audit/LP due-diligence needs "why" | ADR-0029 | — |
| 2026-08-02 | AI | Confidence calibration map added to model_versions; escalation uses calibrated confidence | Uncalibrated LLM confidence fired escalation on noise | ADR-0032 | — |
| 2026-08-02 | Data | Regime classifier made first-class, deterministic, versioned | Regime was an LLM input; strategies ran in wrong regime | ADR-0034 | — |
| 2026-08-02 | Trading | TCA records and execution-quality reporting spec'd | Execution bleed was invisible; best-exec evidence missing | ADR-0040 | — |
| 2026-08-02 | Trading | Daily broker reconciliation added as SETTLED gate | Internal SETTLED without broker reconciliation = silent position drift | ADR-0021 | — |
| 2026-08-06 | AI/Orchestration | Microsoft AutoGen declared in CLAUDE.md stack but NOT imported anywhere in `backend/src/lumine/`. Multi-agent orchestration implemented with a hand-written `autogen_pipeline/` (`_base.run_llm_stage`, `orchestrator.DecisionOrchestrator`) | AutoGen's conversational group-chat model fought the deterministic, single-turn, schema-validated stage contract (D7-11, ADR-0029). Custom runner keeps strict per-stage validation, trace-per-call audit, and deadline reserves (D3-12) under direct control. Naming retained (`autogen_pipeline/`) to honor the spec's module path | ADR-0068 | — |
| 2026-08-06 | Trading | Decision engine implemented at `autogen_pipeline/orchestrator.py` not `trade_core/decision_engine.py` as spec'd in `repository-structure.md` | `trade_core` owns deterministic sizing/risk/reconciliation/execution; the orchestration layer that wires LLM stages belongs with the LLM pipeline. Keeps `trade_core` LLM-free (CLAUDE.md "LLMs only for reasoning") | Pending ADR | — |
| 2026-08-06 | Risk engine | `resolve_risk_adjustment` except tuple widened from `(TypeError, ValueError)` to `(TypeError, ValueError, decimal.InvalidOperation)` | `Decimal("not_a_number")` raises `InvalidOperation` (an `ArithmeticError`, NOT a `ValueError` subclass). Original code violated the fail-closed contract (ADR-0016) by crashing instead of returning `DEFAULT_MULTIPLIER`. Regression test added in `test_risk_assessor.py::test_malformed_band_value_fails_closed` | ADR-0016 | — |
| 2026-08-06 | Audit/Lineage | `write_lineage()` gained keyword-only `commit: bool = True` parameter; orchestrator's `_write_lineage` calls it with `commit=False` and wraps the trace/journal FK backfill UPDATEs + final commit in one try/except that rolls back on failure | Previously `write_lineage` committed internally (txn 1) then the orchestrator issued two UPDATEs + its own commit (txn 2). Txn 2 failure left an orphan committed `lineage_records` row with unlinked `reasoning_traces`/`workflow_journal` — a write-before-dispatch (D3-7/D3-11) integrity gap. Now the lineage INSERT and the backfill share one transaction; both roll back together. `commit=True` default preserves all existing callers. Regression test `test_backfill_failure_rolls_back_lineage_atomically` | ADR-0017 | — |

## How to add an entry

1. Write the ADR first (`docs/adr/NNNN-…md`, append to `INDEX.md`).
2. Update the affected phase docs in the same PR.
3. Add a row here.
4. Update `spec-reconciliation.md` if the deviation changes a Phase 14
   spec claim.
