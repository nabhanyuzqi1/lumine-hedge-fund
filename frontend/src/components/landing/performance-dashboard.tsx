import { cn } from "@/lib/utils";
import { SIMULATED_METRICS } from "@/data/landing/performance";

/**
 * PerformanceDashboard — Section 14 of master prompt.
 * Shows realistic performance metrics with clear SIMULATED label.
 * Never fabricate real performance numbers.
 */

interface MetricCardProps {
  label: string;
  value: string | number;
  format?: "percent" | "number" | "ratio";
}

function MetricCard({ label, value, format = "number" }: MetricCardProps) {
  const formatValue = () => {
    if (format === "percent") {
      const num = typeof value === "number" ? value : parseFloat(value);
      const isNegative = num < 0;
      return (
        <span className={cn(isNegative ? "text-down" : "text-up")}>
          {num > 0 ? "+" : ""}
          {num.toFixed(1)}%
        </span>
      );
    }
    if (format === "ratio") {
      return <span className="text-ink">{value}</span>;
    }
    return <span className="text-ink">{value}</span>;
  };

  return (
    <div className="rounded-chip border border-line-soft bg-raised/30 px-4 py-3 backdrop-blur transition-colors hover:border-line hover:bg-raised/50">
      <div className="space-y-1">
        <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
          {label}
        </div>
        <div className="font-mono text-lg font-bold">{formatValue()}</div>
      </div>
    </div>
  );
}

interface PerformanceDashboardProps {
  className?: string;
}

export function PerformanceDashboard({ className }: PerformanceDashboardProps) {
  const metrics = SIMULATED_METRICS;

  return (
    <div className={cn("w-full max-w-4xl space-y-6", className)}>
      {/* Header */}
      <div className="space-y-3 text-center">
        <div className="flex items-center justify-center gap-2">
          <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
          <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
            Performance Analytics
          </span>
          <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
        </div>
        <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
          Performance Metrics
        </h3>
      </div>

      {/* Metrics grid */}
      <div className="rounded-panel border border-line bg-raised shadow-panel">
        <div className="space-y-4 p-6 md:p-8">
          {/* Primary metrics */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="Total Return"
              value={metrics.totalReturn}
              format="percent"
            />
            <MetricCard label="CAGR" value={metrics.cagr} format="percent" />
            <MetricCard
              label="Max Drawdown"
              value={metrics.maxDrawdown}
              format="percent"
            />
            <MetricCard
              label="Sharpe Ratio"
              value={metrics.sharpe.toFixed(2)}
              format="ratio"
            />
          </div>

          {/* Secondary metrics */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <MetricCard
              label="Sortino Ratio"
              value={metrics.sortino.toFixed(2)}
              format="ratio"
            />
            <MetricCard
              label="Profit Factor"
              value={metrics.profitFactor.toFixed(2)}
              format="ratio"
            />
            <MetricCard
              label="Win Rate"
              value={metrics.winRate}
              format="percent"
            />
          </div>

          {/* Tertiary metrics */}
          <div className="grid gap-3 sm:grid-cols-3">
            <MetricCard
              label="Expectancy (R)"
              value={metrics.expectancy.toFixed(2)}
              format="ratio"
            />
            <MetricCard
              label="Avg R Multiple"
              value={metrics.avgR.toFixed(2)}
              format="ratio"
            />
            <MetricCard
              label="Total Trades"
              value={metrics.totalTrades}
              format="number"
            />
          </div>
        </div>

        {/* Mode selector (visual only) */}
        <div className="border-t border-line-soft bg-abyss/50 p-4 md:p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
              Data Source
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                disabled
                className="rounded-chip border border-line-soft bg-raised/30 px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest text-ink-faint opacity-50 cursor-not-allowed"
              >
                Backtest
              </button>
              <button
                type="button"
                disabled
                className="rounded-chip border border-line-soft bg-raised/30 px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest text-ink-faint opacity-50 cursor-not-allowed"
              >
                Paper
              </button>
              <button
                type="button"
                disabled
                className="rounded-chip border border-line-soft bg-raised/30 px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest text-ink-faint opacity-50 cursor-not-allowed"
              >
                Live
              </button>
            </div>
          </div>
        </div>

        {/* SIMULATED label */}
        <div className="border-t border-warn/20 bg-warn/5 px-4 py-2 md:px-6">
          <span className="font-mono text-[9px] font-semibold uppercase tracking-widest text-warn">
            ILLUSTRATIVE / SIMULATED DATA
          </span>
        </div>
      </div>
    </div>
  );
}
