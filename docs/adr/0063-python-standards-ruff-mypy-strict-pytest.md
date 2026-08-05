# ADR-0063 — Python standards: ruff + mypy strict + pytest

- **Status:** Accepted
- **Phase:** 14-implementation
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

The Python backend needs linting, formatting, type checking, and testing
tooling. Multiple separate tools (flake8, isort, black, pyupgrade) multiply
configuration and CI runtime. Type errors should be caught at development
time, not runtime. AutoGen's dynamic agent interfaces do not type-check
cleanly under strict mode. Logging must be structured with trace correlation.

## Decision

`ruff` for linting and formatting (replacing flake8, isort, black,
pyupgrade). `mypy --strict` for all `src/` except the AutoGen pipeline (where
AutoGen's dynamic types make strict mode impractical). `pytest` +
`pytest-cov` for testing with >= 80% line coverage target on deterministic
modules. Google-style docstrings for public API only; internal helpers use
inline comments. `structlog` for structured JSON logging with `trace_id` on
every line. `pydantic-settings` for configuration loading with validation.

## Rationale

- `ruff` is a single Rust binary that replaces 4+ Python tools. It runs
  orders of magnitude faster than the tools it replaces and implements 800+
  rules covering style, bugs, complexity, and security.
- `mypy --strict` catches type errors at development time rather than runtime.
  The AutoGen pipeline exclusion is pragmatic — AutoGen's dynamic agent
  interfaces do not type-check cleanly under strict mode.
- Google-style docstrings for public API only; internal helpers use inline
  comments. Docstrings on every function create noise without benefit — the
  function signature and name should be self-documenting for internal code.
- flake8 + isort + black + pyupgrade rejected: 4x the configuration, 4x the
  CI runtime, 4x the dependency surface.
- `pylint` rejected: slower than ruff, more false positives, more
  configuration overhead.
- Docstrings on all functions rejected: internal helper docstrings rot faster
  than they're updated. Public API docstrings are the contract.

## Consequences

- Positive: single-tool linting/formatting with fast CI.
- Positive: strict type checking catches errors at dev time.
- Negative: AutoGen pipeline is excluded from strict type checking (mitigated:
  pragmatic boundary; rest of codebase is strict).
- Reversibility: swap ruff or mypy by updating configuration; the standards
  are the contract, not the specific tool.

## Cross-references

- Related ADRs: ADR-0061, ADR-0062, ADR-0064
- Implements principle(s): #6
- Affects phases: 14
- Source document: `../14-implementation/decisions.md` (D14-3)
