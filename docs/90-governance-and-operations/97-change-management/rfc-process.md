# RFC Process

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 180

## When an RFC is required
- A change affecting ≥2 phases.
- A change to a phase boundary (Phase 5/9/10/11 ownership).
- A change to a `91-anti-scope-register.md` item (must supersede the rejecting ADR).
- A change to the critical path or the agent hierarchy.
- A new external dependency or a new storage system.

## When an ADR alone suffices
- A single-phase decision with no boundary impact.
- A decision that doesn't touch the anti-scope register.

## Process
1. Author copies `rfcs/0000-template.md` → `rfcs/NNNN-<short-title>.md`.
2. Open a PR with the RFC (no code). Tag reviewers per `CODEOWNERS`.
3. ARB reviews on its cadence (weekly) or asynchronously for time-sensitive items.
4. On acceptance: convert the RFC to an ADR (`docs/adr/NNNN-…md`), append
   to `INDEX.md`, update affected phase docs in the same PR.
5. Implementation PRs reference the ADR.

## RFC vs ADR
- RFC = proposal + discussion. Mutable. Lives in `rfcs/`.
- ADR = decision. Immutable once Accepted. Lives in `docs/adr/`.
- An accepted RFC produces exactly one ADR (or supersedes an existing one).
