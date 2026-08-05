# AutoGen Orchestration

## Overview

This document defines how the LLM committee from Phase 2 is expressed in
AutoGen. Phase 2 locked the topology and responsibilities; Phase 4 chooses
the AutoGen pattern that implements it.

## Decision: dynamic rounds

The committee is implemented as a sequence of separate AutoGen conversations,
created and destroyed on demand:

1. **Analyst round** — 4 analysts run in parallel, each in its own
   conversation. They are independent; no agent talks to another analyst.
2. **Debate round (conditional, bounded debate)** — if the deterministic trigger fires, a
   second conversation is created with the 4 analysts plus a moderator role.
   Exactly 1 round, bounded, no recursion.
3. **IC Forum round** — a conversation containing only the IC Forum agent.
   It receives the analyst outputs as static context, not as chat messages.
4. **CIO Proposer round** — a conversation containing only the CIO Proposer
   agent. It receives the IC output and the original raw analyst outputs as
   static context.

This is not a single long `GroupChat` with all participants. Each stage is an
isolated conversation whose membership is chosen to match the stage's
purpose.

## Why dynamic rounds

- Matches the adaptive-parallel topology locked in Phase 2: default path is
  efficient (analysts parallel → IC → CIO); debate is an extra stage only
  when needed.
- Each stage output can be validated independently before the next stage
  starts. Malformed analyst JSON can fail fast instead of polluting the IC
  Forum context.
- Keeps prompts single-purpose: an analyst prompt never has to handle "what
  if someone else disagrees" because the debate round has its own prompt.
- Simpler reproducibility: a saved `lineage_records.proposal` can describe
  which rounds ran and with which inputs.

## Authority boundaries preserved

- Analysts propose only; they do not see each other's outputs in the default
  path.
- IC Forum consolidates only; it cannot command trades.
- CIO Proposer decides the final proposal and may override IC, but its
  output is still data (proposal), not a command.
- RiskValidator downstream retains FINAL VETO (Phase 1 / Phase 8).

## Conversation lifecycle

### Analyst round

```
conversation A1: Technical Analyst + system message
conversation A2: Macro Analyst + system message
conversation A3: News Analyst + system message
conversation A4: SMC Analyst + system message

inputs: features/macro/news context per sub-role
outputs: analyst_json_1 .. analyst_json_4
```

Each analyst conversation is a single-turn call: system prompt + user
context → structured JSON response.

### Deterministic debate trigger

After all 4 analysts return valid JSON, system code (not an LLM) evaluates:

```
trigger_debate = (
    ic_confidence_predicted < policy.ic_confidence_threshold
    or disagreement_score(analyst_json_*) > policy.disagreement_threshold
)
```

The thresholds come from `policy_versions` (Phase 3 registry). The trigger
is deterministic and reproducible for the same inputs.

#### Definition of `ic_confidence_predicted`

```python
def ic_confidence_predicted(analyst_outputs: list[dict]) -> float:
    """Predict IC Forum confidence before the IC Forum runs.

    Computed as the weighted average of the four analyst confidences.
    Weights are equal (0.25 each) because the IC Forum has not yet
    assigned its own weights. This is a simple heuristic that correlates
    with the IC Forum's actual confidence — when analysts are uncertain,
    the IC Forum will also be uncertain, and vice versa.
    """
    return sum(a["confidence"] for a in analyst_outputs) / len(analyst_outputs)
```

#### Definition of `disagreement_score`

```python
def disagreement_score(analyst_outputs: list[dict]) -> float:
    """Measure inter-analyst disagreement, 0.0 (full consensus) to 1.0 (split).

    Two dimensions:
    1. Direction disagreement: fraction of analysts whose bias direction
       differs from the majority. 0.0 = all same direction, 0.5 = 2 vs 2.
    2. Confidence spread: (max_confidence - min_confidence) across analysts.

    The final score combines both, weighted 0.7 for direction and 0.3 for
    confidence spread. Direction disagreement is the primary trigger —
    if two analysts say BUY and two say SELL, debate is almost certain.
    """
    biases = [a["bias"] for a in analyst_outputs]
    confidences = [a["confidence"] for a in analyst_outputs]

    # Majority direction
    bullish_count = biases.count("bullish")
    bearish_count = biases.count("bearish")
    neutral_count = biases.count("neutral")
    total = len(biases)
    majority = max(bullish_count, bearish_count, neutral_count)

    direction_disagreement = 1.0 - (majority / total)

    # Confidence spread
    confidence_spread = (max(confidences) - min(confidences)) if confidences else 0.0

    return 0.7 * direction_disagreement + 0.3 * confidence_spread
```

Both functions are deterministic, pure, and reproducible for the same inputs.
They are system code, never an LLM call. The thresholds
(`policy.ic_confidence_threshold`, `policy.disagreement_threshold`) are
configured in `policy_versions` and pinned at `CONTEXT_PINNED`.

### Debate round (conditional)

```
conversation D: Technical Analyst + Macro Analyst + News Analyst + SMC Analyst + Debate Moderator

inputs: analyst_json_1 .. analyst_json_4
rules:
  - each analyst may challenge one other argument once
  - moderator enforces 1 round and terminates
outputs: refined_analyst_json_1 .. refined_analyst_json_4
```

The moderator is a lightweight system role or dedicated agent whose only job
is to bound the round. The debate prompt explicitly forbids recursion.

### IC Forum round

```
conversation IC: IC Forum agent only

inputs:
  - analyst_json_1 .. analyst_json_4 (original or refined)
  - current portfolio context (exposure, open positions)
outputs: ic_output JSON
```

IC Forum is a single-turn call with all context in the user message.

### CIO Proposer round

```
conversation CIO: CIO Proposer agent only

inputs:
  - analyst_json_1 .. analyst_json_4
  - ic_output
  - mandate / portfolio context
outputs: final_proposal JSON
```

CIO Proposer is a single-turn call. Its output is the value stored in
`lineage_records.proposal`.

## Failure modes

| Failure | Handling |
|---------|----------|
| Analyst returns invalid JSON | Fail the stage; no IC round; lineage records the failure path. |
| Deterministic trigger raises | Treat as safe state: no debate, proceed with default path, flag for review. |
| Debate round returns invalid JSON | Discard debate, use pre-debate analyst outputs, flag for review. |
| IC Forum returns invalid JSON | No CIO round; safe state. |
| CIO Proposer returns invalid JSON | No proposal emitted; safe state. |

All failures are surfaced to Review (Phase 2 worker matrix) rather than
silently retried with relaxed validation.

## What this document does NOT define

- Exact prompt text for any role (prompt files under `docs/prompts/`; wording
  evolves in Phase 14+).
- JSON schemas for outputs (see `proposal-schema.md`).
- LLM gateway routing, retries, or provider selection (Phase 6).
- Code that creates AutoGen conversations (Phase 14+).

## Phase boundary

This document fixes the dynamic-round AutoGen orchestration pattern, the
authority boundaries between rounds, and the deterministic debate trigger.
It does not define prompt wording, output schemas (see
`proposal-schema.md`), gateway code, or production implementation.
