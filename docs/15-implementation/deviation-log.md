# Deviation Log — Phase 14 → Phase 15

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-02
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

## How to add an entry

1. Write the ADR first (`docs/adr/NNNN-…md`, append to `INDEX.md`).
2. Update the affected phase docs in the same PR.
3. Add a row here.
4. Update `spec-reconciliation.md` if the deviation changes a Phase 14
   spec claim.
