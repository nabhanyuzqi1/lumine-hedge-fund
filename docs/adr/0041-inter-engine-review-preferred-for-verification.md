# ADR-0041 — Inter-engine review preferred for verification

- **Status:** Accepted
- **Phase:** 14-implementation
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

CLAUDE.md rule 8 requires that every non-trivial implementation be verified
by a separate agent before reporting completion. Rule 9 states that
cross-engine reviews are preferred when available for verification agents.
A same-engine verifier shares the same blind spots and failure modes as
the implementer; a cross-engine verifier brings a different model's
reasoning, reducing the risk of shared systematic errors going undetected.

## Decision

Cross-engine reviews are preferred for verification agents. When a
verification agent is available on a different model/engine than the
implementer, that agent should be used for independent verification. Every
non-trivial implementation must still be verified by a separate agent
(rule 8); the preference for cross-engine (rule 9) strengthens that
requirement by reducing shared blind spots.

## Rationale

- A same-engine verifier shares the implementer's systematic biases and
  failure modes.
- Cross-engine verification brings a different model's reasoning to bear on
  the same artifact, catching errors the implementer's engine would
  systematically miss.
- The preference is not a hard requirement (cross-engine may not always be
  available) but the default when a verifier is selected.
- Independent verification is a first-class quality gate, not an
  afterthought.

## Consequences

- Positive: shared systematic errors are more likely to be caught.
- Positive: verification quality improves with engine diversity.
- Negative: cross-engine verification may add latency or cost (different
  model, different provider).
- Reversibility: the preference is a process rule; it can be tightened or
  relaxed without architectural change.

## Cross-references

- Related ADRs: ADR-0042, ADR-0043
- Implements principle(s): #4
- Affects phases: 14, 15
- Source document: `../../CLAUDE.md` (rule 9)
