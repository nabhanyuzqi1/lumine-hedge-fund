# Observability Schema

- **Status:** active
- **Owner:** devops / architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

Fixes the **what** of observability: log fields, metric names, trace
structure, correlation. The **where** (shippers, sinks) is Phase 11
topology. Principle: telemetry is a projection of the journal (D7-10); the
journal wins on conflict.

## Structured logs (JSON)
Every log line carries the journal event fields plus `service`, `host`,
`level`:

| Field | Source |
|-------|--------|
| `workflow_run_id` | journal |
| `stage_run_id` | journal (stage-level events) |
| `logical_call_id` | gateway idempotency key (Phase 6) |
| `lineage_id` | present only after the lineage gate |
| `ts` | UTC iso8601 |
| `from_state`, `to_state` | lifecycle states |
| `failure_code` | taxonomy (recovery-and-termination.md) |
| `recovery_action` | when applicable |
| `tier`, `model_version_id` | post-fallback |
| `service`, `host`, `level` | infra |

Log level mapping per `07-autogen/observability.md`.

## Metrics (Prometheus-style)
Counters/histograms; labels are **low-cardinality** (no symbol, no run IDs
in metric labels — identity lives in logs/traces/journal).

| Metric | Type | Labels |
|--------|------|--------|
| `workflow_runs_total` | counter | `book`, `strategy`, `terminal_state` |
| `workflow_stage_duration` | histogram | `stage` |
| `workflow_run_duration` | histogram | `book`, `strategy` |
| `workflow_failures_total` | counter | `failure_code` |
| `workflow_resumes_total` | counter | `outcome` (resumed/aborted) |
| `workflow_degrades_total` | counter | `kind` (escalation-skipped/debate-skipped/…) |
| `gateway_admission_total` | counter | `lane`, `outcome` (accepted/rejected) |
| `gateway_tokens_in_flight` | gauge | `tier` |
| `gateway_queue_depth` | gauge | `lane` |
| `llm_tokens_total` | counter | `role`, `tier`, `model_version_id` |
| `llm_cost_total` | counter | `role`, `tier` |
| `lineage_write_latency` | histogram | (none) |
| `reconciliation_breaks_total` | counter | `break_type` |
| `tca_slippage_bps` | histogram | `symbol`, `broker_id`, `regime_id` |
| `calibration_eca` | gauge | `role`, `model_version_id` |

## Traces (OpenTelemetry)
- One trace per `workflow_run_id`; spans per `stage_run_id`; child spans
  per `logical_call_id`.
- Span attributes: `tier`, `model_version_id` actually used (post-fallback),
  `prompt_version_id`, `policy_version_id`, `feature_version_id`,
  `regime_version_id`, `calendar_version_id`.
- W3C `traceparent` propagated across the agent → gateway → DB boundary.
- Trace status mirrors stage outcome; the trace is reconstructable from the
  journal alone (D7-10).

## Dashboards as code
- Grafana dashboards committed as JSON in `docs/11-infrastructure/dashboards/`.
- Provisioned via infra-as-code (Phase 11). Drift between committed and live
  dashboards = CI warning.

## Alert triggers
Per `07-autogen/observability.md` plus:
- `reconciliation_breaks_total{break_type="position_mismatch"}` > 0 → page
- `lineage_write_latency` p99 > 10ms → warn
- `calibration_eca` > threshold → warn (ADR-0032)
- `tca_slippage_bps` p99 > threshold → warn (ADR-0040)
- chain-verification failure → page (ADR-0017)

## Phase boundary
Fixes the schema. Shippers/sinks/retention are Phase 11.
