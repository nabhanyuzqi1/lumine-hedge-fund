import { type RefObject, useEffect, useRef } from "react";

import { HeatmapChart, LineChart, TreemapChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import type { EChartsCoreOption } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

import { buildEchartsTheme } from "@/lib/chart-theme";

// Register once per bundle — this module is only imported from lazily-loaded
// chart panes, so ECharts never enters the critical bundle.
echarts.use([
  TreemapChart,
  HeatmapChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

/**
 * Shared ECharts lifecycle: init with the Lumine theme, apply options on
 * change (notMerge), ResizeObserver → `chart.resize()`, dispose on unmount.
 * Returns the container ref for the pane's root div.
 */
export function useEcharts(option: EChartsCoreOption | null): RefObject<HTMLDivElement | null> {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = echarts.init(container, buildEchartsTheme());
    chartRef.current = chart;

    let observer: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(() => chart.resize());
      observer.observe(container);
    }

    return () => {
      observer?.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (option && chartRef.current) {
      chartRef.current.setOption(option, true);
    }
  }, [option]);

  return containerRef;
}
