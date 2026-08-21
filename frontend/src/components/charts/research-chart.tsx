import { useEffect, useRef, useState } from "react";

import { type IChartApi, type ISeriesApi, LineSeries, createChart } from "lightweight-charts";

import { ChartCard } from "@/components/charts/chart-card";
import { useChartResize } from "@/hooks/useChartResize";
import { buildLwcOptions, getChartColors } from "@/lib/chart-theme";

export interface SeriesPoint {
  ts: string;
  pnl: number;
}

export interface ResearchChartProps {
  paper: SeriesPoint[];
  real: SeriesPoint[];
  height?: number;
  waitingLabel?: string;
}

function toLwcData(series: SeriesPoint[]): { time: string; value: number }[] {
  return series.map((p) => ({
    time: p.ts.slice(0, 10).replace(/-/g, "-"),
    value: p.pnl,
  }));
}

/**
 * Research P&L chart — 2 line series (paper amber, real accent) stacked
 * on the same pane, fed by /research/series endpoint.
 */
export function ResearchChart({
  paper,
  real,
  height = 240,
  waitingLabel,
}: ResearchChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [chart, setChart] = useState<IChartApi | null>(null);
  const paperSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const realSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const colors = getChartColors();
    const chartInstance = createChart(container, buildLwcOptions());
    const paperLine = chartInstance.addSeries(LineSeries, {
      color: "#f59e0b",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      title: "Paper (sandbox)",
    });
    const realLine = chartInstance.addSeries(LineSeries, {
      color: colors.accent,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      title: "Real (MT5 live)",
    });
    paperSeriesRef.current = paperLine;
    realSeriesRef.current = realLine;
    setChart(chartInstance);

    return () => {
      chartInstance.remove();
      paperSeriesRef.current = null;
      realSeriesRef.current = null;
    };
  }, []);

  useChartResize(chart, containerRef);

  useEffect(() => {
    const paperLine = paperSeriesRef.current;
    const realLine = realSeriesRef.current;
    if (!paperLine || !realLine) return;
    if (paper.length > 0) paperLine.setData(toLwcData(paper));
    if (real.length > 0) realLine.setData(toLwcData(real));
  }, [paper, real]);

  return (
    <ChartCard
      title="P&L Kumulatif — Paper vs Real"
      description="Closed positions · USD"
      height={height}
    >
      <div ref={containerRef} className="h-full w-full" />
      {paper.length === 0 && real.length === 0 && waitingLabel && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="rounded-md border border-amber-500/30 bg-bg-base/80 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.2em] text-amber-400 backdrop-blur">
            {waitingLabel}
          </div>
        </div>
      )}
    </ChartCard>
  );
}