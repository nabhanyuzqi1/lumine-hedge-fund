# Lumine — Architecture Overview

This is the one-page canonical entry point. For depth, follow the links.

## What Lumine is

An AI-native hedge fund platform where LLM agents reason about markets and a
deterministic Python layer manages risk, sizing, and execution. LLMs only
reason; deterministic code handles money and safety.

## Agent hierarchy

```text
CEO
  └── CIO
        └── Investment Committee (IC)
              ├── Technical Analyst
              ├── Macro Analyst
              ├── News Analyst
              └── SMC Analyst
        └── Risk Officer
        └── Portfolio Manager
              └── Execution Controller
                    └── Trade Journal
                          └── Performance Reviewer
```

Each agent has a typed spec (purpose, inputs, outputs, KPIs, failure modes).
See `docs/02-departments/` and `docs/90-governance-and-operations/94-runbooks/agent-failure-matrix.md`.

## Critical path (every trade decision)

```text
Scheduler ─► trade-core
  │
  ▼
LLM committee (4 analysts ─► optional debate ─► IC ─► CIO Proposer)   [reasoning]
  │
  ▼
RiskValidator ── FINAL VETO                                            [deterministic]
  │  APPROVE
  ▼
PortfolioSizer                                                         [deterministic]
  │
  ▼
ExecutionRouter
  ├── BEGIN TX
  ├── INSERT lineage_records  ◄── blocking ACID gate (safe state by default)
  ├── COMMIT  ── must succeed before dispatch
  └── publish mt5.commands stream
  │
  ▼
MT5 Bridge ─► fill ─► listener ─► UPDATE positions / INSERT fills
```

No LLM sits above RiskValidator. No async worker sits on the critical path.
The CIO kill switch is read every cycle and sits above the entire path.

## The five invariants

1. **Reproducibility (#6):** every decision pins `model_version_id`,
   `prompt_version_id`, `policy_version_id`, `strategy_version_id`,
   `feature_version_id`, `regime_version_id`, `calendar_version_id`. Replay
   rebuilds identical context. (Non-determinism leaks closed by ADR-0016,
   ADR-0020, ADR-0032, ADR-0036.)
2. **Auditability (#4):** the durable journal is the source of truth;
   telemetry is a projection. The journal is hash-chained and WORM-anchored
   (ADR-0017). Reasoning traces are stored, not just outputs (ADR-0029).
3. **Safe state by default (#10):** failures stop the pipeline. The blocking
   ACID lineage gate means a decision that cannot record itself cannot
   dispatch. Malformed output is rejected, never coerced (ADR-0011).
4. **LLMs only reason:** deterministic code owns sizing, risk limits, and
   execution. The LLM risk role is advisory; the sizing multiplier is a
   registry lookup (ADR-0016).
5. **Evidence before capital:** every trade carries an auditable chain
   from trigger → features → reasoning → proposal → risk verdict →
   fill → reconciliation.

## Architecture layers

1. Data Collection
2. Feature Engineering
3. Market Analysis
4. Investment Committee
5. Risk Committee
6. Execution
7. Monitoring
8. Journal
9. Learning

## Where to read more

- System architecture: `docs/01-architecture/`
- Agent & data contracts: `docs/03-agents-and-contracts/`
- AutoGen runtime: `docs/07-autogen/`
- Trading: `docs/08-trading/`
- API contracts: `docs/09-api/`
- Decisions: `docs/adr/INDEX.md`
- Operations: `docs/90-governance-and-operations/`
