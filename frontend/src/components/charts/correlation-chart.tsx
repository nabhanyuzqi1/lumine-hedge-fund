import { useMemo } from 'react';

import type { EChartsCoreOption } from 'echarts/core';

import { ChartCard } from '@/components/charts/chart-card';
import { useEcharts } from '@/hooks/useEcharts';
import { correlationToHeatmap } from '@/lib/chart-transform';
import type { CorrelationMatrix } from '@/data/fixtures';

export interface CorrelationChartProps {
  symbols: string[];
  matrix: CorrelationMatrix;
  height?: number;
}

/**
 * Cross-asset correlation heatmap (ECharts) — diverging scale: red negative,
 * dark near zero, green positive. Backend correlation endpoint is not in the
 * Phase 9 contract yet, so data comes from deterministic fixtures.
 */
export function CorrelationChart({ symbols, matrix, height = 320 }: CorrelationChartProps) {
  const option = useMemo<EChartsCoreOption>(() => {
    const { data, labels } = correlationToHeatmap(symbols, matrix);
    return {
      tooltip: {
        formatter: (params: { data: [number, number, number] }) => {
          const [i, j, value] = params.data;
          return `${labels[i]} × ${labels[j]}: ${value.toFixed(2)}`;
        },
      },
      grid: { left: 56, right: 12, top: 8, bottom: 48 },
      xAxis: { type: 'category', data: labels, axisLabel: { rotate: 30 } },
      yAxis: { type: 'category', data: labels },
      visualMap: {
        min: -1,
        max: 1,
        calculable: false,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        itemWidth: 10,
        itemHeight: 90,
        inRange: { color: ['#f0555b', '#0f1522', '#34d399'] },
      },
      series: [
        {
          type: 'heatmap',
          data,
          emphasis: { itemStyle: { borderColor: '#e8eef7', borderWidth: 1 } },
        },
      ],
    };
  }, [symbols, matrix]);

  const containerRef = useEcharts(option);

  return (
    <ChartCard title="Cross-Asset Correlation" description="Rolling 30d · Pearson" height={height}>
      <div ref={containerRef} className="h-full w-full" />
    </ChartCard>
  );
}
