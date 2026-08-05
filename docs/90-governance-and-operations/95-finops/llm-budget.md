# LLM Budget

- **Status:** active
- **Owner:** ai-engineers / cio
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

## Budget structure
| Dimension | Budget | Action on exceed |
|-----------|--------|------------------|
| Daily total spend | $X/day | Alert; if >2× → page |
| `strongest` tier daily | $Y/day (small) | Alert; throttle escalation (admission-control) |
| `context-rich` tier daily | $Z/day | Alert |
| Per-book daily | $B/day | Alert; consider book-level kill switch |
| Research monthly | $R/month | Hard cap; `research_budget` knob to zero when hit (ADR-0026) |

Exact values are set in `policy_versions.finops` (JSONB) and versioned —
budget changes are policy-version promotions, not ad-hoc config edits.

## Cost circuit breaker
Modeled on the Phase 6 cost breaker: if daily spend exceeds the
kill-switch-adjacent threshold, the system **escalates one tier down** for
non-critical roles (analysts) or **degrades gracefully** (skip debate,
per recovery-and-termination `workflow_degrades_total`). This is a
journal-recorded degrade event, never a silent quality drop.

## Calibration tie-in
Over-escalation is the #1 cost driver. Confidence calibration (ADR-0032)
prevents escalating on noise. A model with bad calibration is a cost risk,
not just a quality risk — calibration gates budget health too.

## What this does NOT define
- Provider unit pricing (lives in `model_versions` registry, updated per provider).
- The admission-control mechanism (ADR-0022, Phase 6).
