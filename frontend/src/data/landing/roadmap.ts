/**
 * Lumine roadmap data for landing page.
 * Honest representation of development phases.
 */

export interface RoadmapPhase {
  phase: number;
  title: string;
  subtitle: string;
  description: string;
  status: "COMPLETE" | "IN_PROGRESS" | "PLANNED";
  milestones: string[];
}

export const ROADMAP: RoadmapPhase[] = [
  {
    phase: 1,
    title: "Research Intelligence",
    subtitle: "Multi-Agent Research & Strategy Discovery",
    description:
      "Foundation of the intelligence system: specialized agents for technical, macro, news, and market structure analysis.",
    status: "IN_PROGRESS",
    milestones: [
      "Multi-agent architecture",
      "Committee deliberation system",
      "Strategy hypothesis generation",
      "Research documentation",
    ],
  },
  {
    phase: 2,
    title: "Simulation",
    subtitle: "Backtesting, Walk-Forward Validation & Paper Trading",
    description:
      "Rigorous validation framework: historical testing, out-of-sample validation, and real-time paper trading.",
    status: "IN_PROGRESS",
    milestones: [
      "Historical backtesting engine",
      "Walk-forward analysis",
      "Out-of-sample testing",
      "Paper trading environment",
      "Monte Carlo simulation",
    ],
  },
  {
    phase: 3,
    title: "Controlled Execution",
    subtitle: "Real-Time Systematic Execution Under Risk Controls",
    description:
      "Production execution with deterministic risk gates: position sizing, exposure limits, and kill-switch protection.",
    status: "PLANNED",
    milestones: [
      "MT5 execution bridge",
      "Deterministic risk engine",
      "Position sizing automation",
      "Kill-switch implementation",
      "Transaction cost analysis",
    ],
  },
  {
    phase: 4,
    title: "Portfolio Intelligence",
    subtitle: "Multi-Strategy & Multi-Asset Allocation",
    description:
      "Portfolio-level optimization: strategy allocation, correlation management, and dynamic capital deployment.",
    status: "PLANNED",
    milestones: [
      "Multi-strategy orchestration",
      "Correlation-aware allocation",
      "Portfolio risk management",
      "Dynamic rebalancing",
      "Strategy performance attribution",
    ],
  },
  {
    phase: 5,
    title: "Institutional Infrastructure",
    subtitle: "Scalable Quantitative Investment Platform",
    description:
      "Enterprise-grade infrastructure: distributed execution, advanced analytics, and institutional compliance.",
    status: "PLANNED",
    milestones: [
      "Distributed execution system",
      "Advanced portfolio analytics",
      "Institutional reporting",
      "Compliance framework",
      "API for external integration",
    ],
  },
];
