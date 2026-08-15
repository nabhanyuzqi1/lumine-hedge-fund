/**
 * Performance Indicator Widget
 *
 * Compact real-time display of FPS and memory usage in terminal header.
 * Color-coded by performance threshold state.
 */

import { cn } from "@/lib/utils";
import type { PerformanceStatus } from "@/hooks/usePerformanceMetrics";

interface PerformanceIndicatorProps {
  fps: number;
  memoryMB: number;
  status?: PerformanceStatus;
}

export function PerformanceIndicator({
  fps,
  memoryMB,
  status = "normal",
}: PerformanceIndicatorProps) {
  const isCritical = status === "critical";
  const isWarn = status === "warn";

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg px-2 py-1 text-xs font-mono",
        "border border-border-subtle bg-bg-raised",
        isCritical && "bg-red-500/10 border-red-500/30 text-red-400",
        isWarn && "bg-amber-500/10 border-amber-500/30 text-amber-400",
        !isCritical && !isWarn && "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
      )}
      aria-label={`Performance: ${fps} FPS, ${memoryMB} MB memory`}
      data-testid="performance-indicator"
    >
      <span className="tabular-nums">{fps}<span className="text-[10px] ml-0.5">fps</span></span>
      <span className="text-text-tertiary">|</span>
      <span className="tabular-nums">{memoryMB}<span className="text-[10px] ml-0.5">MB</span></span>
    </div>
  );
}
