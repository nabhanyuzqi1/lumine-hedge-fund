# Prompt Change Policy

- **Status:** active
- **Owner:** ai-engineers / cio
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

## Workflow
1. Author the new prompt version file (`{sub_role}@v{n+1}.prompt`).
2. Run `make eval` against the target `model_version_id` on the eval suite
   (`eval_suites` row bound to the sub_role).
3. Eval must pass all thresholds (`eval_suites.threshold`).
4. Register `prompt_versions` row with `eval_suite_id` + `eval_pass_hash`.
5. Promotion API flips status → `production` ONLY if `eval_pass_hash`
   resolves to a passing run for the current model version (ADR-0028).
6. Set `compatibility` (`backward_compatible` / `breaking`) per
   `inter-agent-message-versioning.md` (ADR-0038).
7. ADR if architectural; `deviation-log.md` entry otherwise.

## Approval
- Minor (backward-compatible wording): AI engineer + eval pass.
- Major (breaking: variables/schema change): AI engineer + CIO sign-off + ADR.
- Any change touching the Risk Officer or CIO Proposer prompts: CIO sign-off always.

## Rollback
- Flip status back per `rollback-runbook.md`. In-flight runs handle via
  supersession gates (ADR-0025).

## Forbidden
- Editing a `production` prompt file in place (hash would diverge — ADR-0015).
- Promoting without eval (ADR-0028).
- Bypassing the instruction-hierarchy / untrusted-input rules (ADR-0018).
