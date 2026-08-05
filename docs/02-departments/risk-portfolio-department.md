# Risk & Portfolio Department (Deterministic Sub-modules)

## Overview

The Risk, Portfolio, and Execution-router functions are deterministic
sub-modules inside trade-core (Zone 1). They run in-proc, synchronously, on
the critical path. Each sub-module has a stable input/output boundary;
internals may change without breaking neighbors.

This document fixes the sub-module structure, the tiered kill switch, and the
suspension flow. It does not define risk math formulas, policy YAML schemas,
or code — those belong to later phases.

## Sub-module structure

```
trade-core (Zone 1, in-proc sync)
├─ RiskValidator        (sub-module, FINAL VETO)
│     input:  proposal, current exposure, risk policy, kill-switch flag
│     output: APPROVE / REJECT / MODIFY + reason
├─ PortfolioSizer       (sub-module)
│     input:  approved proposal, book limits, capital allocation
│     output: sized order per book + attribution tag
└─ ExecutionRouter      (sub-module)
│     input:  sized order
│     output: dispatch to mt5.commands stream
```

These are logical sub-modules with stable boundaries, not separate processes.
The in-proc sync lane (Phase 1) preserves atomicity and low latency on the
critical path.

## RiskValidator — FINAL VETO

The RiskValidator checks the LLM proposal against:

- Current exposure (from PostgreSQL positions).
- Risk policy / envelope (from registry `policy_versions`).
- Kill-switch flag (synchronous read, tiered: global + book + strategy).
- Strategy book limits.

Output: `APPROVE` / `REJECT` / `MODIFY` + reason.

- **REJECT is absolute.** No component may override a REJECT — not the CIO
  Proposer LLM, not the IC, not any async worker (principle #2).
- **Fail-safe.** On validator error, the default is REJECT (principle #10:
  safe state by default).
- **On critical path.** The validator runs synchronously, ahead of any order
  dispatch.

## PortfolioSizer

The PortfolioSizer runs only on APPROVE.

- Size calculation per book (intraday / swing). Book limits are independent.
- Attribution tag is mandatory on every order (`intraday` / `swing`).
- Risk veto takes precedence — the sizer cannot override a REJECT.
- Sizing parameters live in versioned registry entries (principle #9: no
  hardcoding).

## ExecutionRouter

The ExecutionRouter dispatches the sized order to the `mt5.commands` Redis
stream.

- Does not call the MT5 API directly (Phase 1 invariant: via bridge).
- Lineage write must succeed BEFORE dispatch (Phase 1 lineage rule: sync,
  blocking, ACID). If the lineage write fails, no dispatch (safe state).
- One lineage write per decision, never batched.

## Tiered kill switch

The kill switch is tiered to allow granular isolation without halting the
entire system.

| Level | Scope | Authority | Effect |
|-------|-------|-----------|--------|
| Global | Entire system | CIO (human) | Flatten all, halt new entries |
| Per-book | Intraday / Swing | Risk dept or CIO | Suspend one book, keep the other running |
| Per-strategy | Specific strategy | Risk dept or CIO | Isolate a problem strategy without halting the book |

The kill-switch flag is read synchronously in RiskValidator, on the critical
path, ahead of any order dispatch. No LLM, no async worker, no automated
process may override or delay it (Phase 1 invariant).

## Suspension flow

```
trigger suspend (CIO or Risk dept)
     ↓
set flag (global / book / strategy) in state store
     ↓
RiskValidator reads flag next cycle → REJECT new entries for suspended scope
     ↓
existing positions: managed per policy (flatten / reduce / hold)
     ↓
restart: CIO only (system cannot self-restart)
```

Restart is a human gate. The system may not self-restart from a kill state
(principle #7: self-modification as research, not production authority).

## Separation guarantees

- **Risk veto is absolute.** No LLM or worker may override a REJECT.
- **Sizer cannot override risk.** Sizing happens only after APPROVE.
- **Router cannot bypass lineage.** No lineage, no dispatch.
- **Kill switch is synchronous.** Read on every cycle, ahead of dispatch.
- **Books never blend.** Attribution tags are mandatory; lineage records
  carry the book tag (principle #5).

## Phase boundary

This document fixes the sub-module structure, tiered kill switch, and
suspension flow. It does not define:

- Risk math formulas / envelope calculations (Phase 7 — Risk Policy).
- Policy YAML / JSON schema (Phase 7).
- Exposure computation implementation (Phase 3 / Phase 14+).
- Code (Phase 14+).
