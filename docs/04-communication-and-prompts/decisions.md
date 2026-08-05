# Phase 4 — Locked Decisions

## Decision log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Prompt storage = files in repo** | One prompt file per sub-role under `docs/prompts/` (e.g. `technical_analyst@v1.prompt`). `prompt_ref` in `prompt_versions` stores the relative path; `prompt_hash` is SHA-256 of the file content computed at registry-import time. Git-native provenance, PR review, and diff history for free. Registry remains the version/drift-detection envelope. |
| 2 | **AutoGen orchestration = dynamic rounds** | Each stage of the committee is a separate AutoGen conversation created on demand: (a) 4 analysts in parallel, (b) optional 1 bounded debate round, (c) IC Forum, (d) CIO Proposer. Matches the adaptive-parallel topology locked in Phase 2 and keeps each stage independently validatable. |
| 3 | **Analyst output = structured JSON** | Every analyst returns a strict JSON object: `argument`, `confidence`, `bias`, and optional `citations`. Deterministic parsing, no regex on narrative, supports deterministic debate trigger and reproducible lineage. |
| 4 | **IC Forum output = JSON with per-analyst reasoning** | IC Forum returns `recommendation`, `confidence`, `summary`, `weights` per analyst input, and `dissent`. Preserves evidence of how consensus was reached and supports CIO override authority. |
| 5 | **Debate trigger = deterministic code, not LLM** | After the analyst round, system code checks IC confidence and inter-analyst disagreement against thresholds stored in `policy_versions`. Only if a threshold is breached is the optional debate round invoked. Keeps escalation reproducible (principle #6) and safe (principle #10). |
| 6 | **CIO Proposer receives IC output + all 4 raw analyst outputs** | CIO is final authority and may override IC (Phase 2 authority rule). Passing the full context prevents information loss and makes override decisions auditable. |
| 7 | **CIO Proposer output = full JSON with audit trail** | Final proposal includes `action`, `symbol`, `confidence`, `reasoning`, `overrode_ic`, `debate_held`, `analyst_inputs`, `ic_output`, and `policy_version_id`. This becomes the canonical sub-structure stored in `lineage_records.proposal`. |

## Principles honored

- **#4 Evidence before capital**: every proposal carries its own evidence chain (analyst inputs, IC weights, dissent, CIO override flag).
- **#6 Reproducibility before adaptation**: strict schemas, deterministic debate trigger, file-backed prompts with SHA-256 hashes, and version pins all make a decision replayable.
- **#9 Replaceability**: model IDs, prompt files, and policy thresholds are all resolved from registry; no hardcoded model names or prompt text in code.
- **#10 Safe state by default**: deterministic trigger and strict JSON schemas reduce failure modes; malformed outputs fail validation instead of silently propagating.

## Phase boundary respected

Phase 4 fixes prompt storage, AutoGen orchestration pattern, and proposal
schemas. It does NOT define: workflow recovery (Phase 7), risk math or
MT5 protocol (Phase 8), API contracts (Phase 9), or production code
(Phase 14+).
