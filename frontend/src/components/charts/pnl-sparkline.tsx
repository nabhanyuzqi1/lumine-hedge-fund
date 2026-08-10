import { useEffect, useRef, useState } from 'react';

import { LineSeries, createChart, type IChartApi, type ISeriesApi } from 'lightweight-charts';

import { useChartResize } from '@/hooks/useChartResize';
import { buildLwcOptions, getChartColors } from '@/lib/chart-theme';
import { pnlToLine } from '@/lib/chart-transform';
import type { EquityPoint } from '@/data/fixtures';

export interface PnlSparklineProps {
  points: EquityPoint[];
}

/**
 * Live P&L sparkline — minimal line pane with axes hidden; sits inside a
 * compact ChartCard. Newest point is the running unrealized P&L.
 */
export function PnlSparkline({ points }: PnlSparklineProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [chart, setChart] = useState<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null);

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

  return <div ref={containerRef} className="h-full w-full" />;
}
