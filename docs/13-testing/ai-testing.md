# AI & LLM Testing

## Overview

Testing strategy for the non-deterministic parts of the system: LLM
outputs, AutoGen agent conversations, prompt quality, and model drift.
Three layers: schema contract (deterministic, CI), prompt quality
(offline eval, pre-registration), and decision quality (backtest +
paper outcome).

## Layer 1 — Schema contract tests

**What is tested:** Every AutoGen agent output must validate against
its JSON schema (Phase 4). This is deterministic — schema validation
does not depend on LLM output quality.

**Where:** CI, Level 3 (contract tests).

### Agent output schemas

| Agent | Schema | Required fields |
|-------|--------|-----------------|
| Technical Analyst | `technical_analyst_output` | `argument`, `confidence`, `bias`, `citations` |
| Macro Analyst | `macro_analyst_output` | `argument`, `confidence`, `bias`, `citations` |
| News Analyst | `news_analyst_output` | `argument`, `confidence`, `bias`, `citations` |
| SMC Analyst | `smc_analyst_output` | `argument`, `confidence`, `bias`, `citations` |
| IC Forum | `ic_forum_output` | `recommendation`, `confidence`, `summary`, `weights`, `dissent` |
| CIO Proposer | `cio_proposal_output` | `action`, `symbol`, `confidence`, `reasoning`, `overrode_ic`, `debate_held`, `analyst_inputs`, `ic_output`, `policy_version_id` |

### Test coverage per agent

```python
def test_technical_analyst_output_schema():
    output = technical_analyst.analyze(market_data_fixture)
    schema = load_schema("technical_analyst_output")
    jsonschema.validate(output, schema)
    assert 0.0 <= output["confidence"] <= 1.0
    assert output["bias"] in ["bullish", "bearish", "neutral"]
    assert isinstance(output["citations"], list)

def test_all_analysts_output_schema_validation():
    """Every analyst must produce valid JSON for a standard market input."""
    market_data = load_fixture("market_data/range_bound_xauusd.json")
    for agent in [technical, macro, news, smc]:
        output = agent.analyze(market_data)
        schema = load_schema(f"{agent.name}_output")
        jsonschema.validate(output, schema)

def test_ic_forum_output_with_split_committee():
    """IC Forum must produce valid output when analysts disagree."""
    analyst_inputs = [
        {"bias": "bullish", "confidence": 0.8},
        {"bias": "bearish", "confidence": 0.7},
        {"bias": "bullish", "confidence": 0.6},
        {"bias": "bearish", "confidence": 0.5},
    ]
    output = ic_forum.deliberate(analyst_inputs)
    schema = load_schema("ic_forum_output")
    jsonschema.validate(output, schema)
    assert "weights" in output
    assert len(output["weights"]) == 4

def test_cio_proposer_output_with_override():
    """CIO must be able to override IC and flag it."""
    output = cio_proposer.propose(ic_output, analyst_inputs)
    schema = load_schema("cio_proposal_output")
    jsonschema.validate(output, schema)
    # overrode_ic must be a boolean, not null
    assert isinstance(output["overrode_ic"], bool)
```

### Edge case coverage

| Edge case | Test |
|-----------|------|
| Empty market data | All agents return `confidence: 0.0`, `bias: "neutral"` |
| Extreme values | ATR = 0, EMA = 0, RSI = 0 or 100 |
| Missing data | One field missing from market data input |
| All analysts neutral | IC Forum must handle no consensus |
| Single analyst input | IC Forum with only 1 analyst (edge case) |
| Null citations | Citations must be `[]` not `null` |
| Very long argument | Argument > 10,000 chars — schema must accept |
| Unicode in argument | Non-ASCII characters — schema must not reject |

## Layer 2 — Prompt quality (offline eval)

**What is tested:** Does a prompt produce outputs that match the
author's expectations across a diverse set of scenarios?

**Where:** Offline, before prompt registration. Not in CI.

### Eval dataset structure

Datasets are YAML files stored in the repository alongside prompts.

```yaml
# prompts/evals/technical_analyst/datasets/range_bound.yml
name: "range_bound_market"
prompt_ref: "technical_analyst@v1"
scenarios:
  - id: "range_01"
    description: "XAUUSD in a tight 2-day range"
    input:
      symbol: "XAUUSD"
      timeframe: "H1"
      features:
        atr: 0.0012
        ema_fast: 2650.30
        ema_slow: 2650.45
        rsi: 52.1
        pivot_high: 2652.80
        pivot_low: 2648.10
    expected:
      bias: "neutral"
      min_confidence: 0.5
      must_contain:
        - "range"
        - "consolidation"
      must_not_contain:
        - "breakout"
        - "strong trend"

  - id: "range_02"
    description: "XAUUSD in a wide 5-day range"
    input:
      features:
        atr: 0.0045
        ema_fast: 2655.00
        ema_slow: 2650.00
        rsi: 48.3
    expected:
      bias: "neutral"
      min_confidence: 0.4
      must_contain:
        - "range"
      must_not_contain:
        - "breakout"
```

### Eval metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Bias accuracy | Correct bias prediction vs expected | ≥ 80% |
| Confidence calibration | Confidence within expected range | ≥ 80% |
| Containment | Expected keywords present | 100% |
| Exclusion | Forbidden keywords absent | 100% |
| Hallucination | No fabricated prices, symbols, or events | 100% |
| Schema valid | Output passes JSON schema validation | 100% |

