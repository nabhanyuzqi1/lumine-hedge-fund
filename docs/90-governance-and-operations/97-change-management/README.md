# Change Management

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 180

How architectural change happens at Lumine. CLAUDE.md rule 4: architecture
changes update docs first. This tier makes that rule enforceable.

## RFC process
- [`rfc-process.md`](rfc-process.md) — when an RFC is required, how it's reviewed, how it becomes an ADR.
- [`rfcs/0000-template.md`](rfcs/0000-template.md) — RFC template.
- `rfcs/` — proposed and accepted RFCs.

## Architecture Review Board (ARB)

- [`architecture-review-board.md`](architecture-review-board.md) — membership, cadence, decision authority.

## Relationship to ADRs

- An RFC proposes; an ADR records the decision.
- Small changes: ADR directly (no RFC).
- Large changes: RFC → ARB review → ADR.
- The `91-anti-scope-register.md` items require an RFC that supersedes the
  rejecting ADR before work begins.
