import { useEffect, useRef, useState } from "react";

import { type IChartApi, type ISeriesApi, LineSeries, createChart } from "lightweight-charts";

import type { EquityPoint } from "@/data/fixtures";
import { useChartResize } from "@/hooks/useChartResize";
import { buildLwcOptions, getChartColors } from "@/lib/chart-theme";
import { pnlToLine } from "@/lib/chart-transform";

export interface PnlSparklineProps {
  points: EquityPoint[];
  /** Fallback label saat belum ada data live. */
  waitingLabel?: string;
}

/**
 * Live P&L sparkline — minimal line pane with axes hidden; sits inside a
 * compact ChartCard. Newest point is the running unrealized P&L.
 */
export function PnlSparkline({ points, waitingLabel }: PnlSparklineProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [chart, setChart] = useState<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const colors = getChartColors();
    const chartInstance = createChart(container, {
      ...buildLwcOptions(),
      timeScale: { visible: false },
      rightPriceScale: { visible: false },
    });
    const line = chartInstance.addSeries(LineSeries, {
      color: colors.accent,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    seriesRef.current = line;
    setChart(chartInstance);

    return () => {
      chartInstance.remove();
      seriesRef.current = null;
    };
  }, []);

  useChartResize(chart, containerRef);

  useEffect(() => {
    const line = seriesRef.current;
    if (!line || points.length === 0) return;
    line.setData(pnlToLine(points));
  }, [points]);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />
      {points.length === 0 && waitingLabel && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="rounded-md border border-amber-500/30 bg-bg-base/80 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.2em] text-amber-400 backdrop-blur">
            {waitingLabel}
          </div>
        </div>
      )}
    </div>
  );
}