### Eval workflow

```
1. Prompt author creates or modifies a prompt candidate
2. Run eval suite against all scenarios for that prompt
3. Review results:
   - Score ≥ 80% → prompt can be registered in the registry
   - Score < 80% → iterate on prompt, re-run eval
4. Register prompt → hash is computed and stored
5. Prompt is now immutable (hash-verified in CI)
```

### Hallucination detection

```python
def detect_hallucination(output, input_data):
    """Check if the LLM fabricated information not present in input."""
    # Extract all numeric values from output
    output_numbers = extract_prices(output["argument"])
    input_numbers = extract_prices(json.dumps(input_data))

    # Any price in output not in input (within tolerance)?
    for price in output_numbers:
        if not any(abs(price - inp) < 0.001 for inp in input_numbers):
            return True, f"Fabricated price: {price}"

    # Any symbol mentioned that is not in input?
    symbols_mentioned = extract_symbols(output["argument"])
    if input_data["symbol"] not in symbols_mentioned:
        return True, f"Wrong symbol: {symbols_mentioned}"

    return False, None
```

## Layer 3 — Decision quality

**What is tested:** Does the AI, as a system, produce profitable
decisions? This is measured by outcome, not by individual output.

**Where:** Backtest (Level 5) and paper trading (Level 6).

### Backtest quality metrics

| Metric | Threshold | Type |
|--------|-----------|------|
| Sharpe ratio | > 0 | Sanity check |
| Max drawdown | < 20% | Sanity check |
| Profit factor | > 1.0 | Sanity check |
| Win rate | No threshold | Informational |

These are sanity checks, not performance targets. A strategy that
fails these is likely broken. See `backtest-paper.md` for full
specification.

### Paper trading quality metrics

| Metric | Threshold | Type |
|--------|-----------|------|
| Order error rate | 0 | Must |
| Lineage completeness | 100% | Must |
| LLM cost within budget | Yes | Must |
| Decision consistency | Reasonable | Informational |

### Model drift detection

When a model provider updates a model (e.g., `gpt-5.5` → `gpt-5.6`),
or when the same model produces different outputs over time, the
system must detect it before it affects live trading.

```python
def detect_model_drift(model_id, prompt_version, scenarios):
    """Compare current model outputs to baseline."""
    current_outputs = run_eval_suite(model_id, prompt_version, scenarios)
    baseline = load_baseline(model_id, prompt_version)

    # Check confidence distribution drift
    current_conf = [o["confidence"] for o in current_outputs]
    baseline_conf = [o["confidence"] for o in baseline]
    drift_score = ks_test(current_conf, baseline_conf)

    # Check bias distribution drift
    current_bias = Counter(o["bias"] for o in current_outputs)
    baseline_bias = Counter(o["bias"] for o in baseline)
    bias_drift = sum(abs(current_bias[k] - baseline_bias[k])
                     for k in set(current_bias) | set(baseline_bias))

    return {
        "confidence_drift": drift_score,
        "bias_drift": bias_drift,
        "significant": drift_score > 0.3 or bias_drift > 0.2,
    }
```

**Drift detection schedule:**
- Weekly in staging: re-run 100 eval scenarios with current model.
- On model version bump: immediate re-run of all scenarios.
- Alert if drift is significant (KS statistic > 0.3 or bias shift > 20%).

### Prompt immutability test

```python
def test_prompt_immutability():
    """Every registered prompt must match its registered hash."""
    for prompt_ref in registry.list_prompts():
        stored_hash = registry.get_hash(prompt_ref)
        current_hash = sha256(read_file(prompt_ref.path))
        assert stored_hash == current_hash, \
            f"Prompt {prompt_ref} modified. Hash: {current_hash[:8]} != {stored_hash[:8]}"
```

This test runs in CI (Level 3 contract tests). It guarantees that
prompts cannot be changed without updating the registry hash — and
the registry hash update is a deliberate action, not an accident.

## What AI testing does NOT cover

- **Does not test "is this trade good?"** — there is no ground truth
  for trading decisions. The system tests that the AI produces
  structurally valid, consistent outputs, not that it produces
  profitable ones.
- **Does not mock LLM in system tests** — Level 4 system tests use
  mock LLM. AI quality is evaluated at Levels 5 (backtest) and 6
  (paper trading).
- **Does not have "AI unit tests"** — no `assert` on the natural
  language text of an LLM output. Only schema, confidence range,
  bias enum, and hallucination are asserted.
- **Does not evaluate prompt quality in CI** — prompt eval is an
  offline, pre-registration process. CI only verifies that
  registered prompts have not been modified (hash check).

## What this document does NOT define

- Eval harness implementation code (Phase 14+).
- Eval dataset content for each agent (Phase 14+ — authored alongside
  prompts).
- Drift detection implementation and baseline storage (Phase 14+).
- Prompt registration workflow automation (Phase 14+).
- Model provider selection and routing (Phase 6/7).

## Phase boundary

AI testing architecture, three-layer strategy, schema contract
requirements, prompt eval methodology, drift detection approach,
and prompt immutability enforcement are fixed here. Implementation
code and eval datasets belong to Phase 14+.