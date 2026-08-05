# Quality Gates (Enforcement)

- **Status:** active
- **Owner:** qa / architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

`docs/13-testing/test-levels.md` defines the 7 test levels. This document
defines the **enforcement** — what blocks a merge or a deploy. A strategy
untested is a strategy unshipped.

## CI merge gates (every PR)
| Gate | Tool | Threshold | Blocks merge? |
|------|------|-----------|---------------|
| Lint (backend) | `ruff` | zero errors | yes |
| Lint (frontend) | `eslint` | zero errors | yes |
| Typecheck | `mypy --strict`, `tsc` | zero errors | yes |
| Unit tests | `pytest tests/unit` | 100% pass | yes |
| Coverage — critical path | `pytest --cov` | ≥80% on `trade_core/`, `risk/`, `execution/`, `security/` | yes |
| Coverage — other | `pytest --cov` | ≥60% | warn |
| Contract tests | `pytest tests/contract` | 100% pass | yes |
| Docs lint | `markdownlint`, `lychee`, `adr-index-check` | zero errors | yes |
| Supply chain | `pip-audit`, `osv-scanner`, `gitleaks` | zero high/critical CVEs | yes |

## Deploy gates (promotion to production)
| Gate | Evidence | Blocks deploy? |
|------|----------|----------------|
| All merge gates green | CI status | yes |
| Spec reconciliation | no new `Critical` gaps in `Done` areas | yes |
| Eval gate (prompts/models) | `eval_pass_hash` valid (ADR-0028, ADR-0030) | yes |
| Reconciliation passing | last daily reconciliation pass | yes |
| Chain verification | hash chain verified (ADR-0017) | yes |
| Calibration in band | `calibration_eca` < threshold (ADR-0032) | yes (for model promos) |

## Periodic gates
| Gate | Cadence | Blocks? |
|------|---------|---------|
| Integration tests | nightly | deploy blocked next day if failing |
| Backtest parity | per strategy promotion | promotion blocked |
| Restore drill | monthly | P1 if missed |
| Security scan | daily + on dep change | deploy blocked if high CVE |
| Calibration re-measure | monthly | promotion blocked if drift |

## Test level → artifact mapping
| Level | Lives in | Must have ≥1 real test before area is "Done" |
|-------|----------|-----------------------------------------------|
| Unit | `tests/unit/` | per critical module |
| Integration | `tests/integration/` | per cross-module flow |
| Contract | `tests/contract/` | per API endpoint + SSE event |
| Backtest | `tests/backtest/` | per strategy (parity-gated) |
| System | `tests/system/` | per critical-path scenario |
| Security | `tests/` + `security-testing.md` | per threat |
| AI | `prompts/evals/` | per agent/prompt (eval-gated) |

## Anti-patterns
- "Tests added later" — no. Tests gate the merge.
- Skipping coverage on `trade_core/` — no. Critical path coverage is non-negotiable.
- Promoting without eval — no (ADR-0028).

## Phase boundary
Binds Phase 13 testing to Phase 14 CI and Phase 15 implementation status.
