import { Suspense, lazy, useState } from "react";

import {
  useCorrelation,
  useEquityCurve,
  useExposure,
  useMarketBars,
  useSignals,
} from "@/api/hooks";
import { CandlestickChart, type Timeframe } from "@/components/charts/candlestick-chart";
import { ChartCard } from "@/components/charts/chart-card";
import { DrawdownChart } from "@/components/charts/drawdown-chart";
import { EquityChart } from "@/components/charts/equity-chart";
import { PnlSparkline } from "@/components/charts/pnl-sparkline";
import { useDemoStreams } from "@/hooks/useDemoStreams";

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
 * panes are statically imported; ECharts panes load lazily. Market data flows
 * from the demo stream hook until the backend SSE endpoints are live.
 */
export function DashboardPage() {
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");

  const bars = useMarketBars("XAUUSD", timeframe);
  const equity = useEquityCurve();
  const exposure = useExposure();
  const signals = useSignals("XAUUSD");
  const correlation = useCorrelation();
  const demo = useDemoStreams(true, "XAUUSD");

  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-4 p-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Dashboard</h1>
          <p className="text-sm text-text-muted">
            Institutional overview · XAUUSD live demo stream
          </p>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <div className="md:col-span-2 xl:col-span-3">
          <CandlestickChart
            bars={bars.data ?? []}
            lastTick={demo.lastTick}
            timeframe={timeframe}
            onTimeframeChange={setTimeframe}
          />
        </div>

        <EquityChart points={equity.data ?? []} />
        <DrawdownChart equity={equity.data ?? []} />

        <ChartCard title="Live P&L" description="Unrealized · USD" height={96}>
          <PnlSparkline points={demo.pnlSeries} />
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
      </div>
    </div>
  );
}
