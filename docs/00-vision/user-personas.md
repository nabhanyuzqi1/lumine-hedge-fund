# User Personas

## Primary persona — Autonomous fund system

The system itself is the primary operating user of the platform. It
researches, decides, executes, supervises, and reviews without routine
human operation.

**Goals**

- Generate and execute profitable XAUUSD decisions continuously.
- Coordinate research, market reasoning, risk, portfolio, execution, and
  review functions.
- Adapt exposure to regime, volatility, evidence quality, and strategy
  health.
- Detect degraded operation and enter a safe state.

**Constraints**

- Cannot bypass the CIO kill switch.
- Cannot restart after a CIO-initiated shutdown.
- Cannot self-promote sandbox artifacts (strategies, prompts, models,
  policies) into production.
- Must preserve decision lineage and disclose uncertainty.
- Must keep intraday and swing performance separately attributable.

## Accountable persona — Human CIO

A dedicated human Chief Investment Officer holds final accountability for
capital outcomes, production admission, and emergency control.

**Goals**

- Define the investment mandate and operating policy.
- Review return, drawdown, risk concentration, model drift, operational
  health, and incidents.
- Stop trading independently of AI control.
- Authorize restart after shutdown.
- Approve sandbox candidates for production promotion.

**Not expected**

- Approve each individual trade.
- Participate in routine agent discussions.
- Manually operate healthy trading workflows.

## Supporting future personas

These organizational roles are anticipated as the platform matures but are
not first-release requirements:

- **Quant researcher** — designs and validates strategies, features, and
  evaluation frameworks.
- **Risk officer** — independently reviews risk posture, limits, and
  incidents.
- **Portfolio manager** — oversees allocation across strategies and
  instruments.
- **Trading operations engineer** — maintains broker connectivity,
  execution health, and reconciliation.
- **Platform administrator** — manages infrastructure, secrets, deployments,
  and access.
- **Security / audit reviewer** — verifies controls, audit trails, and
  compliance.

## Governance model

```
Human CIO
├── Defines mandate
├── Approves production eligibility
├── Owns independent kill switch
└── Authorizes post-shutdown restart

Autonomous system
├── Researches approved strategy space
├── Operates production trades
├── Adjusts exposure and internal risk posture
├── Suspends unhealthy strategies
└── Produces complete audit evidence

Sandbox adaptation
├── Generates strategy / model / prompt / policy candidates
├── Runs backtests and shadow evaluation
└── Cannot self-promote to production
```
