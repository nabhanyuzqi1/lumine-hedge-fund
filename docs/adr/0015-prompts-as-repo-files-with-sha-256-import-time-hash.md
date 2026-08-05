# ADR-0015 — Prompts as repo files with SHA-256 import-time hash

- **Status:** Accepted
- **Phase:** 04-communication-and-prompts
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

Prompts must be versioned, auditable, and reproducible. Storing prompt
text as database blobs loses git-native provenance (author, diff, PR
review) and requires a separate deployment pipeline. The `prompt_versions`
registry (Phase 3) needs a `prompt_ref` and `prompt_hash` semantics so
that replay resolves the exact prompt that produced a historical decision.

## Decision

Prompts live as plain text files in the repository under `docs/prompts/`,
one file per sub-role version. When a new prompt version is registered, the
importer reads the file, computes SHA-256 of the exact bytes, and stores
the hex digest in `prompt_hash` (immutable). `prompt_ref` is the relative
path from repo root. If the file on disk is later edited without creating
a new registry row, the hash diverges from pinned hashes, making replay
drift detectable.

## Rationale

- Git-native provenance: every change has author, diff, and PR review.
- Human-readable during development and incident response.
- No separate prompt deployment pipeline; the registry row is just a
  pointer and a hash.
- Old versions stay in the repo forever, satisfying principle #6.
- SHA-256 hash pinning makes replay drift detectable.

## Consequences

- Positive: prompt changes go through standard code review.
- Positive: replay resolves the exact prompt by hash.
- Negative: prompt edits require a new registry row (intentional friction).
- Reversibility: the file layout is stable; the registry contract is
  structural.

## Cross-references

- Related ADRs: ADR-0028, ADR-0038, ADR-0044
- Implements principle(s): #6, #10
- Affects phases: 04, 03
- Source document: `../04-communication-and-prompts/prompt-storage.md`
