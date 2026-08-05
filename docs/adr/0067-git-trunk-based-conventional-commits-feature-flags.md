# ADR-0067 — Git: trunk-based, conventional commits, feature flags

- **Status:** Accepted
- **Phase:** 14-implementation
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

Long-lived branches accumulate drift and produce painful merges. A
single-operator project needs the ability to merge incomplete work to main
without affecting the running system. Commit history should be machine-readable
for changelog generation. Main branch history should be linear and clean.

## Decision

Trunk-based development — no long-lived branches. Feature flags
(`LUMINE_FEATURE_<NAME>`) for incomplete features on main. Conventional
commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `ci:`).
PR required for all changes; squash merge to main.

## Rationale

- Trunk-based development minimizes merge conflicts and keeps the integration
  surface small. Long-lived branches accumulate drift and produce painful
  merges.
- Feature flags allow incomplete work to be merged to main without affecting
  the running system. This is critical for a single-operator project — the
  operator should not be blocked on a feature branch while an urgent fix is
  needed on main.
- Conventional commits produce a machine-readable changelog and make it easy
  to answer "what changed in this release?".
- Squash merge keeps the main branch history linear and clean. Each merged PR
  is one commit with a descriptive message.
- GitFlow rejected: excessive branching ceremony for a single-operator
  project. The develop branch is a long-lived branch by another name.
- Merge commits (no squash) rejected: creates a non-linear history where
  individual WIP commits clutter the main branch log.
- No feature flags rejected: forces the operator to either keep features on
  long-lived branches or delay merging until the feature is 100% complete.
  Both are worse than feature flags.

## Consequences

- Positive: minimal merge conflicts; small integration surface.
- Positive: incomplete work can be merged to main safely behind flags.
- Positive: machine-readable changelog from conventional commits.
- Negative: feature flags require disciplined cleanup (mitigated: flag
  removal is a checklist item before sprint completion).
- Reversibility: workflow is policy, not architecture; adjustable anytime.

## Cross-references

- Related ADRs: ADR-0065, ADR-0047
- Implements principle(s): #4, #7
- Affects phases: 14, 15
- Source document: `../14-implementation/decisions.md` (D14-7)
