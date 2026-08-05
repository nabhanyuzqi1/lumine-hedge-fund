# Onboarding — New Engineer

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 180

## Day 1
1. Read `README.md`, `ARCHITECTURE.md`, `CLAUDE.md`.
2. Read `docs/00-vision/` (vision, scope, success metrics).
3. Read this folder's `91-glossary.md`.
4. Clone repo; `make install`; `make test` (expect partial — see `docs/15-implementation/spec-reconciliation.md`).
5. Read `docs/90-governance-and-operations/93-standards/coding-standards.md`.

## Week 1
6. Read `docs/01-architecture/` (high-level, data-flow, deployment-topology).
7. Read `docs/14-implementation/repository-structure.md` and `coding-standards.md`.
8. Read `docs/adr/INDEX.md` — skim every Accepted ADR title.
9. Pick a `good-first-issue`-style task; land a PR following `CONTRIBUTING.md`.

## Month 1
10. Deep-read the phase for your area (e.g. `docs/07-autogen/` for runtime).
11. Read the audit contracts (S1–S25) relevant to your area.
12. Shadow an on-call rotation.

## Principles to internalize
- Architecture before code. LLMs only reason. Safe state by default.
- Evidence before capital. Reproducibility before adaptation.
- Every architectural change gets an ADR.

## What NOT to do
- Don't add a feature in `91-anti-scope-register.md` without superseding its ADR.
- Don't mix phases in one PR.
- Don't edit a phase doc without checking `docs/INDEX.md` for cross-phase impact.
- Don't commit scratch state (see `.gitignore`).
