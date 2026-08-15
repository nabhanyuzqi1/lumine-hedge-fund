import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { SIMULATED_METRICS } from "@/data/landing/performance";
import type { PerformanceMetrics } from "@/data/landing/performance";

/**
 * PerformanceDashboard — Section 23 of UI/UX Rebuild V2.
 * Interactive analytics laboratory: BACKTEST / PAPER tabs switch
 * metric sets; LIVE is disabled with COMING SOON. All data is
 * ILLUSTRATIVE and clearly labeled.
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
      return (
        <span className={cn(num < 0 ? "text-down" : "text-up")}>
          {num > 0 ? "+" : ""}
          {num.toFixed(1)}%
        </span>
      );
    }
    return <span className="text-ink">{value}</span>;
  };

  return (
    <motion.div
      className="rounded-chip border border-line-soft bg-raised/30 px-4 py-3 backdrop-blur transition-colors hover:border-line hover:bg-raised/50"
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.35 }}
    >
      <div className="space-y-1">
        <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
          {label}
        </div>
        <div className="font-mono text-lg font-bold">{formatValue()}</div>
      </div>
    </motion.div>
  );
}

type DataSource = "backtest" | "paper";

const PAPER_METRICS: PerformanceMetrics = {
  ...SIMULATED_METRICS,
  totalReturn: 12.8,
  cagr: 19.2,
  maxDrawdown: -6.1,
  sharpe: 1.62,
  sortino: 2.01,
  profitFactor: 1.94,
  winRate: 55.7,
  expectancy: 1.18,
  avgR: 1.5,
  totalTrades: 86,
};

interface PerformanceDashboardProps {
  className?: string;
  showHeader?: boolean;
}

export function PerformanceDashboard({ className, showHeader = true }: PerformanceDashboardProps) {
  const [source, setSource] = useState<DataSource>("backtest");
  const metrics = source === "backtest" ? SIMULATED_METRICS : PAPER_METRICS;

  return (
    <div className={cn("w-full max-w-4xl space-y-6", className)}>
      {showHeader && (
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
          <p className="mx-auto max-w-2xl text-sm leading-relaxed text-ink-dim">
            Illustrative analytics showing how Lumine evaluates strategy quality.
            Switch between backtest and paper views.
          </p>
        </div>
      )}

      <motion.div
        className="rounded-panel border border-line bg-raised shadow-panel"
        initial={{ opacity: 0, y: 28 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.7, ease: "easeOut" }}
      >
        <div className="space-y-4 p-6 md:p-8">
          {/* Mode selector */}
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
              Data Source
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setSource("backtest")}
                className={cn(
                  "rounded-chip border px-3.5 py-1.5 font-mono text-[10px] uppercase tracking-widest transition-all",
                  source === "backtest"
                    ? "border-accent bg-accent/15 text-accent"
                    : "border-line-soft bg-raised/30 text-ink-dim hover:text-ink"
                )}
              >
                Backtest
              </button>
              <button
                type="button"
                onClick={() => setSource("paper")}
                className={cn(
                  "rounded-chip border px-3.5 py-1.5 font-mono text-[10px] uppercase tracking-widest transition-all",
                  source === "paper"
                    ? "border-accent bg-accent/15 text-accent"
                    : "border-line-soft bg-raised/30 text-ink-dim hover:text-ink"
                )}
              >
                Paper
              </button>
              <button
                type="button"
                disabled
                className="cursor-not-allowed rounded-chip border border-line-soft bg-raised/30 px-3.5 py-1.5 font-mono text-[10px] uppercase tracking-widest text-ink-faint opacity-50"
                title="Coming soon"
              >
                Live · Coming Soon
              </button>
            </div>
          </div>

          {/* Metrics — animate on tab switch */}
          <AnimatePresence mode="wait">
            <motion.div
              key={source}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.3 }}
              className="space-y-4"
            >
              {/* Primary metrics */}
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <MetricCard label="CAGR" value={metrics.cagr} format="percent" />
                <MetricCard label="Max Drawdown" value={metrics.maxDrawdown} format="percent" />
                <MetricCard label="Sharpe Ratio" value={metrics.sharpe.toFixed(2)} format="ratio" />
              </div>

              {/* Secondary metrics */}
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <MetricCard label="Profit Factor" value={metrics.profitFactor.toFixed(2)} format="ratio" />
                <MetricCard label="Win Rate" value={metrics.winRate} format="percent" />
                <MetricCard label="Expectancy (R)" value={metrics.expectancy.toFixed(2)} format="ratio" />
              </div>
            </motion.div>
          </AnimatePresence>
        </div>

        {/* SIMULATED label */}
        <div className="border-t border-warn/20 bg-warn/5 px-4 py-2 md:px-6">
          <span className="font-mono text-[9px] font-semibold uppercase tracking-widest text-warn">
            ILLUSTRATIVE / SIMULATED DATA — NOT REAL PERFORMANCE
          </span>
        </div>
      </motion.div>
    </div>
  );
}
