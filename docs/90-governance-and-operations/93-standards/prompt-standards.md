# Prompt Standards

- **Status:** active
- **Owner:** ai-engineers / cio
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90
- **Source:** promoted from `docs/04-communication-and-prompts/prompt-storage.md`

## File format
- One file per sub-role version: `backend/src/lumine/prompts/templates/{sub_role}@v{n}.prompt`.
- YAML frontmatter: `sub_role`, `version`, `model_tier_hint`, `description`.
- Body: Liquid-style `{{ variable }}` templating; raw-JSON output instructions.

## Versioning & hashing (ADR-0015, CLAUDE.md rule 10)
- `prompt_versions` registry: `sub_role`, `version`, `prompt_ref`, `prompt_hash`
  (SHA-256 of file bytes at import), `variables`, `output_schema`.
- `prompt_hash` is immutable. Editing a file without a new registry row →
  hash diverges from pinned hashes → replay drift detected.

## Eval binding (ADR-0028)
- `prompt_versions` carries `eval_suite_id` (FK to `eval_suites`) and
  `eval_pass_hash`.
- Promotion to `production` REFUSED unless `eval_pass_hash` resolves to a
  passing eval run for the current `model_version_id`.
- Eval must run on the EXACT model version being promoted.

## Compatibility
- Breaking changes (removed/required variables, output schema change) bump
  major version; backward-compatible additions are minor (per
  `inter-agent-message-versioning.md` ADR-0038).

## Output validation
- Producer and consumer both validate against `output_schema` (principle #10).
- Missing variables = validation failure, not silent fallback.

## Untrusted input
- External data (news) enters via structured extraction, never raw in the
  prompt body (ADR-0018). Data lives in a fenced `<data>` block.

## Reasoning traces
- The full prompt actually sent (post-templating, post-truncation) is stored
  in `reasoning_traces` with its hash (ADR-0029, ADR-0036).

## Anti-patterns
- No dynamic prompt assembly that depends on non-pinned state.
- No inter-cycle memory bleed into the prompt (ADR-0027 working-memory tier only).
- No "ask the model which model to use" routing (ADR-0004).
