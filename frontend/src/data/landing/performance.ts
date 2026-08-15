/**
 * Performance analytics data for landing page.
 * SIMULATED DATA — clearly labeled, not real trading results.
 */

export interface PerformanceMetrics {
  totalReturn: number;
  cagr: number;
  maxDrawdown: number;
  sharpe: number;
  sortino: number;
  profitFactor: number;
  winRate: number;
  expectancy: number;
  avgR: number;
  totalTrades: number;
}

export interface EquityPoint {
  date: string;
  equity: number;
  drawdown: number;
}

export const SIMULATED_METRICS: PerformanceMetrics = {
  totalReturn: 34.2,
  cagr: 28.5,
  maxDrawdown: -12.4,
  sharpe: 1.85,
  sortino: 2.34,
  profitFactor: 2.12,
  winRate: 58.3,
  expectancy: 1.42,
  avgR: 1.8,
  totalTrades: 247,
};

/**
 * Realistic equity curve with drawdowns and recovery periods.
 * Not a straight line — includes realistic volatility.
 */
export const SIMULATED_EQUITY_CURVE: EquityPoint[] = [
  { date: "2025-01", equity: 100000, drawdown: 0 },
  { date: "2025-02", equity: 102400, drawdown: 0 },
  { date: "2025-03", equity: 104100, drawdown: 0 },
  { date: "2025-04", equity: 101800, drawdown: -2.2 },
  { date: "2025-05", equity: 103500, drawdown: 0 },
  { date: "2025-06", equity: 106200, drawdown: 0 },
  { date: "2025-07", equity: 108900, drawdown: 0 },
  { date: "2025-08", equity: 106700, drawdown: -2.0 },
  { date: "2025-09", equity: 110200, drawdown: 0 },
  { date: "2025-10", equity: 113400, drawdown: 0 },
  { date: "2025-11", equity: 111200, drawdown: -1.9 },
  { date: "2025-12", equity: 115800, drawdown: 0 },
  { date: "2026-01", equity: 119300, drawdown: 0 },
  { date: "2026-02", equity: 117100, drawdown: -1.8 },
  { date: "2026-03", equity: 121600, drawdown: 0 },
  { date: "2026-04", equity: 124900, drawdown: 0 },
  { date: "2026-05", equity: 128400, drawdown: 0 },
  { date: "2026-06", equity: 125700, drawdown: -2.1 },
  { date: "2026-07", equity: 130200, drawdown: 0 },
  { date: "2026-08", equity: 134200, drawdown: 0 },
];

export interface RegimeIndicator {
  regime: string;
  strength: number;
  description: string;
}

export const MARKET_REGIME: RegimeIndicator[] = [
  { regime: "TRENDING", strength: 85, description: "Strong directional bias" },
  { regime: "RANGING", strength: 25, description: "Consolidation phase" },
  { regime: "HIGH VOL", strength: 60, description: "Elevated volatility" },
  { regime: "LOW VOL", strength: 40, description: "Compressed ranges" },
  { regime: "RISK-ON", strength: 70, description: "Risk appetite elevated" },
  { regime: "NEWS RISK", strength: 35, description: "Event-driven environment" },
];
