# Reasoning Trace Storage — Closing the "Why" Audit Gap

## Overview

Decision **D7-11**: every LLM stage call writes a full reasoning trace
to a new `reasoning_traces` table, and `lineage_records` references
the trace IDs so a decision's full reasoning chain is reconstructable.

`lineage-schema.md` (Phase 3) pins the proposal JSONB — the committee
*output*. It does not store the *reasoning*. An auditor asking "why
did the committee decide this?" cannot answer it from the proposal
alone: the proposal is the synthesized action, not the chain of
argument that produced it. This document closes that gap without
violating reproducibility (#6) or the stateless policy (D6-5).

## Decision: `reasoning_traces` table

### Schema

```sql
CREATE TABLE reasoning_traces (
  trace_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id    UUID NOT NULL,              -- FK workflow_runs (Phase 7 journal)
  stage_run_id       UUID NOT NULL,              -- FK stage_runs (Phase 7 journal)
  role               TEXT NOT NULL,              -- 'technical_analyst' | 'macro_analyst' | ... | 'cio_proposer'
  model_version_id   UUID NOT NULL,              -- FK model_versions
  prompt_version_id  UUID NOT NULL,              -- FK prompt_versions
  prompt_sent        TEXT NOT NULL,              -- full post-templating prompt, exactly as sent
  response_raw       TEXT NOT NULL,              -- full model response, including reasoning tokens where exposed
  parsed_output      JSONB NOT NULL,             -- schema-validated parsed output (the stage's contribution)
  prompt_hash        TEXT NOT NULL,              -- SHA-256 of prompt_sent (immutable)
  response_hash      TEXT NOT NULL,              -- SHA-256 of response_raw (immutable)
  ts                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_traces_run    ON reasoning_traces (workflow_run_id);
CREATE INDEX idx_traces_stage  ON reasoning_traces (stage_run_id);
CREATE INDEX idx_traces_role   ON reasoning_traces (role, ts);
```

### One row per stage LLM call

Each LLM invocation in the workflow writes exactly one row. A cycle
with 4 analysts + 1 IC Forum + 1 CIO Proposer = 6 rows (more if
debate or escalation fires). The row is written synchronously with
the stage's completion, before the workflow advances — same blocking
discipline as `lineage_records` (principle #10: safe state by
default). If the trace write fails, the stage does not advance.

### Linkage to lineage

`lineage_records.proposal` (Phase 3 JSONB) gains a
`reasoning_trace_ids` array referencing the trace IDs that compose
the decision:

```json
{
  "reasoning_trace_ids": [
    "<trace_id_tech>",
    "<trace_id_macro>",
    "<trace_id_news>",
    "<trace_id_smc>",
    "<trace_id_ic>",
    "<trace_id_cio>"
  ],
  "debate_held": false,
  "overrode_ic": false,
  ...
}
```

This is a non-breaking addition to the proposal JSONB; existing
proposal fields are unchanged. An auditor reconstructs the full
reasoning chain by resolving the array.

## Hash pinning and replay integrity

`prompt_hash` and `response_hash` are immutable. On replay:

1. Re-resolve `prompt_version_id` and `model_version_id` from the
   trace row.
2. Rebuild `prompt_sent` from the versioned prompt template + the
   pinned `trigger` / `features` / `risk_context` in lineage.
3. Hash the rebuilt prompt; compare to `prompt_hash`. Divergence =
   alert (prompt drift, context builder bug, or tampering).
4. Re-invoke the model; hash the new response; compare to
   `response_hash`. Divergence is *expected* (LLM nondeterminism) and
   is recorded but does not alert. Structural divergence (different
   action, different verdict) alerts.

The prompt hash is the load-bearing one: it proves the model saw
exactly what the record says it saw. The response hash is a
fingerprint for change detection, not a replay equality assertion.

## Provider differences: reasoning tokens

Some providers expose reasoning tokens (chain-of-thought, thinking
summaries); some do not. The contract:

| Provider mode | `response_raw` content |
|---------------|------------------------|
| Reasoning tokens exposed (e.g. o1-style thinking, DeepSeek reasoning trace) | Full response including reasoning tokens, verbatim |
| Reasoning tokens not exposed (standard completions) | The raw completion text; the gap is noted in `parsed_output._reasoning_gap: true` |
| Streaming responses | Reassembled full text; no partial fragments stored |

Where reasoning tokens are not exposed, the audit gap is partial: the
"why" is answerable from the completion's stated reasoning (most
analyst prompts require an `argument` field), but not from a hidden
chain-of-thought. The `_reasoning_gap` flag makes this explicit rather
than silent. The gap is a provider limitation, not a system defect.

## Retention

**Permanent.** Decision-rate, not tick-rate: even at 100 cycles/day
the table grows at ~600 rows/day, ~220k rows/year. Text compresses
well; cold storage is cheap. Deletion is forbidden — old traces are
the audit record (principle #4). Retention policy is identical to
`lineage_records`: append-only, no UPDATE, no DELETE.

## Privacy and encryption

Reasoning traces may contain position data, strategy reasoning, and
market context. They are **encrypted at rest** (Phase 12). Access is
logged (Phase 12 audit log). The `prompt_sent` and `response_raw`
columns are the encrypted payload; `prompt_hash`, `response_hash`,
and the ID/foreign-key columns are plaintext (they are hashes and
references, not content) to keep queries and joins functional.

Decryption keys are managed per Phase 12; this document does not
redefine key management.

## What this closes

Before: `lineage_records.proposal` stores the committee's output
(action, side, confidence, reasoning summary). An auditor can answer
"what was decided?" and "what did the CIO say the reasoning was?".
They cannot answer "what did each analyst actually argue, in full,
including the model's verbatim response?".

After: the `reasoning_trace_ids` array lets the auditor pull every
analyst's full prompt and response, the IC Forum's full debate, and
the CIO Proposer's full synthesis. The "why" is answerable from
stored reasoning, not just the "what".

## What this document does NOT define

- The prompt templating engine (Phase 14+).
- Eval harness integration with traces (Phase 13 evals consume
  `parsed_output`; traces are the raw substrate, not the eval unit).
- Decryption key rotation (Phase 12).
- Streaming reassembly implementation (Phase 14+).
- Retention storage tiering (Phase 5 physical storage, Phase 11
  infra).

## Phase boundary

This document amends `lineage-schema.md` (Phase 3) by adding the
`reasoning_trace_ids` array to the proposal JSONB, and amends
`observability.md` (Phase 7) by defining the trace table that the
trace spans reference. It does not alter the blocking ACID gate
(Phase 3), the stateless policy (D6-5, Phase 6), or the failure
taxonomy (Phase 7). It defines one new table and its linkage; DDL
refinement and physical indexes belong to Phase 5, code to Phase 14+.
