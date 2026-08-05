# Agent Registry Specification (F22, S10)

- **Status:** active
- **Owner:** architects / ai-engineers
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

CLAUDE.md requires each agent define Purpose, Responsibilities, Inputs,
Outputs, KPIs, Prompt Philosophy, Memory Requirements, Failure Modes.
`03-agents-and-contracts/registry-schema.md` defines the registry table.
This spec defines the **typed agent definition** in code and its binding to
failure modes and runbooks (ADR-0033).

## AgentSpec (typed dataclass)

```python
@dataclass(frozen=True)
class AgentSpec:
    agent_id: str                  # "cio_proposer", "risk_officer", ...
    role: str                      # human-readable
    purpose: str
    responsibilities: tuple[str, ...]
    inputs: tuple[str, ...]        # variable names consumed
    outputs: tuple[str, ...]       # variable names produced
    kpis: tuple[str, ...]
    prompt_sub_role: str           # FK to prompt_versions.sub_role
    default_tier: Tier             # cost-efficient | context-rich | strongest
    escalation_target: Tier | None
    memory_tier: MemoryTier        # working | episodic (V1); semantic/procedural deferred
    failure_modes: tuple[FailureModeBinding, ...]
    autonomy_limits: tuple[str, ...]   # references agent-autonomy-limits.md
```

## FailureModeBinding (ADR-0033)

```python
@dataclass(frozen=True)
class FailureModeBinding:
    failure_code: FailureCode      # from recovery-and-termination.md taxonomy
    expected_cause: str
    runbook_ref: str               # docs/90-.../94-runbooks/<file>.md
    severity: Severity             # P0 | P1 | P2 | P3
    auto_recovery_allowed: bool
```

## Registry contract
- `backend/src/lumine/autogen_pipeline/agents/registry.py` is the single
  source of truth at runtime.
- `backend/src/lumine/autogen_pipeline/agents/specs/{agent}.py` holds one
  `AgentSpec` per agent.
- At startup, the registry loads all specs, validates each against the
  Phase 3 `registry-schema.md` (prompt_sub_role exists, tiers are valid,
  failure_modes cover the relevant taxonomy codes), and refuses to start
  if any spec is incomplete.

## Failure-mode coverage (CI-enforced)
- Every agent has ≥1 `FailureModeBinding` per relevant taxonomy code.
- The agent-failure-matrix (`docs/90-.../94-runbooks/agent-failure-matrix.md`)
  is a **generated artifact** from the registry, not hand-maintained.
- CI check: registry → matrix generation → diff against committed matrix.
  Drift = failure.

## Agents (per CLAUDE.md hierarchy)
| agent_id | prompt_sub_role | default_tier |
|----------|-----------------|--------------|
| `ceo` | (none — human authority) | n/a |
| `cio` | `cio_proposer` | context-rich |
| `ic_forum` | `ic_forum` | context-rich |
| `technical_analyst` | `technical_analyst` | cost-efficient |
| `macro_analyst` | `macro_analyst` | cost-efficient |
| `news_analyst` | `news_analyst` | cost-efficient |
| `smc_analyst` | `smc_analyst` | cost-efficient |
| `risk_officer` | `risk_officer` | context-rich |
| `portfolio_manager` | (deterministic, no prompt) | n/a |
| `execution_controller` | (deterministic, no prompt) | n/a |

`portfolio_manager` and `execution_controller` are deterministic (no LLM
prompt) but still have an `AgentSpec` for inputs/outputs/failure-modes.

## Phase boundary
This fixes the agent definition contract. Physical storage is Phase 3/5;
runtime instantiation is Phase 7; failure-mode runbooks are the
`90-governance-and-operations` tier.
