# Sprint 3 — Decision Engine: Plan & Evidence

**Status:** Plan drafted — pending approval gate before implementation
**Date:** 2026-08-03
**Sprint:** 3 (Decision Engine) of Phase 15 — Implementation
**Owner:** Chief AI Architect
**Prior sprint:** Sprint 2 (Data Pipeline) — Approved 2026-08-03

---

## 1. Sprint Goal

The core sprint. An end-to-end decision cycle runs: feature trigger → 4
analyst agents → optional debate → IC Forum → CIO Proposer → risk
validation → lineage write → execution dispatch → reconciliation.
Paper trading begins in staging on day 13.

**Exit criteria (from `docs/14-implementation/sprint-plan.md`):**
- Full decision cycle runs end-to-end (trigger → fill → reconciliation)
- All 4 analyst agents produce schema-valid JSON
- IC Forum handles consensus, split, and no-consensus scenarios
- CIO Proposer can override IC with documented reason
- Risk validator rejects over-exposure, oversized, and kill-switched proposals
- Lineage records written before execution dispatch (write-before-dispatch)
- All Level 4 system tests pass
- Paper trading running continuously in staging with zero order errors

**Additional gates (per CLAUDE.md mandatory rules):**
- `make lint-backend`, `make typecheck-backend` pass with zero errors
- `make test` passes (unit + integration + Level 4 system)
- bandit + pip-audit clean
- Independent verification agent returns PASS

---

## 2. Scope

### 2.1 In scope

