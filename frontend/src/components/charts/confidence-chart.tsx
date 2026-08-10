import { useMemo } from 'react';

import type { EChartsCoreOption } from 'echarts/core';

import { ChartCard } from '@/components/charts/chart-card';
import { useEcharts } from '@/hooks/useEcharts';
import { CHART_COLORS } from '@/lib/chart-theme';
import { confidenceToEcharts } from '@/lib/chart-transform';
import type { SignalPoint } from '@/data/fixtures';

export interface ConfidenceChartProps {
  points: SignalPoint[];
  height?: number;
}

const ANALYST_COLORS = [CHART_COLORS.accent, CHART_COLORS.cyan, CHART_COLORS.warn, CHART_COLORS.up];

/**
 * AI committee confidence timeline (ECharts) — one line per analyst, y in
 * [0, 1]. Reads analyst-output stream data via the signals hook.
 */
export function ConfidenceChart({ points, height = 320 }: ConfidenceChartProps) {
  const option = useMemo<EChartsCoreOption>(() => {
    const { series } = confidenceToEcharts(points);
    return {
      grid: { left: 40, right: 12, top: 32, bottom: 28 },
      legend: {
        top: 0,
        itemWidth: 10,
        itemHeight: 10,
        textStyle: { color: CHART_COLORS.text },
      },
      xAxis: { type: 'time', axisLabel: { hideOverlap: true } },
      yAxis: { type: 'value', min: 0, max: 1 },
      series: series.map((line, index) => ({
        name: line.name,
        type: 'line',
        data: line.data,
        smooth: false,
        symbol: 'none',
        lineWidth: 2,
        itemStyle: { color: ANALYST_COLORS[index % ANALYST_COLORS.length] },
      })),
    };
  }, [points]);

  const containerRef = useEcharts(option);

  return (
    <ChartCard
      title="AI Committee Confidence"
      description="Per-analyst conviction · 0–1"
      height={height}
    >
      <div ref={containerRef} className="h-full w-full" />
    </ChartCard>
  );
}
