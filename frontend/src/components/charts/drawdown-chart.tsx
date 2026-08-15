import { useEffect, useMemo, useRef, useState } from "react";

import { AreaSeries, type IChartApi, type ISeriesApi, createChart } from "lightweight-charts";

import { ChartCard } from "@/components/charts/chart-card";
import type { EquityPoint } from "@/data/fixtures";
import { useChartResize } from "@/hooks/useChartResize";
import { buildLwcOptions, getChartColors } from "@/lib/chart-theme";
import { equityToArea, equityToDrawdown } from "@/lib/chart-transform";

export interface DrawdownChartProps {
  equity: EquityPoint[];
  height?: number;
}

/**
 * Underwater drawdown pane — always ≤ 0, derived from the same equity
 * points as `EquityChart` so the two panes can never disagree.
 */
export function DrawdownChart({ equity, height = 240 }: DrawdownChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [chart, setChart] = useState<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const drawdown = useMemo(() => equityToDrawdown(equity), [equity]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const colors = getChartColors();
    const chartInstance = createChart(container, buildLwcOptions());
    const area = chartInstance.addSeries(AreaSeries, {
      lineColor: colors.down,
      topColor: `${colors.down}26`,
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
    if (!area || drawdown.length === 0) return;
    area.setData(equityToArea(drawdown));
  }, [drawdown]);

  return (
    <ChartCard title="Drawdown" description="Underwater curve · % below peak" height={height}>
      <div ref={containerRef} className="h-full w-full" />
    </ChartCard>
  );
}
