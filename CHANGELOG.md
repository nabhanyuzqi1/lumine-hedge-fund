# Changelog

All notable changes to Lumine are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) for
the platform once it reaches 1.0.

## [Unreleased]

### Added — Architecture audit (Pass 1 + Pass 2)

This entry records the structural rework from the two-pass architecture
audit. Implementation of these contracts is tracked in
`docs/15-implementation/`.

#### Governance & structure

- Global ADR registry (`docs/adr/`) with `INDEX.md` and template; phase
  `decisions.md` files now point to ADRs.
- Governance & operations tier `docs/90-governance-and-operations/`
  (glossary, onboarding, standards, runbooks, FinOps, AI governance,
  change management, FAQ).
- Root governance files: `README.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`,
  `SECURITY.md`, `CODEOWNERS`.
- `docs/INDEX.md` topic × phase knowledge map.
- `docs/15-implementation/` (Phase 15 home: status, spec reconciliation,
  deviation log, sprint evidence).
- Folder renames: `03-data/` → `03-agents-and-contracts/`,
  `04-prompts-autogen/` → `04-communication-and-prompts/`;
  `autogen-orchestration.md` moved to `07-autogen/orchestration.md`.

#### Capital-integrity contracts

- ADR-0016: LLM risk role advisory-only; deterministic sizing lookup.
- ADR-0017: hash-chained, WORM-anchored audit journal.
- ADR-0018: prompt injection defense-in-depth.
- ADR-0019: backtest parity contract.
- ADR-0020: versioned, point-in-time feature store.
- ADR-0021: daily broker reconciliation as SETTLED gate.

#### Scale contracts

- ADR-0022: LLM gateway admission control with priority lanes.
- ADR-0023: lineage partitioning + write-aside safety gate.
- ADR-0024: multi-broker model (schema-ready, V1 one adapter).
- ADR-0025: registry supersession model with graded compatibility.
- ADR-0026: comparative replay resource isolation.

#### Institutional contracts

- ADR-0027: four-tier memory architecture with governed deferral triggers.
- ADR-0028: machine-enforced eval gate on prompt promotion.
- ADR-0029: reasoning traces stored alongside outputs.
- ADR-0030: model risk management (SR 11-7 style).
- ADR-0031: strategy promotion / demotion policy.
- ADR-0032: confidence calibration gate.
- ADR-0033: agent failure-mode matrix.

#### Correctness contracts

- ADR-0034: deterministic regime classifier.
- ADR-0035: clock synchronization contract.
- ADR-0036: context-window budget with deterministic truncation.
- ADR-0037: market calendar / holiday / economic-event contract.
- ADR-0038: inter-agent message schema versioning.
- ADR-0039: deadline propagation.
- ADR-0040: TCA and execution-quality reporting.

#### Process contracts (CLAUDE.md rules → ADRs)

- ADR-0041: inter-engine review preferred for verification.
- ADR-0042: no coding before Phase 14 approval.
- ADR-0043: phased development — no skipping, no mixing.
- ADR-0044: prompts and schemas versioned, hashed, auditable.

#### Phase-decision promotion (Pass 2 follow-up)

- ADR-0045..0050: Phase 11 infrastructure decisions (hosting, container
  topology, secrets, backup-DR, observability, CI/CD gates) promoted from
  `docs/11-infrastructure/decisions.md` into the global registry.
- ADR-0051..0054: Phase 12 security decisions (supply chain, network
  firewall, audit-log immutability, threat-model refresh cadence) promoted
  from `docs/12-security/decisions.md`.
- ADR-0055..0060: Phase 13 testing decisions (7-level test pyramid,
  testcontainers, contract/SSE/system test scope, backtest code-path parity
  via DI, paper-trading gate, security pentest cadence) promoted from
  `docs/13-testing/decisions.md`.
- ADR-0061..0067: Phase 14 implementation decisions (repo layout, package
  selection, coding standards, sprint sequence, trunk-based git, feature
  flags, dependency policy) promoted from `docs/14-implementation/decisions.md`.

### Changed

- `.gitignore`: added `.remember/`, `.openclaude/`, `backend/.data/`.
- `docs/phase-mapping.md`: rewritten as a 1:1 phase→folder table; historical
  narrative moved to ADR context.

### Removed

- Scratch state from repo root (now gitignored).
