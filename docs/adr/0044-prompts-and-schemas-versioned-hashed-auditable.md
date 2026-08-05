# ADR-0044 — Prompts and schemas versioned, hashed, auditable

- **Status:** Accepted
- **Phase:** 14-implementation
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

CLAUDE.md rule 10 states: "All prompts and schemas must be versioned,
hashed, and auditable." Prompts and schemas are the contract between human
intent and model behavior. Without versioning, a prompt change is
invisible. Without hashing, there is no proof that the prompt pinned in
lineage is the prompt that actually ran. Without auditability, there is no
evidence trail for regulatory or internal review. This rule is the
governing principle behind ADR-0015 (prompt storage), ADR-0028 (eval
gate), and ADR-0038 (message schema versioning).

## Decision

All prompts and schemas are versioned, hashed, and auditable. Prompts live
as repo files with SHA-256 import-time hash (ADR-0015). Prompt promotion
requires a machine-enforced eval gate with hash-pinned evidence
(ADR-0028). Inter-agent message schemas carry semver and are pinned in a
registry with `code_hash` (ADR-0038). Every decision's lineage pins the
exact prompt version, schema version, and their hashes, so the full
contract that produced a historical decision is re-addressable forever.

## Rationale

- Versioning makes prompt/schema changes visible and reviewable.
- Hashing proves the pinned artifact is the artifact that ran — no silent
  drift.
- Auditability provides the evidence trail for regulatory review and
  post-incident analysis (principle #4).
- The combination of versioning + hashing + auditability is what makes
  reproducibility (#6) enforceable: replay resolves the exact pinned
  versions and verifies them by hash.

## Consequences

- Positive: every prompt and schema change is visible, reviewed, and
  hash-pinned.
- Positive: replay can verify that the pinned prompt/schema matches the
  recorded hash.
- Negative: prompt/schema edits require a new registry row (intentional
  friction).
- Reversibility: the contract is structural; old versions stay pinned
  forever.

## Cross-references

- Related ADRs: ADR-0015, ADR-0028, ADR-0038
- Implements principle(s): #4, #6
- Affects phases: 04, 03, 13, 14
- Source document: `../../CLAUDE.md` (rule 10)
