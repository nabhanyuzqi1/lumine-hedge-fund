# ADR-0064 — TypeScript standards: biome + TypeScript strict + vitest

- **Status:** Accepted
- **Phase:** 14-implementation
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

The TypeScript/React frontend needs linting, formatting, type checking, and
testing tooling. Separate eslint + prettier tools double configuration and
plugin compatibility surface. Default exports break IDE auto-import and make
refactoring fragile. Jest is slower than Vite-native alternatives in a Vite
project.

## Decision

`biome` for linting and formatting (replacing eslint + prettier). TypeScript
`strict: true`. `vitest` + React Testing Library for component and hook
tests. Named exports only. Functional components only.

## Rationale

- `biome` is a single Rust binary replacing eslint + prettier, with faster
  execution and zero-config defaults that match community standards.
- TypeScript strict mode catches `null`/`undefined` errors, missing
  properties, and implicit `any` at compile time.
- `vitest` is Vite-native, shares the same transform pipeline, and runs tests
  orders of magnitude faster than Jest in a Vite project.
- Named exports only: default exports break IDE auto-import, make refactoring
  harder, and create inconsistent import names.
- Functional components + hooks: no class components, no legacy patterns.
  Consistent with React's modern direction.
- eslint + prettier rejected: two separate tools, slower, more configuration,
  plugin compatibility issues.
- Jest rejected: slower in Vite projects, requires separate configuration,
  doesn't share the transform pipeline.
- Default exports rejected: break tree-shaking analysis, make refactoring
  fragile, create inconsistent import naming.

## Consequences

- Positive: single-tool linting/formatting with fast CI.
- Positive: strict type checking and Vite-native test runner.
- Positive: named exports improve IDE experience and refactor safety.
- Negative: biome has a smaller plugin ecosystem than eslint (mitigated:
  zero-config defaults cover V1 needs).
- Reversibility: swap biome or vitest by updating configuration; the
  standards are the contract, not the specific tool.

## Cross-references

- Related ADRs: ADR-0061, ADR-0062, ADR-0063
- Implements principle(s): #6
- Affects phases: 14, 10
- Source document: `../14-implementation/decisions.md` (D14-4)
