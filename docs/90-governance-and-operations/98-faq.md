# FAQ

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 180

## Architecture

**Why stateless V1?** Reproducibility (principle #6). Hidden memory makes
replay depend on unrecorded state. Learning happens by version promotion,
not agent memory. See ADR-0003, ADR-0027.

**Where do I find a decision?** `docs/adr/INDEX.md`. Phase `decisions.md`
files are pointers.

**Why two `data`-ish folders?** We renamed: `03-agents-and-contracts/`
(agent registry, lineage, feature store, regime, calendar) and `05-data/`
(physical storage). One logical, one physical. See ADR-0014 and
`phase-mapping.md`.

**Why is the LLM risk adjustment removed?** It was a non-deterministic input
to position sizing. The LLM is now advisory; the sizing multiplier is a
deterministic registry lookup. See ADR-0016.

## Implementation

**Why is `trade_core/` empty when the spec lists files?** Phase 15 is in
progress. See `docs/15-implementation/spec-reconciliation.md` for the
spec-vs-reality table. Don't trust the spec alone; check reconciliation.

**How do I run things?** `make help`. CI runs the same targets.

**Why is the frontend empty?** Sprint 6. See `frontend-sprint-plan.md`.

## Operations

**Who can clear the kill switch?** Only the CIO/human authority. Never the
system. See ADR-0010.

**A reconciliation broke — what do I do?** `94-runbooks/reconciliation-break.md`.
Don't resume trading until it passes.

**The hash chain broke — what do I do?** P0. `94-runbooks/chain-verification-failure.md`.
Halt trading.

## AI

**Can I ship a prompt without an eval?** No. The promotion API refuses
(ADR-0028). Run `make eval` first.

**Why did the system escalate to the expensive tier?** Deterministic
triggers in `model-routing.md` using **calibrated** confidence (ADR-0032).
If it's over-escalating, calibration may have drifted.

**Can agents remember past decisions?** Not in V1 (stateless). Episodic
memory (lineage-backed) is allowed; semantic/procedural memory are deferred
with triggers (ADR-0027).
