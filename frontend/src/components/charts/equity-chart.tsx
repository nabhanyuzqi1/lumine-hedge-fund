import { useEffect, useRef, useState } from "react";

import { AreaSeries, type IChartApi, type ISeriesApi, createChart } from "lightweight-charts";

import { ChartCard } from "@/components/charts/chart-card";
import type { EquityPoint } from "@/data/fixtures";
import { useChartResize } from "@/hooks/useChartResize";
import { buildLwcOptions, getChartColors } from "@/lib/chart-theme";
import { equityToArea } from "@/lib/chart-transform";

export interface EquityChartProps {
  points: EquityPoint[];
  height?: number;
  /** Fallback label saat belum ada data live. */
  waitingLabel?: string;
}

/**
 * Equity curve pane — area series in accent blue, fed by the portfolio
 * equity history (fixture until the backend equity endpoint lands).
 */
export function EquityChart({ points, height = 240, waitingLabel }: EquityChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [chart, setChart] = useState<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const colors = getChartColors();
    const chartInstance = createChart(container, buildLwcOptions());
    const area = chartInstance.addSeries(AreaSeries, {
      lineColor: colors.accent,
      topColor: `${colors.accent}33`,
      bottomColor: "transparent",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    seriesRef.current = area;
    setChart(chartInstance);

    return () => {
      chartInstance.remove();
      seriesRef.current = null;
    };
  }, []);

  useChartResize(chart, containerRef);

  useEffect(() => {
    const area = seriesRef.current;
    if (!area || points.length === 0) return;
    area.setData(equityToArea(points));
  }, [points]);

  return (
    <ChartCard title="Portfolio Equity" description="Daily equity curve · USD" height={height}>
      <div ref={containerRef} className="h-full w-full" />
      {points.length === 0 && waitingLabel && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="rounded-md border border-amber-500/30 bg-bg-base/80 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.2em] text-amber-400 backdrop-blur">
            {waitingLabel}
          </div>
        </div>
      )}
    </ChartCard>
  );
}