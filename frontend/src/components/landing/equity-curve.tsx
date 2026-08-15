import { motion } from "framer-motion";
import { useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { SIMULATED_EQUITY_CURVE } from "@/data/landing/performance";

/**
 * EquityCurve — Section 15 of master prompt.
 * Shows realistic equity curve with drawdowns and recovery.
 * Not a straight upward line — includes realistic volatility.
 */

interface EquityCurveProps {
  className?: string;
  showHeader?: boolean;
}

export function EquityCurve({ className, showHeader = true }: EquityCurveProps) {
  const data = SIMULATED_EQUITY_CURVE;
  const chartRef = useRef<HTMLDivElement>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const handleMove = (e: React.MouseEvent) => {
    const el = chartRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const ratio = (e.clientX - r.left) / r.width;
    const index = Math.round(ratio * (data.length - 1));
    setHoverIndex(Math.max(0, Math.min(data.length - 1, index)));
  };

  const hoverPoint = hoverIndex !== null ? data[hoverIndex] : null;

  // Calculate SVG path and dimensions
  const { path, minEquity, maxEquity, width, height } = useMemo(() => {
    const w = 800;
    const h = 300;
    const padding = 40;

    const equityValues = data.map((d) => d.equity);
    const min = Math.min(...equityValues);
    const max = Math.max(...equityValues);

    const xScale = (i: number) => padding + (i / (data.length - 1)) * (w - 2 * padding);
    const yScale = (equity: number) =>
      h - padding - ((equity - min) / (max - min)) * (h - 2 * padding);

    const pathData = data
      .map((d, i) => {
        const x = xScale(i);
        const y = yScale(d.equity);
        return i === 0 ? `M ${x} ${y}` : `L ${x} ${y}`;
      })
      .join(" ");

    return {
      path: pathData,
      minEquity: min,
      maxEquity: max,
      width: w,
      height: h,
    };
  }, [data]);

  // Format currency
  const formatCurrency = (value: number) => {
    return `$${(value / 1000).toFixed(0)}k`;
  };

  return (
    <div className={cn("w-full max-w-4xl space-y-6", className)}>
      {/* Header */}
      {showHeader && (
        <div className="space-y-3 text-center">
          <div className="flex items-center justify-center gap-2">
            <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
              Equity Curve
            </span>
            <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
          </div>
          <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
            Simulated Equity Growth
          </h3>
          <p className="mx-auto max-w-2xl text-sm leading-relaxed text-ink-dim">
            Realistic equity curve showing drawdowns, recovery periods, and sideways
            consolidation. Not a perfect upward line.
          </p>
        </div>
      )}

      {/* Chart */}
      <motion.div
        className="rounded-panel border border-line bg-raised shadow-panel"
        initial={{ opacity: 0, y: 28 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.7, ease: "easeOut" }}
      >
        <div className="p-6 md:p-8">
          <div className="overflow-x-auto">
            <div
              ref={chartRef}
              className="relative"
              onMouseMove={handleMove}
              onMouseLeave={() => setHoverIndex(null)}
            >
              <svg
                viewBox={`0 0 ${width} ${height}`}
                className="w-full"
                style={{ minWidth: "600px" }}
              >
              {/* Grid lines */}
              <defs>
                <pattern
                  id="grid"
                  width="40"
                  height="40"
                  patternUnits="userSpaceOnUse"
                >
                  <path
                    d="M 40 0 L 0 0 0 40"
                    fill="none"
                    stroke="rgba(28, 37, 52, 0.3)"
                    strokeWidth="0.5"
                  />
                </pattern>
              </defs>
              <rect width={width} height={height} fill="url(#grid)" />

              {/* Equity curve */}
              <motion.path
                d={path}
                fill="none"
                stroke="url(#equity-gradient)"
                strokeWidth="3"
                strokeLinecap="round"
                strokeLinejoin="round"
                initial={{ pathLength: 0, opacity: 0 }}
                whileInView={{ pathLength: 1, opacity: 1 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ duration: 1.8, ease: "easeInOut", delay: 0.3 }}
              />

              {/* Gradient definition */}
              <defs>
                <linearGradient id="equity-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#4d8dff" stopOpacity="0.8" />
                  <stop offset="100%" stopColor="#34d399" stopOpacity="0.9" />
                </linearGradient>
              </defs>

              {/* Y-axis labels */}
              <text
                x="10"
                y="50"
                fontSize="10"
                fill="#6d7c92"
                fontFamily="IBM Plex Mono, monospace"
              >
                {formatCurrency(maxEquity)}
              </text>
              <text
                x="10"
                y={height - 30}
                fontSize="10"
                fill="#6d7c92"
                fontFamily="IBM Plex Mono, monospace"
              >
                {formatCurrency(minEquity)}
              </text>

              {/* X-axis labels (first, middle, last) */}
              <text
                x="40"
                y={height - 10}
                fontSize="9"
                fill="#6d7c92"
                fontFamily="IBM Plex Mono, monospace"
              >
                {data[0].date}
              </text>
              <text
                x={width / 2 - 20}
                y={height - 10}
                fontSize="9"
                fill="#6d7c92"
                fontFamily="IBM Plex Mono, monospace"
              >
                {data[Math.floor(data.length / 2)].date}
              </text>
              <text
                x={width - 80}
                y={height - 10}
                fontSize="9"
                fill="#6d7c92"
                fontFamily="IBM Plex Mono, monospace"
              >
                {data[data.length - 1].date}
              </text>
              </svg>

              {/* Hover tooltip */}
              {hoverPoint && hoverIndex !== null && (
                <div
                  className="pointer-events-none absolute top-2 z-10 -translate-x-1/2 rounded-chip border border-line bg-abyss/95 px-3 py-2 backdrop-blur"
                  style={{
                    left: `${(hoverIndex / (data.length - 1)) * 100}%`,
                  }}
                >
                  <div className="font-mono text-[9px] uppercase tracking-widest text-ink-faint">
                    {hoverPoint.date}
                  </div>
                  <div className="mt-1 font-mono text-xs font-bold text-ink">
                    ${hoverPoint.equity.toLocaleString()}
                  </div>
                  <div
                    className={cn(
                      "font-mono text-[10px] font-semibold",
                      hoverPoint.drawdown < 0 ? "text-down" : "text-up"
                    )}
                  >
                    DD {hoverPoint.drawdown.toFixed(1)}%
                  </div>
                </div>
              )}

              {/* Hover guide line */}
              {hoverIndex !== null && (
                <div
                  className="pointer-events-none absolute inset-y-2 w-px bg-accent/40"
                  style={{
                    left: `${(hoverIndex / (data.length - 1)) * 100}%`,
                  }}
                />
              )}
            </div>
          </div>
        </div>

        {/* Legend */}
        <div className="border-t border-line-soft bg-abyss/50 px-6 py-4 md:px-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <div className="h-3 w-12 rounded-sm bg-gradient-to-r from-accent to-up" />
              <span className="font-mono text-[10px] uppercase tracking-widest text-ink-dim">
                Equity Growth
              </span>
            </div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
              {data[0].date} — {data[data.length - 1].date}
            </div>
          </div>
        </div>

        {/* SIMULATED label */}
        <div className="border-t border-warn/20 bg-warn/5 px-4 py-2 md:px-6">
          <span className="font-mono text-[9px] font-semibold uppercase tracking-widest text-warn">
            ILLUSTRATIVE / SIMULATED DATA
          </span>
        </div>
      </motion.div>
    </div>
  );
}
