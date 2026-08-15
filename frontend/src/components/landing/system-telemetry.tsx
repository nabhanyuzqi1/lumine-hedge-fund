import { cn } from "@/lib/utils";

/**
 * SystemTelemetry — Hero section system status overlay.
 * Shows live-looking system status, markets, and engine stats.
 * All data is SIMULATED and clearly labeled.
 */

interface SystemTelemetryProps {
  className?: string;
}

export function SystemTelemetry({ className }: SystemTelemetryProps) {
  return (
    <div
      className={cn(
        "absolute inset-0 pointer-events-none select-none overflow-hidden",
        className
      )}
    >
      {/* Top-left: System status */}
      <div className="absolute left-6 top-6 pointer-events-auto">
        <div className="flex items-center gap-2 rounded-chip border border-line-soft bg-abyss/90 px-3 py-1.5 backdrop-blur">
          <div className="h-1.5 w-1.5 rounded-full bg-up animate-pulse" />
          <span className="font-mono text-[10px] uppercase tracking-widest text-ink-dim">
            System Online
          </span>
        </div>
      </div>

      {/* Top-right: Mode indicator */}
      <div className="absolute right-6 top-6 pointer-events-auto">
        <div className="flex items-center gap-2 rounded-chip border border-line-soft bg-abyss/90 px-3 py-1.5 backdrop-blur">
          <span className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
            Mode
          </span>
          <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-accent">
            Research
          </span>
        </div>
      </div>

      {/* Bottom-left: Engine stats */}
      <div className="absolute bottom-6 left-6 pointer-events-auto">
        <div className="space-y-1.5 rounded-chip border border-line-soft bg-abyss/90 px-3 py-2 backdrop-blur">
          <div className="font-mono text-[9px] uppercase tracking-widest text-ink-faint">
            Engine
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1">
            <div className="font-mono text-[10px] text-ink-dim">Agents</div>
            <div className="font-mono text-[10px] font-semibold text-ink">4</div>
            <div className="font-mono text-[10px] text-ink-dim">Markets</div>
            <div className="font-mono text-[10px] font-semibold text-ink">8</div>
            <div className="font-mono text-[10px] text-ink-dim">Latency</div>
            <div className="font-mono text-[10px] font-semibold text-accent">
              &lt;120ms
            </div>
          </div>
        </div>
      </div>

      {/* Bottom-right: SIMULATED label */}
      <div className="absolute bottom-6 right-6 pointer-events-auto">
        <div className="rounded-chip border border-warn/30 bg-warn/10 px-3 py-1.5 backdrop-blur">
          <span className="font-mono text-[9px] font-semibold uppercase tracking-widest text-warn">
            Simulated Environment
          </span>
        </div>
      </div>
    </div>
  );
}