| Component | Files | Description |
|-----------|-------|-------------|
| 9router HTTP client | `llm_gateway/client.py`, `llm_gateway/types.py` | Async HTTP client to 9router; OpenAI-compatible `/v1/chat/completions` wire contract (D6-2); resolves `model_version_id` → provider+model; returns actual model + token counts + cost |
| Model registry lookup | `llm_gateway/registry.py` | `resolve_model(model_version_id) -> ModelRoute`; reads `model_versions` (production rows only); retired → fail fast (`ModelUnavailableError`) |
| Static tier routing | `llm_gateway/router.py` | D6-1 tier enum (`cost-efficient`, `context-rich`, `strongest`); per-role tier map (analysts=cost-efficient, IC/CIO=context-rich); escalation trigger deterministic (model-routing.md) |
| Cost control + circuit breaker | `llm_gateway/budget.py` | D6-4 pre-call budget check (code, not LLM); reads `llm_usage` running sum per tier; degrade policy ordered (journal→research→re-runs→debate); protected = primary pass default tier; reset UTC midnight |
| `llm_usage` writer | `llm_gateway/usage.py` | D6-7 append-only writer; 11-column schema; write after each call (post-fallback model, tokens, cost); budget counters derive from this table |
| Per-tier fallback chain | `llm_gateway/fallback.py` | D6-6: try primary → same-tier alternates → degrade tier down (never up); log each hop with reason; cost-efficient exhausted → stage failure (Phase 7 recovery) |
| Prompt registry + loader | `prompts/registry.py`, `prompts/templates/` | D4-1: prompt files in `docs/prompts/`; `registry.yaml` source → `prompt_versions` DB; SHA-256 hash verify at startup (mismatch = fatal); `get_prompt(sub_role, version)` |
| 4 analyst agents | `autogen_pipeline/agents/{technical,macro,news,smc}_analyst.py` | D4-2/D4-3: single-turn AutoGen agents, parallel, isolated conversations; load prompt → call LLM via gateway → validate JSON against `analyst_output` schema |
| IC Forum | `autogen_pipeline/ic_forum.py` | D4-4: single-turn, receives 4 analyst outputs as static context; returns `ic_output` (recommendation, confidence, summary, weights, dissent) |
| Debate | `autogen_pipeline/debate.py` | D4-5: deterministic trigger (code checks IC confidence + disagreement vs `policy_versions` thresholds); 1 bounded round, moderator terminates, recursion forbidden |
| CIO Proposer | `autogen_pipeline/cio_proposer.py` | D4-6/D4-7: single-turn, receives IC + all 4 raw analyst outputs; produces full proposal JSON (`version: "v1"`); override flag + reason |
| Risk validator (deterministic) | `risk/validator.py` | Exposure (max 2%/trade, 5% total, 3% correlated, 3% daily-loss halt), position limit, kill-switch, strategy book limit |
| Sizing calculator | `risk/sizing.py` | ATR-based stop (`atr_14 * 2`), 1% risk per trade, `base_volume = (equity*risk)/(stop*pip_value)`, clamp to broker max |
| Risk assessor (LLM-assisted) | `risk/assessor.py` | D8-8/D8-7: LLM outputs `{veto, regime_bucket, risk_notes}` — advisory only; `final_volume = base_volume * multiplier` from `policy_versions.risk_adjustments` lookup by `(regime_bucket, volatility_band)`; LLM never produces float reaching `final_volume` |
| Lineage writer | `data/lineage.py` | D3-7 + `lineage-schema.md`: append-only `lineage_records`; write-before-dispatch (BEGIN→INSERT→COMMIT, commit failure → safe state, NO dispatch); contains proposal + risk verdict + 4 version pins + risk_context |
| Execution router | `execution/router.py` | D8-9 (`order_id:attempt_N`, Redis `SET NX EX 3600`) + D3-7 (`processed_commands` `INSERT ON CONFLICT DO UPDATE`, lineage-level dedup); `LPUSH mt5:commands`, wait `mt5:results` 30s; no auto-retry, FAILED stays FAILED |
| Reconciliation | `execution/reconciliation.py` | D8-8 (reconciliation, not risk assessor): fill vs expected comparison; daily broker reconciliation gate for CLOSED→SETTLED; mismatch arms kill switch |
| Reasoning trace storage | `autogen_pipeline/traces.py` | D7-11: `reasoning_traces` table; one row per LLM call (prompt_sent, response_raw, parsed_output, hashes); synchronous write before stage advances; `lineage_records.proposal.reasoning_trace_ids` array |
| Orchestration entrypoint | `autogen_pipeline/orchestrator.py` | Full cycle wiring; checkpoints (ANALYSTS_VALIDATED, DEBATE_VALIDATED, IC_VALIDATED, PROPOSAL_VALIDATED); deadline propagation (D7-4 reserves: analysts 500ms, ic 800ms, cio 1000ms, risk 500ms); safe-state on failure |
| Level 4 system tests | `tests/system/test_decision_cycle.py` | Full cycle with mock LLM (fixture files) + mock MT5 (simulated fills); scenarios: strong buy/sell, neutral, split committee, CIO override, debate triggered, lineage write failure → halt, safe-state on component failure |

### 2.2 Out of scope (deferred)

- **Real 9router deployment** — Phase 11 infra concern. Sprint 3 builds the client against the OpenAI-compatible wire contract; staging uses a local/mock gateway for paper trading.
- **Live broker reconciliation job scheduling** — Sprint 3 implements the reconciliation *logic* + kill-switch arming; the daily scheduled job wiring is Phase 11.
- **Frontend cost dashboard / reasoning trace viewer** — Phase 10 concern. Sprint 3 writes the data; UI consumes later.
- **Context builder selection logic refinement** — D6-6 budget table + truncation layers are implemented, but tokenizer-per-model matching and prompt-size tuning are Phase 14.
- **Memory architecture beyond stateless V1** — `memory-policy.md` fixes stateless V1 (context assembled from DB + registry per cycle). Long-term memory is post-V1.

---

## 3. Architectural Decisions

Resolving ambiguities identified during contract research (A1-A6 from Phase 4, B1-B8 from Phase 6, C1-C7 from Phase 7/8).

### D3-1: Prompt file location — `docs/prompts/` (resolves A1)

**Decision:** Prompt files live in `docs/prompts/` (D4-1 authoritative). `prompt_ref` stores the relative path. The loader in `prompts/registry.py` reads from there. `backend/src/lumine/prompts/templates/` is NOT used.

