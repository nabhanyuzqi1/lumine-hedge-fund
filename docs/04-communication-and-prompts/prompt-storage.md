# Prompt Storage & Versioning

## Overview

Phase 4 owns how prompts are stored and how the `prompt_versions` registry
references them. The registry schema was locked in Phase 3; this document
fills in the `prompt_ref` and `prompt_hash` semantics and the on-disk layout.

## Decision: files in repo

Prompts live as plain text files in the repository, one file per sub-role
version, under `docs/prompts/`.

```
docs/prompts/
├── technical_analyst@v1.prompt
├── technical_analyst@v2.prompt
├── macro_analyst@v1.prompt
├── news_analyst@v1.prompt
├── smc_analyst@v1.prompt
├── ic_forum@v1.prompt
└── cio_proposer@v1.prompt
```

Each file is the complete prompt template for one sub-role at one version.
Multiple versions may coexist so that old `lineage_records` can still resolve
the exact prompt that produced them.

## Registry contract

The `prompt_versions` table (Phase 3 schema) has these relevant columns:

| Column | Value in Phase 4 |
|--------|------------------|
| `sub_role` | `technical_analyst`, `macro_analyst`, `news_analyst`, `smc_analyst`, `ic_forum`, `cio_proposer` |
| `prompt_hash` | SHA-256 hex digest of the prompt file content at import time |
| `prompt_ref` | Relative path from repo root, e.g. `docs/prompts/technical_analyst@v1.prompt` |
| `variables` | JSONB list of expected template variables (see below) |
| `output_schema` | JSONB JSON-Schema describing the required structured output |

### Import-time hash

When a new prompt version is registered, the importer:

1. Reads the file at `prompt_ref`.
2. Computes SHA-256 of the exact bytes.
3. Stores the hex digest in `prompt_hash`.

`prompt_hash` is immutable. If the file on disk is later edited without
creating a new registry row, the hash will diverge from pinned hashes in old
`lineage_records`, making replay drift detectable.

### Version naming

Prompt versions use the same SEMVER convention as other registry artifacts
(`v1`, `v1.1`, `v2`, etc.). Breaking changes to variables or output schema
must bump at least the minor version; patch versions are for wording-only
changes that preserve schema compatibility.

## File format

A prompt file is plain text. It may contain:

- A YAML frontmatter block (optional but recommended) with metadata such as
  `sub_role`, `version`, `model_tier_hint`, and `description`.
- The prompt body, using a lightweight template syntax (e.g. Liquid-style
  `{{ variable }}`) for variables defined in `prompt_versions.variables`.

Example:

```text
---
sub_role: technical_analyst
version: v1
---

You are the Technical Analyst for an institutional XAUUSD trading committee.

Input features:
- ATR: {{ atr }}
- EMA 20: {{ ema_20 }}
- RSI 14: {{ rsi_14 }}
- Latest OHLC: {{ ohlc }}

Output a JSON object exactly matching this schema:
{{ output_schema }}

Do not include markdown code fences. Respond with raw JSON only.
```

## Variables contract

`prompt_versions.variables` is a JSONB array of variable names the prompt
expects. The caller (Phase 14+ code) must supply all of them. Missing
variables are a validation failure, not a silent fallback.

Example variables for an analyst prompt:

```json
["atr", "ema_20", "rsi_14", "ohlc", "output_schema"]
```

## Output schema contract

`prompt_versions.output_schema` is a JSONB JSON-Schema that constrains the
LLM's response. The caller passes this schema into the prompt so the model
knows the required structure; the caller also validates the parsed response
against the same schema. Producer + consumer both validate (principle #10).

## Why files, not database blobs

- Git-native provenance: every change has author, diff, and PR review.
- Human-readable during development and incident response.
- No separate prompt deployment pipeline; the registry row is just a pointer
  and a hash.
- Old versions stay in the repo forever, satisfying principle #6.

## What this document does NOT define

- Specific prompt text or tuning (Phase 4 owns the format, not the wording;
  wording evolves through Phase 14+ eval work).
- The runtime templating engine (Phase 14+).
- Access control or encryption for prompts (Phase 11 — Security).

## Phase boundary

This document fixes the prompt file layout, `prompt_ref` semantics, and the
hash contract. It does not define prompt content (evolving), the templating
engine (Phase 14+), or security controls (Phase 11).
