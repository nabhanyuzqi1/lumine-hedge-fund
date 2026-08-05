# Lineage Enforcement Contract (F16)

- **Status:** active
- **Owner:** data-engineers / architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

`lineage-schema.md` defines the table and the blocking ACID gate. This
spec defines the **enforcement**: how the system guarantees every
state transition on the critical path writes a lineage row, and how
replay/audit verify coverage.

## The blocking gate (restated, ADR-0014)
```
1. trade-core computes proposal
2. RiskValidator verdict
3. PortfolioSizer sizes
4. ExecutionRouter:
   a. BEGIN TX
   b. INSERT INTO lineage_records   ← blocking, ACID
   c. COMMIT                        ← must succeed
   d. on commit failure → safe state, NO dispatch
   e. on commit success → publish mt5.commands
```
No batching. One write per decision. A decision that cannot record itself
cannot dispatch (principle #10).

## Enforcement points
| Transition | Lineage write | Enforcement |
|------------|---------------|-------------|
| Proposal → APPROVE/REJECT | `lineage_records` row with `verdict` | blocking gate (above) |
| APPROVE → dispatch | gate already passed; `mt5.commands` published | idempotency via `processed_commands` (lineage_id PK) |
| Fill received | `fills` row with `lineage_id` FK | listener matches by lineage_id; unmatched fill = P0 alert |
| Position open/close | `positions.opened_lineage` FK | position without lineage = P0 alert |
| Reconciliation | break tied to lineage_id | unmatched broker fill with no lineage = P0 (reconciliation-break.md) |

## Coverage contract tests
- `tests/contract/test_lineage_coverage.py`: for every critical-path
  scenario, assert a lineage row exists with all 7 pins
  (`model_version_id`, `prompt_version_id`, `policy_version_id`,
  `strategy_version_id`, `feature_version_id` [ADR-0020],
  `regime_version_id` [ADR-0034], `calendar_version_id` [ADR-0037]).
- An unmatched fill or orphan position in tests = failure.

## Replay integrity (ADR-0007, ADR-0017)
- Replay never mutates a historical lineage row.
- Comparative re-execution writes a NEW lineage row (new
  `lineage_id`, `workflow_run_id`) tagged as a comparison artifact — never
  overwrites the original.
- The hash chain (ADR-0017) detects any post-hoc mutation attempt.

## Unmatched-fill alert
A fill arriving with no matching `lineage_id` is a P0: it means an order
was dispatched without recording lineage, or an external trade occurred.
Halt dispatch; investigate per `reconciliation-break.md`.

## Phase boundary
Fixes the enforcement contract. Physical schema is Phase 5; the gate code
is Phase 14; coverage tests are Phase 13.
