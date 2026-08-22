import { Suspense, lazy, useState } from "react";

import { useCorrelation, useEquityCurve, useExposure, useMarketBars, useSignals } from "@/api/hooks";
import { useMarketWS } from "@/hooks/useMarketWS";
import { useMarketStore } from "@/stores";
import { MarketIndicatorsPanel } from "@/components/dashboard/market-indicators-panel";
import { ResearchWorkspaceSwitcher } from "@/components/research/workspace-switcher";
import { SignalPanel } from "@/components/dashboard/signal-panel";
import { ExposureSummaryCard } from "@/components/dashboard/exposure-summary-card";
import { DecisionCard } from "@/components/dashboard/decision-card";
import { CandlestickChart, type Timeframe } from "@/components/charts/candlestick-chart";
import { ChartCard } from "@/components/charts/chart-card";
import { DrawdownChart } from "@/components/charts/drawdown-chart";
import { EquityChart } from "@/components/charts/equity-chart";
import { PnlSparkline } from "@/components/charts/pnl-sparkline";
import { cn } from "@/lib/utils";

// ECharts panes are code-split: `echarts/core` never enters the critical
// bundle. Each lazy pane keeps the <300KB gzip budget.
const LazyAllocation = lazy(() =>
  import("@/components/charts/allocation-chart").then((m) => ({ default: m.AllocationChart }))
);
const LazyCorrelation = lazy(() =>
  import("@/components/charts/correlation-chart").then((m) => ({ default: m.CorrelationChart }))
);
const LazyConfidence = lazy(() =>
  import("@/components/charts/confidence-chart").then((m) => ({ default: m.ConfidenceChart }))
);

function PaneFallback({ title, height = 320 }: { title: string; height?: number }) {
  return (
    <ChartCard title={title} description="Loading pane…" height={height}>
      <div className="h-full w-full animate-pulse rounded bg-bg-overlay" />
    </ChartCard>
  );
}

/**
 * `/dashboard` — institutional chart grid (F-Sprint 4). Lightweight-charts
 * panes are statically imported; ECharts panes load lazily. All data flows
 * from live REST endpoints (market bars, equity, exposure, signals,
 * correlation) — no demo streams. WS tick (18 Aug 2026) → chart live
 * mutasi bar + label "Waiting for live data" HANYA saat benar-benar stale
 * (sebelumnya tanpa lastTick → isStale selalu true → label selalu muncul).
 */
export function DashboardPage() {
const [timeframe, setTimeframe] = useState<Timeframe>("5m");
const [book, setBook] = useState<"real" | "paper">("real");

const bars = useMarketBars("XAUUSD", timeframe);
const equity = useEquityCurve("default", book);
  const exposure = useExposure();
  const signals = useSignals("XAUUSD");
  const correlation = useCorrelation();

  // WS tick → store → lastTick (sama dengan terminal). Tanpa ini chart
  // dashboard BEKU & label stale selalu tampil (isStale butuh lastTick).
  const upsertTick = useMarketStore((state) => state.upsertTick);
  useMarketWS({
    symbol: "XAUUSD",
    enabled: true,
    onTick: (tick) => upsertTick(tick),
  });
  const lastTick = useMarketStore((s) => s.ticks["XAUUSD"] ?? null);

  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-3 p-4">
      {/* Bloomberg-style section header */}
                  <div className="flex items-center gap-3 border-b border-border-subtle pb-2">
                    <span className="font-mono text-[11px] uppercase tracking-widest text-text-muted">RESEARCH</span>
                    <span className="h-px flex-1 bg-border-subtle/40" aria-hidden="true" />
                    <span className="font-mono text-[11px] text-text-secondary">XAUUSD · MULTI-FRAME</span>
                    {/* Per-akun selector: REAL (MT5 live) vs PAPER (seed $10k) */}
                    <button
                      onClick={() => setBook("real")}
                      className={cn(
                        "rounded-chip px-2 py-0.5 text-[10px] font-medium",
                        book === "real" ? "bg-accent/10 text-accent" : "text-ink-faint hover:text-ink"
                      )}
                    >
                      REAL
                    </button>
                    <button
                      onClick={() => setBook("paper")}
                      className={cn(
                        "rounded-chip px-2 py-0.5 text-[10px] font-medium",
                        book === "paper" ? "bg-amber/10 text-amber" : "text-ink-faint hover:text-ink"
                      )}
                    >
                      PAPER
                    </button>
                  </div>

            {/* Workspace Switcher: tab antar Dashboard (portfolio) & Research (paper vs real) */}
                  <ResearchWorkspaceSwitcher />

      {/* Grid scroll alami halaman (bukan bounded per group — user request);
          hanya tabel individu yang dibatasi (signal panel max-h). */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              <div className="md:col-span-2 xl:col-span-3">
                <CandlestickChart
                  bars={bars.data ?? []}
                  lastTick={lastTick}
                  timeframe={timeframe}
                  onTimeframeChange={setTimeframe}
                  height={420}
                />
              </div>

              <EquityChart points={equity.data ?? []} waitingLabel="Waiting for live data" />
              <DrawdownChart equity={equity.data ?? []} />

        <ChartCard title="Live P&L" description="Equity curve · USD" height={96}>
                  <PnlSparkline points={equity.data ?? []} waitingLabel="Waiting for live data" />
                </ChartCard>

        <Suspense fallback={<PaneFallback title="Capital Allocation" />}>
          <LazyAllocation items={exposure.data ?? []} />
        </Suspense>

        <Suspense fallback={<PaneFallback title="Cross-Asset Correlation" />}>
          <LazyCorrelation
            symbols={correlation.data?.symbols ?? []}
            matrix={correlation.data?.matrix ?? []}
          />
        </Suspense>

        <Suspense fallback={<PaneFallback title="AI Committee Confidence" />}>
          <LazyConfidence points={signals.data ?? []} />
        </Suspense>

        <MarketIndicatorsPanel symbol="XAUUSD" />
        <SignalPanel symbol="XAUUSD" />
        <ExposureSummaryCard />

        <DecisionCard
          decision={{
            action: (signals.data?.[0]?.direction as "buy" | "sell" | "hold") ?? "hold",
            confidence: signals.data?.[0]?.confidence ?? 0.5,
            timestamp: new Date().toISOString(),
            rationale: `Live /market/signals · ${signals.data?.length ?? 0} signal(s)`,
          }}
        />
      </div>
    </div>
  );
}