**Why:** `prompt-versioning.md` line 19 references `templates/` but D4-1 in `decisions.md` explicitly says `docs/prompts/`. The decisions log is the locked authority; the sub-doc has a stale path. Git-native provenance (PR review, diff history) is the rationale.

**How to apply:** `prompts/registry.py` resolves `prompt_dir` via `Settings.prompt_dir` (already exists, returns `src/lumine/prompts`) — **fix**: override to point at `docs/prompts/` at the repo root. Add a `PROMPT_DIR` env override for test isolation.

### D3-2: 9router wire contract — OpenAI-compatible (resolves B: no wire-level contract)

**Decision:** 9router client speaks the OpenAI Chat Completions wire format: `POST {gateway_url}/v1/chat/completions`, `Authorization: Bearer {api_key}`, JSON body `{model, messages, ...}`, response `{choices[].message, usage{prompt_tokens,completion_tokens}}`. Non-streaming (D6-2: no streaming in V1).

**Why:** `llm-gateway.md` defines the *logical* request contract (model_version_id, prompt_ref, lineage_id, role, tier, idempotency_key) but no HTTP wire spec. 9router is OpenAI-compatible by design (multi-provider routing). Using the de-facto standard means no custom protocol and real providers work unchanged.

**How to apply:** `llm_gateway/client.py` — `RouterClient.complete(model_version_id, messages, *, lineage_id, role, tier, idempotency_key)`. The client maps `model_version_id` → provider model string via `registry.resolve_model()`, sends the OpenAI-shaped request, and writes the `llm_usage` row from the response `usage` block. Logical fields (lineage_id, role, tier) ride as extra JSON fields or headers — 9router ignores unknown fields per OpenAI spec.

### D3-3: `llm_usage.lane` column — add via migration (resolves B: missing column)

**Decision:** Migration 0004 adds `lane TEXT NULL` to `llm_usage` (admission control references it; `cost-control.md` schema omits it). Nullable so existing rows aren't affected.

**Why:** `gateway-admission-control.md` reads `llm_usage.lane` for admission decisions but `cost-control.md`'s D6-7 schema doesn't define it. The admission-control doc is the consumer; the column must exist. Nullable because not every call has a lane (e.g., journal jobs).

**How to apply:** `alembic/versions/0004_add_llm_usage_lane.py` — `ALTER TABLE llm_usage ADD COLUMN lane TEXT NULL`. Index `(lane, ts)` for admission queries.

### D3-4: `model_versions.config` field name — use `params` (resolves B: config vs params mismatch)

**Decision:** Use `model_versions.params` (JSONB) as the canonical column name. If migration 0001 used `config`, migration 0005 renames it to `params`.

**Why:** `model-registry.md` references `params`; physical ERD / migration may have used `config`. Need to verify against `0001_initial_schema.py` and reconcile to one name. `params` matches the registry doc (the authority for model versioning).

**How to apply:** Read `0001_initial_schema.py` `ModelVersion` — if column is `config`, migration 0005 renames to `params` + updates ORM. If already `params`, no migration needed. Decide after audit (Task: audit model_versions schema).

### D3-5: Message schema version envelope — pin at top level only (resolves A2, A6)

**Decision:** `message_schema_version` + `message_schema_name` are pinned at the **top-level proposal** only (backed by registry row `proposal@1.0.0`). Embedded `analyst_output` and `ic_output` objects do NOT carry envelope fields — their schema version is implied by the parent proposal version and pinned via `prompt_version_ids` per sub_role.

**Why:** `inter-agent-message-versioning.md` says every message carries envelope fields, but `proposal-schema.md`'s embedded objects don't include them, and no per-stage sub-documents exist (A2). Adding envelope fields to every embedded object bloats the proposal and duplicates info already in the top-level pins (A6). The top-level proposal is the lineage-pinned artifact; embedded objects are consumed in-process and validated against the schema referenced by the prompt version.

