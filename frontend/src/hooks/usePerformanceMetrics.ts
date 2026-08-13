/**
 * Performance Metrics Hook
 *
 * Provides reactive performance state for components, updating at 250ms intervals.
 * Memoized selectors prevent unnecessary re-renders.
 */

import { useEffect, useMemo, useState } from "react";
import { metricsCollector, METRIC_THRESHOLDS, type VitalsSnapshot, type PerformanceStatus } from "@/lib/metrics";

export type { PerformanceStatus };

export type PerformanceState = {
  fps: number;
  memoryMB: number;
  vitals: VitalsSnapshot;
  longTaskCount: number;
  renderHealth: { avgFps: number; framesDropped: number };
  performanceStatus: PerformanceStatus;
  memoryStatus: "normal" | "warn";
};

interface UsePerformanceMetricsOptions {
  updateIntervalMs?: number;
  enabled?: boolean;
}

export function usePerformanceMetrics(
  options: UsePerformanceMetricsOptions = {}
): PerformanceState {
  const { updateIntervalMs = 250, enabled = true } = options;
  const [state, setState] = useState<PerformanceState>({
    fps: 60,
    memoryMB: 0,
    vitals: { fcp: null, lcp: null, tti: null },
    longTaskCount: 0,
    renderHealth: { avgFps: 60, framesDropped: 0 },
    performanceStatus: "normal",
    memoryStatus: "normal",
  });

  useEffect(() => {
    if (!enabled) return;

    // Initialize metrics collection on mount
    metricsCollector.init();

    let rafId: number | null = null;
    let intervalId: NodeJS.Timeout | null = null;

    const updateState = () => {
      const lastEntry = metricsCollector.getLastEntry();
      const vitals = metricsCollector.getVitalsSnapshot();
      const memory = metricsCollector.getMemoryReport();
      const renderHealth = metricsCollector.getRenderHealth();

      setState((prev) => ({
        ...prev,
        fps: lastEntry?.fps ?? prev.fps,
        memoryMB: memory.usedMB,
        vitals: {
          fcp: vitals.fcp ?? prev.vitals.fcp,
          lcp: vitals.lcp ?? prev.vitals.lcp,
          tti: vitals.tti ?? prev.vitals.tti,
        },
        longTaskCount: renderHealth.longTaskCount,
        renderHealth: {
          avgFps: renderHealth.avgFps,
          framesDropped: renderHealth.framesDropped,
        },
      }));
    };

    // Initial capture
    updateState();

    // Continuous updates
    intervalId = setInterval(updateState, updateIntervalMs);

    // Cleanup
    return () => {
      if (intervalId !== null) clearInterval(intervalId);
      if (rafId !== null) cancelAnimationFrame(rafId);
      metricsCollector.dispose();
    };
  }, [enabled, updateIntervalMs]);

  // Derived thresholds and alerts
  const performanceStatus = useMemo(() => {
    if (state.fps < METRIC_THRESHOLDS.FPS_WARN) {
      return "critical" as const;
    } else if (state.fps < METRIC_THRESHOLDS.FPS_NORMAL) {
      return "warn" as const;
    }
    return "normal" as const;
  }, [state.fps]);

  const memoryStatus = useMemo(() => {
    if (state.memoryMB > METRIC_THRESHOLDS.MEMORY_WARN_MB) {
      return "warn" as const;
    }
    return "normal" as const;
  }, [state.memoryMB]);

  return {
    fps: state.fps,
    memoryMB: state.memoryMB,
    vitals: state.vitals,
    longTaskCount: state.longTaskCount,
    renderHealth: state.renderHealth,
    performanceStatus,
    memoryStatus,
  };
}
