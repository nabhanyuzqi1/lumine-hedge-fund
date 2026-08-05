# Prompt Versioning & Registry Contract

- **Status:** active
- **Owner:** ai-engineers / cio
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

This document defines the **enforcement** contract for CLAUDE.md rule 10
("prompts versioned, hashed, auditable") and ADR-0028 ("no prompt ships
without a passing eval"). `prompt-storage.md` defines the file layout and
hash semantics; this defines the registry, the loader, and the promotion gate.

## Registry: `prompt_versions` (amends Phase 3 schema)

| Column | Value |
|--------|-------|
| `sub_role` | `technical_analyst`, `macro_analyst`, `news_analyst`, `smc_analyst`, `ic_forum`, `cio_proposer`, `risk_officer` |
| `version` | semver: `v1`, `v1.1`, `v2` |
| `prompt_ref` | repo-relative path, e.g. `backend/src/lumine/prompts/templates/technical_analyst@v1.prompt` |
| `prompt_hash` | SHA-256 hex of the file bytes at import. Immutable. |
| `variables` | JSONB array of expected template variables |
| `output_schema` | JSONB JSON-Schema for structured output |
| `eval_suite_id` | FK to `eval_suites` (ADR-0028) |
| `eval_pass_hash` | hash of the passing eval result manifest for the target model_version |
| `model_tier_hint` | enum: `cost-efficient` / `context-rich` / `strongest` |
| `compatibility` | `exact` / `backward_compatible` / `breaking` (ADR-0038) |
| `superseded_by` | UUID nullable (ADR-0025) |
| `status` | `draft` / `production` / `deprecated` |
| `created_at`, `promoted_at`, `promoted_by` | audit |

## Import-time hash (ADR-0015)
1. Read file at `prompt_ref`.
2. Compute SHA-256 of exact bytes.
3. Store hex in `prompt_hash`. Immutable thereafter.
4. On any read at runtime, recompute and compare; divergence = fatal error
   (the file was edited without a new registry row).

## Promotion gate (ADR-0028) — machine-enforced
The promotion API REFUSES to flip `status` → `production` unless:
1. `eval_suite_id` is set.
2. `eval_pass_hash` resolves to an eval run that PASSED `eval_suites.threshold`
   for the **current** `model_version_id` mapped to this sub_role.
3. Eval was run on the exact model version (no cross-model substitution).
4. For `breaking` compatibility: the prior `production` version remains
   `production` until in-flight runs pinning it terminate (graceful cutover,
   ADR-0025).

## Runtime loader contract
`backend/src/lumine/prompts/registry.py`:
- Loads `registry.yaml` (the human-editable source) and verifies each row's
  hash against the file on disk at startup. Mismatch = fatal.
- Exposes `get_prompt(sub_role, version) -> (text, variables, output_schema, pins)`.
- Templating (Liquid-style) happens here; the **full templated prompt** is
  stored in `reasoning_traces` (ADR-0029) with its hash.
- No `os.environ` or dynamic state in templating — only pinned variables.

## Lineage pinning
`lineage_records.prompt_version_id` pins the exact version. Replay resolves
the version, verifies the hash, and reproduces the prompt. A divergent hash
on replay = alert (the file changed under a pinned version).

## Anti-patterns (rejected)
- Editing a `production` prompt file in place (use a new version).
- Promoting without eval (ADR-0028).
- Cross-model eval substitution (eval must be on the target model).
- Dynamic prompt assembly from non-pinned state (breaks reproducibility).

## Phase boundary
This amends `prompt-storage.md` (Phase 4) and `registry-schema.md` (Phase 3)
with the enforcement contract. The loader is Phase 14 code; the eval gate is
Phase 13.
