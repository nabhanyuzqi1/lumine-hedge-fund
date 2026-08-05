# Phase 2 — Department & Agent Architecture

## Status

- **Phase**: 2
- **Name**: Department & Agent Architecture
- **Prior phase**: Phase 1 — System Architecture (approved)
- **Next phase**: Phase 3 — Data Architecture

## Scope

Phase 2 deepens the 8 departments defined in Phase 1 into architectural detail:
LLM committee topology, deterministic sub-module boundaries, async worker
responsibilities, and cross-department interaction. Phase 2 fixes the
department architecture; implementation details (prompt text, AutoGen
configuration, payload field definitions, code) belong to later phases.

## Documents

| Document | Contents |
|----------|----------|
| `market-reasoning-department.md` | LLM committee (Technical/Macro/News/SMC → IC → CIO Proposer), adaptive parallel topology, per-role model version, sub-role responsibility |
| `risk-portfolio-department.md` | RiskValidator / PortfolioSizer / ExecutionRouter sub-modules, tiered kill switch, suspension flow |
| `execution-department.md` | ExecutionRouter + MT5 Bridge + listener, reconciliation flow, broker-side SL/TP, reconnect isolation |
| `research-review-sandbox.md` | Three async workers (Zone 3), hybrid split by function, closed learning loop |
| `governance-and-cross-department.md` | Authority hierarchy, interaction matrix, separation of authority, governance reporting |
| `decisions.md` | Locked decisions for Phase 2 |

## Authority statement

Phase 2 documents are architectural. They define department responsibilities,
boundaries, and interactions. They do NOT define:

- Prompt text (Phase 4 — Prompt Engineering)
- AutoGen agent configuration / implementation (Phase 4)
- Event payload field definitions (Phase 3)
- Database schema (Phase 3)
- Code of any kind (Phase 14+)

Where Phase 1 and Phase 2 appear to conflict, Phase 1 is the architectural
backbone and Phase 2 is the department deepening; both are authoritative
within their scope.