**How to apply:** `proposal-v1.json` schema stays as-is (no envelope fields on embedded objects). The CIO proposal's `version: "v1"` is the `message_schema_version` equivalent, pinned in `lineage_records`.

### D3-6: Weights epsilon — 0.001 (resolves A3)

**Decision:** IC weights must sum to 1.0 ± 0.001. Outside that range → schema validation warning (not failure), flagged in lineage for review.

**Why:** `proposal-schema.md` says "within a small epsilon" but doesn't define it. 0.001 (0.1%) is tight enough to catch real errors but tolerates floating-point representation noise across 4 weights.

**How to apply:** `schemas/proposal-v1.json` — add a custom validation note; `ic_forum.py` asserts `abs(sum(weights) - 1.0) <= 0.001` and logs a warning if breached but doesn't reject (IC output is still usable; the flag is for audit).

### D3-7: Debate round message schema — minimal internal type (resolves A4)

**Decision:** Debate messages use a minimal internal Pydantic type `DebateMessage` (not a versioned registry schema). `analyst_inputs` in the final proposal always stores the **original** (pre-debate) analyst outputs; a `debate_held: bool` flag + the debate summary in `ic_output.summary` is the only debate evidence in lineage.

**Why:** No schema exists for debate messages (A4). Debate is an internal orchestration stage, not a lineage-pinned artifact — its purpose is to refine IC's input, and the IC output is what gets pinned. Storing original analyst outputs (not post-debate) keeps the lineage reproducible: replaying reproduces the same IC input regardless of debate. `proposal-schema.md` line 123 says analyst_inputs is "original or post-debate" — we pick **original** for reproducibility (principle #6).

**How to apply:** `autogen_pipeline/debate.py` defines `DebateMessage` locally; `analyst_inputs` in the CIO proposal = original analyst outputs; `debate_held` reflects whether debate ran.

### D3-8: `registry.yaml` format — manifest of prompt versions (resolves A5)

**Decision:** `docs/prompts/registry.yaml` is a manifest listing each prompt version: `sub_role`, `version`, `prompt_ref` (relative path), `expected_hash` (SHA-256), `model_tier_hint`, `output_schema_ref`. The loader reads it at startup, verifies each file's actual hash matches `expected_hash` (mismatch = fatal), and seeds/updates `prompt_versions` DB rows.

