import { useMemo } from "react";

import type { EChartsCoreOption } from "echarts/core";

import { ChartCard } from "@/components/charts/chart-card";
import type { ExposureItem } from "@/data/fixtures";
import { useEcharts } from "@/hooks/useEcharts";
import { exposureToTreemap } from "@/lib/chart-transform";

export interface AllocationChartProps {
  items: ExposureItem[];
  height?: number;
}

/**
 * Capital allocation treemap (ECharts) — one top-level node per asset class,
 * children per symbol. Lazily loaded; only mounted while the dashboard grid
 * shows it.
 */
export function AllocationChart({ items, height = 320 }: AllocationChartProps) {
  const option = useMemo<EChartsCoreOption>(
    () => ({
      tooltip: {
        formatter: (info: { name: string; value: number }) =>
          `${info.name}<br/>${(info.value * 100).toFixed(1)}%`,
      },
      series: [
        {
          type: "treemap",
          data: exposureToTreemap(items),
          roam: false,
          nodeClick: false,
          breadcrumb: { show: false },
          label: {
            show: true,
            formatter: "{b}\n{c}%",
            fontSize: 11,
          },
          itemStyle: {
            borderColor: "#0b0f17",
            borderWidth: 2,
            gapWidth: 2,
          },
          levels: [
            {
              itemStyle: { borderWidth: 4, gapWidth: 4 },
              upperLabel: { show: false },
            },
          ],
        },
      ],
    }),
    [items]
  );

  const containerRef = useEcharts(option);

  return (
    <ChartCard title="Capital Allocation" description="Exposure by asset class · %" height={height}>
      <div ref={containerRef} className="h-full w-full" />
    </ChartCard>
  );
}
