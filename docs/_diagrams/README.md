# Diagrams (Diagram-as-Code)

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 180

Diagrams are **code**: Mermaid (GitHub-native) for sequence/state/class,
D2 for topology. They render in GitHub, diff in PRs, and are RAG-friendly
(text). Prose diagrams rot; these don't.

## Files
- [`agent-hierarchy.mmd`](agent-hierarchy.mmd) — CEO/CIO/IC/analysts/Risk/PM/Exec/Journal/Perf.
- [`decision-flow.mmd`](decision-flow.mmd) — critical path: scheduler → committee → Risk → Sizer → lineage gate → MT5.
- [`data-flow.mmd`](data-flow.mmd) — data collection → features → analysis → decision → execution → journal.
- [`workflow-state-machine.mmd`](workflow-state-machine.mmd) — Phase 7 lifecycle states.
- [`deployment-topology.mmd`](deployment-topology.mmd) — Phase 11 topology.

## Embedding
Phase READMEs embed the relevant diagram via ```` ```mermaid ```` blocks
copied from these sources (or transcluded in tooling that supports it).
When a diagram changes, update the source here and the embedded copy in
the phase doc in the same PR.

## Anti-patterns
- Hand-drawn image diagrams (PNG/SVG) committed without source — not diffable.
- Prose-only descriptions of topology (rots silently).
- Diagrams that describe a different version than the code.