**Why:** `prompt-versioning.md` references `registry.yaml` but defines no structure (A5). The manifest is the source of truth for what prompt versions exist and their hashes; the DB table is the queryable mirror. Hash verification at startup enforces immutability (principle #6).

**How to apply:** `prompts/registry.py` — `load_registry()` parses YAML, verifies hashes, upserts `prompt_versions` rows (idempotent), exposes `get_prompt(sub_role, version) -> PromptBundle(text, variables, output_schema, pins)`.

### D3-9: Risk assessor determinism — D8-7 governs (resolves C1, C2, C6)

**Decision:** `risk_assessor.py` follows D8-7 (determinism contract) as the authoritative rule. The `risk-engine.md` body's deprecated `risk_adjustment` float formula is IGNORED. D8-8 in `decisions.md` (Phase 8) = "risk engine LLM-assisted reasoning" (the approach); D8-8 in `reconciliation.md` = "broker reconciliation" — the latter is a numbering collision, tracked as a doc bug, not a code concern.

**Why:** `risk-engine-determinism.md` explicitly supersedes the deprecated float formula (C2). The LLM risk assessor outputs `{veto, regime_bucket, risk_notes}` — `veto` is a hard boolean (REJECT if true), `regime_bucket` + computed `volatility_band` select a multiplier from `policy_versions.risk_adjustments`, `final_volume = base_volume * multiplier`. The LLM never produces a float reaching `final_volume` (C6: D8-8=approach, D8-7=constraint, both apply).

**How to apply:** `risk/assessor.py` — call LLM, parse `{veto, regime_bucket, risk_notes}`, look up multiplier deterministically, compute `final_volume`. Pin `risk_adjustment_multiplier`, `regime_bucket`, `veto` in `lineage_records.risk_context`.

### D3-10: Lineage-level vs order-level dedup ordering (resolves C4)

**Decision:** Lineage-level dedup (D3-7, `processed_commands` `ON CONFLICT(lineage_id)`) runs **first** at dispatch entry. If the lineage_id is already processed, return the existing result, skip everything (no Redis publish, no order). Only if lineage-level passes does order-level dedup (D8-9, `order_id:attempt_N` `SET NX EX 3600`) run, guarding against duplicate dispatches of the same order within the retry window.

**Why:** C4 flags the interaction as under-traced. Lineage-level dedup is coarser (whole decision) and cheaper (DB conflict); order-level is finer (single order attempt) and time-boxed (Redis TTL). Running lineage first avoids redundant Redis writes for fully-processed decisions; order-level then protects against retry storms within the TTL window.

**How to apply:** `execution/router.py` — `dispatch(lineage_id, order)` → check `processed_commands` (D3-7) → if new, `SET NX` order idempotency key (D8-9) → `LPUSH mt5:commands` → await result → `processed_commands` insert.

### D3-11: Reasoning trace transaction scope — separate tx per stage (resolves C5)

**Decision:** Each `reasoning_traces` row is written in its own transaction, synchronously, immediately after the LLM call returns and output is validated. The lineage ACID gate (write-before-dispatch at `PROPOSAL_VALIDATED`) is a separate, later transaction. Trace write failure blocks stage advance (per D7-11).

**Why:** C5 flags that bundling vs separating is unspecified. Separate-per-stage is simpler (no long-lived transaction across LLM calls), matches the "synchronous before stage advances" rule, and keeps the lineage transaction focused on the proposal+verdict+pins. If the lineage transaction fails, the traces remain (auditable evidence of what was attempted) — which is desirable for debugging safe-state failures.

**How to apply:** `autogen_pipeline/traces.py` — `write_trace(...)` opens its own session+transaction, inserts, commits. Called by each agent stage after validation. `lineage_records.proposal.reasoning_trace_ids` collects the trace UUIDs.

### D3-12: Deadline numeric values — Phase 14 reserves (resolves C3)

**Decision:** Use the reserve table from `deadline-propagation.md` (analysts 500ms, ic_forum 800ms, cio_proposer 1000ms, risk_validator 500ms) as concrete V1 values. Total cycle soft deadline = 60s (configurable via `Settings.decision_cycle_timeout_s`). `call_timeout = remaining_budget - reserve`.

**Why:** C3 flags deadline numbers as deferred to Phase 14. The reserve table IS in the spec (just not the total budget). 60s is a reasonable V1 cycle budget for a tick-triggered decision; tunable later. Picking concrete numbers now lets Sprint 3 implement the propagation logic.

**How to apply:** `autogen_pipeline/orchestrator.py` — track `remaining_budget`, compute per-stage `call_timeout`, fail fast on zero-remaining → `DEADLINE_EXCEEDED` with `exhausted_by`. Add `decision_cycle_timeout_s: int = 60` to `Settings`.

### D3-13: D8-8 doc collision — tracked, not code-blocking (resolves C1)

**Decision:** The D8-8 numbering collision (risk assessor vs reconciliation) is a documentation bug. Sprint 3 proceeds using D8-7 (determinism) for the risk assessor and the reconciliation.md content for reconciliation logic. A doc TODO is filed to renumber.

**Why:** Both uses are clear from context; the collision doesn't affect code. Renumbering docs is a Phase 8 doc fix, not a Sprint 3 code concern.

**How to apply:** No code change. Add `# TODO(doc): D8-8 numbering collision between risk-assessor and reconciliation` in `risk/assessor.py`.

---

## 4. Deliverables

| # | Deliverable | Files | Tests |
|---|-------------|-------|-------|
| 1 | 9router client + types | `llm_gateway/client.py`, `llm_gateway/types.py` | `tests/unit/test_llm_client.py` (mock httpx) |
| 2 | Model registry + tier routing + fallback | `llm_gateway/registry.py`, `router.py`, `fallback.py` | `tests/unit/test_llm_routing.py` |
| 3 | Cost control + circuit breaker + usage writer | `llm_gateway/budget.py`, `usage.py` | `tests/unit/test_budget.py`, `test_llm_usage.py` |
| 4 | Prompt registry + loader | `prompts/registry.py`, `docs/prompts/registry.yaml`, 6 prompt files | `tests/unit/test_prompt_registry.py` |
| 5 | Migration 0004 (llm_usage.lane) + 0005 (model_versions.params rename, if needed) | `alembic/versions/0004_*`, `0005_*` | `tests/integration/test_migrations.py` |
| 6 | 4 analyst agents | `autogen_pipeline/agents/*.py` | `tests/unit/test_analysts.py` (mock LLM fixtures) |
| 7 | IC Forum + debate + CIO | `autogen_pipeline/ic_forum.py`, `debate.py`, `cio_proposer.py` | `tests/unit/test_ic_forum.py`, `test_debate.py`, `test_cio.py` |
| 8 | Risk validator + sizing + assessor | `risk/validator.py`, `sizing.py`, `assessor.py` | `tests/unit/test_risk_validator.py`, `test_sizing.py`, `test_risk_assessor.py` |
| 9 | Lineage writer | `data/lineage.py` | `tests/integration/test_lineage.py` (testcontainers PG) |
| 10 | Execution router + reconciliation | `execution/router.py`, `reconciliation.py` | `tests/integration/test_execution_router.py` (testcontainers Redis) |
| 11 | Reasoning trace storage | `autogen_pipeline/traces.py` | `tests/integration/test_reasoning_traces.py` |
| 12 | Orchestrator | `autogen_pipeline/orchestrator.py` | `tests/unit/test_orchestrator.py` |
| 13 | Level 4 system tests | `tests/system/test_decision_cycle.py` | 8 scenarios (mock LLM + mock MT5) |

---

## 5. Quality Gates

| Gate | Tool | Command | Target |
|------|------|---------|--------|
| Lint | ruff | `make lint-backend` | 0 errors |
| Types | mypy | `make typecheck-backend` | 0 errors |
| Unit tests | pytest | `make test-unit` | all pass |
| Integration tests | pytest + testcontainers | `make test-integration` | all pass, < 3 min |
| System tests (Level 4) | pytest | `make test-system` | 8/8 scenarios pass |
| SAST | bandit | `uv run bandit -r src/` | 0 High; Medium only if accepted |
| Deps | pip-audit | `uv run pip-audit` | No known vulns |
| Coverage | pytest-cov | `--cov=src/lumine` | ≥ 85% overall (new modules ≥ 95%) |

---

## 6. Dependencies

- **Phase 4:** `proposal-schema.md`, `prompt-storage.md`, `prompt-versioning.md`, `inter-agent-message-versioning.md`, `decisions.md` (D4-1 through D4-7)
- **Phase 6:** `llm-gateway.md` (D6-2), `model-routing.md` (D6-1), `cost-control.md` (D6-4, D6-7), `model-registry.md`, `gateway-admission-control.md`, `confidence-calibration.md`, `context-budget-policy.md` (D6-6), `memory-policy.md`
- **Phase 7:** `orchestration.md`, `workflow-lifecycle.md`, `recovery-and-termination.md` (D7-7), `checkpoint-and-replay.md`, `concurrency-budget.md`, `deadline-propagation.md` (D7-4), `reasoning-trace-storage.md` (D7-11)
- **Phase 8:** `risk-engine.md`, `risk-engine-determinism.md` (D8-7), `execution-engine.md` (D8-9), `order-lifecycle.md`, `reconciliation.md`, `decisions.md` (D8-8)
- **Phase 3:** `lineage-schema.md` (D3-7), `registry-schema.md`
- **Sprint 1:** `shared/config.py`, `shared/errors.py`, `data/models.py`, `data/session.py`
- **Sprint 2:** `features/provider.py` (FeatureSnapshot), `bridge/client.py` (MT5BridgeClient), `data/redis_client.py`

New runtime dependencies:
- `autogen-agentchat`, `autogen-core` (Microsoft AutoGen)
- `httpx` (async HTTP for 9router — likely already present)
- `tiktoken` or `transformers` tokenizer (token counting for context budget)

---

## 7. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| AutoGen API churn (v0.4+ async API) | Medium | High | Pin autogen version; wrap in thin adapter so AutoGen upgrades don't touch agent logic |
| 9router not deployed in staging | High | Medium | Build client against OpenAI-compatible spec; mock gateway for paper trading until Phase 11 deploys 9router |
| LLM JSON output validation flakiness | High | High | Strict schema validation + retry-once with "fix your JSON" prompt (Phase 7 allows retry, not relaxed parse); fixture-based mock LLM for deterministic tests |
| Deadline propagation too tight (60s) | Medium | Medium | Make configurable; log `DEADLINE_EXCEEDED` with `exhausted_by` for tuning |
| Risk assessor LLM veto instability | Medium | High | `veto=true` is conservative (REJECT); deterministic multiplier lookup is the real sizing authority; veto only blocks, never sizes |
| Migration 0004/0005 on existing staging DB | Low | High | Test on clean testcontainer first; `ADD COLUMN ... NULL` is non-breaking; rename (0005) only if audit confirms mismatch |
| Reasoning trace storage volume | Medium | Low | Append-only, no partitioning in V1 (per cost-control.md); monitor growth |
| Context budget tokenizer mismatch with gateway | Medium | Medium | Use gateway's `usage.prompt_tokens` as authoritative; local tokenizer is pre-flight estimate only |

---

## 8. Acceptance Criteria Check

| Exit criterion | Status | Evidence |
|----------------|--------|----------|
| Full decision cycle runs end-to-end | ⏳ | Pending implementation |
| 4 analyst agents produce schema-valid JSON | ⏳ | Pending |
| IC Forum handles consensus/split/no-consensus | ⏳ | Pending |
| CIO Proposer can override IC with reason | ⏳ | Pending |
| Risk validator rejects over-exposure/oversized/kill-switched | ⏳ | Pending |
| Lineage records written before dispatch | ⏳ | Pending |
| All Level 4 system tests pass | ⏳ | Pending |
| Paper trading running in staging | ⏳ | Pending (day 13-15) |
| Lint / type / SAST / deps | ⏳ | Pending |
| Independent verification | ⏳ | Pending (close-out) |

**Status legend:** ⏳ pending → ✅ done → 🚫 blocked

---

## 9. Sign-off

Sprint 3 plan is drafted. Implementation begins after the user
approves the gate. This is the largest sprint (3 weeks, 13 deliverables);
the architectural decisions above resolve all 21 identified ambiguities
(A1-A6, B1-B8, C1-C7) against the locked spec decisions.

---

## 10. Implementation Sequencing (suggested)

Ordered to unblock dependencies earliest:

1. **Migrations 0004/0005** + audit `model_versions` schema — unblocks all DB-backed components
2. **Prompt registry + loader + 6 prompt files** — unblocks analyst agents
3. **9router client + model registry + tier routing + fallback** — unblocks all LLM-calling agents
4. **Cost control + usage writer** — unblocks gateway admission
5. **4 analyst agents** — unblocks IC Forum
6. **IC Forum + debate** — unblocks CIO
7. **CIO Proposer** — unblocks risk + lineage
8. **Risk validator + sizing + assessor** — unblocks lineage
9. **Reasoning trace storage** — parallel with 6-8
10. **Lineage writer** — unblocks execution
11. **Execution router + reconciliation** — unblocks system tests
12. **Orchestrator** — wires 5-11 together
13. **Level 4 system tests** — validates end-to-end
14. **Paper trading prep** (days 13-15) — staging deploy
