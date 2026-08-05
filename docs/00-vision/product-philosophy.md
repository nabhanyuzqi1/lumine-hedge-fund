# Product Philosophy

These principles govern every later phase. When a design decision conflicts
with a principle, the conflict is resolved explicitly and recorded, not
silently.

## 1. Capital outcomes over agent theater

Agent count, conversation volume, and LLM activity have no intrinsic value.
Every agent must measurably improve decision quality, control, evidence, or
accountability. Agents that exist only for narrative symmetry are removed.

## 2. Deterministic controls over LLM promises

LLMs reason; deterministic systems calculate, validate, persist, schedule,
reconcile, and enforce. Any function that can be deterministic must be
deterministic. LLMs are reserved for reasoning tasks: market interpretation,
news understanding, conflict resolution, committee deliberation, risk
discussion, and strategy explanation.

## 3. Autonomy within governance

The system operates production trades autonomously. The human CIO controls
production admission, emergency stop, and restart. Autonomy never extends
to bypassing governance authority.

## 4. Evidence before capital

No strategy touches live capital without passing research → out-of-sample →
forward paper → limited-live gates. Evidence windows must be sufficient to
distinguish edge from noise.

## 5. Independent strategy books

Intraday and swing mandates remain separately attributable, testable,
promotable, and suspendable. Performance, risk, and capital are never
blended into a single opaque position.

## 6. Reproducibility before adaptation

Every production decision must identify the data, features, strategy,
prompt, model, policy, and code versions that produced it. Without
reproducibility, adaptation is indistinguishable from drift.

## 7. Self-modification as research, not production authority

Adaptive candidates (strategies, prompts, models, policies) run in
sandbox or shadow mode. Production promotion requires independent
evidence and CIO approval. The system never promotes its own modifications
into production.

## 8. Internal fund OS, not retail product

Lumine is an operating system for proprietary capital. It is not a signals
business, copy-trading service, client platform, or marketplace. Product
decisions optimize for institutional quality, not retail reach.

## 9. Architect for replaceability

Every component — broker, model, prompt, strategy, data source, agent
framework — must be replaceable without rewriting the platform. Lock-in is
treated as a defect.

## 10. Safe state by default

Any failure, ambiguity, or loss of control must drive the system toward a
safe state (flat or reduced exposure, strategy suspension, alert), never
toward expanded risk. When in doubt, do less.
