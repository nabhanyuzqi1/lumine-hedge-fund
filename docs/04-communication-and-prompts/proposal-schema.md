# Proposal JSONB Schema

## Overview

This document defines the sub-structure of `lineage_records.proposal`, which
Phase 3 left as JSONB to be finalized in Phase 4. The schema is what the CIO
Proposer outputs and what gets pinned to every decision for reproducibility.

## Top-level schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": [
    "version",
    "decision_ts",
    "symbol",
    "action",
    "confidence",
    "reasoning",
    "debate_held",
    "overrode_ic",
    "analyst_inputs",
    "ic_output",
    "policy_version_id",
    "model_version_ids",
    "prompt_version_ids"
  ],
  "properties": {
    "version": { "type": "string", "const": "v1" },
    "decision_ts": { "type": "string", "format": "date-time" },
    "symbol": { "type": "string", "example": "XAUUSD" },
    "action": { "type": "string", "enum": ["BUY", "SELL", "HOLD", "REJECT"] },
    "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
    "reasoning": { "type": "string" },
    "debate_held": { "type": "boolean" },
    "overrode_ic": { "type": "boolean" },
    "override_reason": { "type": "string" },
    "analyst_inputs": {
      "type": "array",
      "items": { "$ref": "#/definitions/analyst_output" }
    },
    "ic_output": { "$ref": "#/definitions/ic_output" },
    "policy_version_id": { "type": "string", "format": "uuid" },
    "model_version_ids": {
      "type": "object",
      "properties": {
        "technical_analyst": { "type": "string", "format": "uuid" },
        "macro_analyst": { "type": "string", "format": "uuid" },
        "news_analyst": { "type": "string", "format": "uuid" },
        "smc_analyst": { "type": "string", "format": "uuid" },
        "ic_forum": { "type": "string", "format": "uuid" },
        "cio_proposer": { "type": "string", "format": "uuid" }
      },
      "required": ["technical_analyst", "macro_analyst", "news_analyst", "smc_analyst", "ic_forum", "cio_proposer"]
    },
    "prompt_version_ids": {
      "type": "object",
      "properties": {
        "technical_analyst": { "type": "string", "format": "uuid" },
        "macro_analyst": { "type": "string", "format": "uuid" },
        "news_analyst": { "type": "string", "format": "uuid" },
        "smc_analyst": { "type": "string", "format": "uuid" },
        "ic_forum": { "type": "string", "format": "uuid" },
        "cio_proposer": { "type": "string", "format": "uuid" }
      },
      "required": ["technical_analyst", "macro_analyst", "news_analyst", "smc_analyst", "ic_forum", "cio_proposer"]
    }
  },
  "definitions": {
    "analyst_output": {
      "type": "object",
      "required": ["sub_role", "argument", "confidence", "bias"],
      "properties": {
        "sub_role": { "type": "string", "enum": ["technical_analyst", "macro_analyst", "news_analyst", "smc_analyst"] },
        "argument": { "type": "string" },
        "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
        "bias": { "type": "string", "enum": ["bullish", "bearish", "neutral"] },
        "citations": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    },
    "ic_output": {
      "type": "object",
      "required": ["recommendation", "confidence", "summary", "weights", "dissent"],
      "properties": {
        "recommendation": { "type": "string", "enum": ["BUY", "SELL", "HOLD", "REJECT"] },
        "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
        "summary": { "type": "string" },
        "weights": {
          "type": "object",
          "properties": {
            "technical_analyst": { "type": "number" },
            "macro_analyst": { "type": "number" },
            "news_analyst": { "type": "number" },
            "smc_analyst": { "type": "number" }
          },
          "required": ["technical_analyst", "macro_analyst", "news_analyst", "smc_analyst"]
        },
        "dissent": { "type": "string" }
      }
    }
  }
}
```

## Field semantics

| Field | Meaning |
|-------|---------|
| `version` | Schema version of the proposal object. Starts at `v1`. |
| `decision_ts` | Timestamp when the proposal was produced (same as `lineage_records.decision_ts`). |
| `symbol` | Trading symbol, e.g. `XAUUSD`. |
| `action` | Proposed action from CIO. `BUY`/`SELL` go to RiskValidator; `HOLD`/`REJECT` end the proposal path. |
| `confidence` | CIO confidence in the final proposal, 0.0–1.0. |
| `reasoning` | Concise CIO reasoning. |
| `debate_held` | `true` if the optional debate round ran. |
| `overrode_ic` | `true` if CIO action differs from IC recommendation. |
| `override_reason` | Required when `overrode_ic` is `true`. |
| `analyst_inputs` | Array of the 4 analyst outputs (original or post-debate). |
| `ic_output` | Full IC Forum output, including weights and dissent. |
| `policy_version_id` | UUID of the active policy version (thresholds, debate trigger). |
| `model_version_ids` | Per-sub-role model version UUIDs pinned for this decision. |
| `prompt_version_ids` | Per-sub-role prompt version UUIDs pinned for this decision. |

## JSON Schema files

A copy of this schema lives in `schemas/proposal-v1.json` (Phase 3 decision:
one JSON Schema file per stream/payload). It is used by both the producer
(CIO Proposer validates its own output before returning) and the consumer
(`trade-core` validates before writing to `lineage_records`).

## Validation rules beyond JSON Schema

- `analyst_inputs` must contain exactly one entry for each of the four
  sub-roles.
- The sum of `ic_output.weights` should equal `1.0` within a small epsilon;
  if not, the consumer flags the record for review rather than rejecting it
  outright (safe state + human review, principle #10).
- If `overrode_ic` is `true`, `override_reason` must be non-empty.
- `action` may differ from `ic_output.recommendation` only when
  `overrode_ic` is `true`.

## What this schema does NOT define

- Risk math, sizing, or stop-loss values (Phase 8).
- MT5 command format (Phase 8).
- API / backtest-facing contracts (Phase 9).
- Runtime code that validates or produces the proposal (Phase 14+).

## Phase boundary

This document fixes the `lineage_records.proposal` JSONB sub-structure,
including analyst, IC Forum, and CIO Proposer output shapes. It does not
define risk math, execution protocol, or production code.
