import { type RefObject, useEffect } from "react";

/**
 * Shared ResizeObserver wiring for chart panes. One observer per container;
 * calls `chart.resize(width, height)` from the measured container box
 * (lightweight-charts v5 requires explicit dimensions). Observers disconnect
 * on unmount / chart swap — this is the single resize path for every chart
 * in the dashboard.
 */
export interface ResizableChart {
  resize: (width: number, height: number) => void;
}

export function useChartResize<T extends ResizableChart>(
  chart: T | null,
  containerRef: RefObject<HTMLDivElement | null>
): void {
  useEffect(() => {
    if (!chart) return;
    const container = containerRef.current;
    if (!container || typeof ResizeObserver === "undefined") return;

    const observer = new ResizeObserver(() => {
      chart.resize(container.clientWidth, container.clientHeight);
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [chart, containerRef]);
}
