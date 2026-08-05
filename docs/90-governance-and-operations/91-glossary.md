# Glossary

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 365

Domain and system terminology. Add terms as they enter common use.

## Trading & markets

| Term | Definition |
|------|------------|
| XAUUSD | Spot gold vs USD. Lumine's first instrument. |
| Pip | Smallest price increment for a symbol. For XAUUSD, typically $0.01. |
| Slippage | `fill_price - benchmark`. Benchmark = arrival mid at `decision_ts`. See `docs/08-trading/tca-and-execution-quality.md`. |
| Spread | `ask - bid` at a point in time. |
| Drawdown | Peak-to-trough decline of equity. Max DD is a strategy promotion gate. |
| Fill | Confirmation that an order (or part) executed. |
| Partial fill | Some volume filled; remainder pending. |
| Position | Net open exposure in a symbol on an account. |
| Book | A trading mandate boundary. Lumine V1: `intraday`, `swing`. Books never blend (principle #5). |
| Regime | Market state (low/high vol × trend/range × crisis). See `docs/03-agents-and-contracts/regime-model.md`. |
| Session | Trading hours window (Asia/London/NY). See `market-calendar-contract.md`. |
| TCA | Transaction Cost Analysis. See `tca-and-execution-quality.md`. |
| Best execution | Regulatory obligation to seek the best execution terms; evidenced by TCA. |
| Reconciliation | Daily comparison of internal positions/fills against broker statements. |

## Agent hierarchy

| Term | Definition |
|------|------------|
| CEO / CIO | Human authority above the system; owns kill switch, promotion, mandate. |
| IC | Investment Committee — 4 analysts + forum that produces a committee view. |
| Analyst (Technical/Macro/News/SMC) | LLM agent producing a domain-specific market read. |
| Risk Officer / RiskValidator | Deterministic final veto on the critical path. No LLM sits above it. |
| Portfolio Manager / PortfolioSizer | Deterministic position sizing. |
| Execution Controller / ExecutionRouter | Dispatches sized orders; owns the blocking ACID lineage gate. |
| Trade Journal | Append-only record of decisions and outcomes. |
| Performance Reviewer | Async evaluation feeding the Research sandbox. |

## Architecture

| Term | Definition |
|------|------------|
| Lineage | The immutable record tying a decision to its pins (model/prompt/policy/strategy/feature/regime/calendar versions). See `lineage-schema.md`. |
| Pins | Version UUIDs frozen at `CONTEXT_PINNED` for a workflow run. |
| Journal | The durable, append-only, hash-chained record of workflow transitions. Source of truth (D7-5). |
| Checkpoint | A validated state from which resume is permitted. |
| Critical path | Scheduler → committee → RiskValidator → Sizer → ExecutionRouter → lineage gate → MT5. No async workers here. |
| Kill switch | CIO-held halt; terminates active runs at the next LLM call boundary; no autonomous restart. |
| Safe state by default | Failures stop the pipeline; a decision that cannot record itself cannot dispatch (principle #10). |

## AI / LLM

| Term | Definition |
|------|------------|
| Tier | Model cost class: `cost-efficient` (1×), `context-rich` (~10×), `strongest` (~30×). |
| Escalation | Deterministic move to a higher tier within a cycle (never de-escalates). |
| Calibration | Mapping raw LLM confidence to calibrated probability; required for escalation (ADR-0032). |
| Working memory | Intra-cycle context (allowed V1). |
| Episodic memory | Past decisions from lineage (allowed V1, DB-backed). |
| Semantic memory | Concept graph / embeddings (deferred; ADR-0027). |
| Procedural memory | Learned policies (deferred; ADR-0027). |

## Operations

| Term | Definition |
|------|------------|
| ADR | Architectural Decision Record. See `docs/adr/INDEX.md`. |
| RFC | Request for Comments — architecture change proposal. See `97-change-management/`. |
| RTO | Recovery Time Objective — max acceptable downtime. |
| RPO | Recovery Point Objective — max acceptable data loss. |
| WORM | Write-Once-Read-Many storage; backs the audit anchor (ADR-0017). |
| SLO | Service Level Objective. |
| SBOM | Software Bill of Materials. |
