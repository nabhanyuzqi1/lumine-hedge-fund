import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import { cn } from "@/lib/utils";

/**
 * BreakEvenVisualization — Section 21 of UI/UX Rebuild V2.
 * Interactive simulation: drag the price slider along the trade path
 * and watch Lumine's structure-aware decision change:
 *   HOLD SL → MOVE TO BE → EXIT
 * The user understands the concept simply by interacting with it.
 */

interface BreakEvenVisualizationProps {
  className?: string;
  showHeader?: boolean;
}

/* Decision zones along the simulated path (0-100). */
type Decision = {
  id: "hold" | "be" | "exit";
  label: string;
  structure: string;
  momentum: string;
  color: string;
};

const DECISIONS: Decision[] = [
  {
    id: "hold",
    label: "HOLD SL",
    structure: "STRONG",
    momentum: "STRONG",
    color: "#34D399",
  },
  {
    id: "be",
    label: "MOVE → BE",
    structure: "STRONG",
    momentum: "WEAKENING",
    color: "#4D8DFF",
  },
  {
    id: "exit",
    label: "EXIT",
    structure: "DETERIORATING",
    momentum: "WEAK",
    color: "#F0555B",
  },
];

function decisionFor(pos: number): Decision {
  if (pos < 35) return DECISIONS[0];
  if (pos < 65) return DECISIONS[1];
  return DECISIONS[2];
}

/* Chart geometry (viewBox 600 x 220). */
const W = 600;
const H = 220;
const ENTRY_Y = 170;
const TP_Y = 60;
const BE_Y = ENTRY_Y; // break-even = entry price
const PAD = 40;

export function BreakEvenVisualization({
  className,
  showHeader = true,
}: BreakEvenVisualizationProps) {
  const [pos, setPos] = useState(30);
  const decision = decisionFor(pos);

  // Price path: monotonic rise from entry to TP.
  const priceY = (t: number) => ENTRY_Y - (ENTRY_Y - TP_Y) * (t / 100);
  const markerX = PAD + (pos / 100) * (W - PAD * 2);
  const markerY = priceY(pos);

  // Zone boundary positions (x axis)
  const xAt = (t: number) => PAD + (t / 100) * (W - PAD * 2);
  const x35 = xAt(35);
  const x65 = xAt(65);

  return (
    <div className={cn("mx-auto w-full max-w-4xl space-y-6", className)}>
      {showHeader && (
        <div className="space-y-3 text-center">
          <div className="flex items-center justify-center gap-2">
            <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
              Signature Feature
            </span>
            <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
          </div>
          <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
            Break-Even Should
            <br />
            Understand Structure.
          </h3>
          <p className="mx-auto max-w-2xl text-sm leading-relaxed text-ink-dim">
            A profitable position does not automatically justify moving its stop to
            entry. Drag the price along the path and watch Lumine decide.
          </p>
        </div>
      )}

      <motion.div
        className="overflow-hidden rounded-panel border border-line bg-raised shadow-panel"
        initial={{ opacity: 0, y: 28 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.7, ease: "easeOut" }}
      >
        {/* Simulation */}
        <div className="space-y-5 p-6 md:p-8">
          {/* Chart */}
          <div className="relative">
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
              {/* Grid */}
              {[0.25, 0.5, 0.75].map((g) => (
                <line
                  key={g}
                  x1={PAD}
                  x2={W - PAD}
                  y1={ENTRY_Y - (ENTRY_Y - TP_Y) * g}
                  y2={ENTRY_Y - (ENTRY_Y - TP_Y) * g}
                  stroke="var(--color-line)"
                  strokeWidth="0.5"
                  strokeDasharray="4 4"
                  opacity="0.5"
                />
              ))}

              {/* Zone backgrounds */}
              <rect x={PAD} y={TP_Y} width={x35 - PAD} height={ENTRY_Y - TP_Y} fill="rgba(52,211,153,0.05)" />
              <rect x={x35} y={TP_Y} width={x65 - x35} height={ENTRY_Y - TP_Y} fill="rgba(77,141,255,0.05)" />
              <rect x={x65} y={TP_Y} width={W - PAD - x65} height={ENTRY_Y - TP_Y} fill="rgba(240,85,91,0.05)" />

              {/* Zone labels */}
              <text x={(PAD + x35) / 2} y={H - 12} fontSize="8" fill="var(--color-ink-faint)" textAnchor="middle" fontFamily="IBM Plex Mono, monospace">
                HOLD
              </text>
              <text x={(x35 + x65) / 2} y={H - 12} fontSize="8" fill="var(--color-ink-faint)" textAnchor="middle" fontFamily="IBM Plex Mono, monospace">
                BE
              </text>
              <text x={(x65 + W - PAD) / 2} y={H - 12} fontSize="8" fill="var(--color-ink-faint)" textAnchor="middle" fontFamily="IBM Plex Mono, monospace">
                EXIT
              </text>

              {/* Level lines */}
              <line x1={PAD} x2={W - PAD} y1={BE_Y} y2={BE_Y} stroke="#FFB020" strokeWidth="1" strokeDasharray="6 4" opacity="0.6" />
              <text x={PAD + 2} y={BE_Y - 6} fontSize="8" fill="#FFB020" fontFamily="IBM Plex Mono, monospace">
                BE / ENTRY
              </text>
              <line x1={PAD} x2={W - PAD} y1={TP_Y} y2={TP_Y} stroke="#34D399" strokeWidth="1" strokeDasharray="6 4" opacity="0.6" />
              <text x={W - PAD - 2} y={TP_Y + 14} fontSize="8" fill="#34D399" textAnchor="end" fontFamily="IBM Plex Mono, monospace">
                TP +2R
              </text>

              {/* Price path */}
              <motion.path
                d={`M ${PAD} ${ENTRY_Y} L ${W - PAD} ${TP_Y}`}
                fill="none"
                stroke="url(#be-gradient)"
                strokeWidth="2.5"
                strokeLinecap="round"
                initial={{ pathLength: 0 }}
                whileInView={{ pathLength: 1 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ duration: 1.6, ease: "easeInOut" }}
              />
              {/* Area glow under path */}
              <motion.path
                d={`M ${PAD} ${ENTRY_Y} L ${W - PAD} ${TP_Y} L ${W - PAD} ${H} L ${PAD} ${H} Z`}
                fill="url(#be-area)"
                initial={{ opacity: 0 }}
                whileInView={{ opacity: 1 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ duration: 1.4, delay: 0.8 }}
              />
              <defs>
                <linearGradient id="be-gradient" x1="0%" y1="100%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#4d8dff" stopOpacity="0.9" />
                  <stop offset="100%" stopColor="#34d399" stopOpacity="0.9" />
                </linearGradient>
                <linearGradient id="be-area" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="#34d399" stopOpacity="0.10" />
                  <stop offset="100%" stopColor="#4d8dff" stopOpacity="0.02" />
                </linearGradient>
              </defs>

              {/* Entry marker */}
              <circle cx={PAD} cy={ENTRY_Y} r="4" fill="#FFB020" />

              {/* Position marker glow + dot (instan — selalu presisi) */}
              <circle cx={markerX} cy={markerY} r="14" fill={decision.color} opacity="0.15" />
              <circle
                cx={markerX}
                cy={markerY}
                r="6"
                fill={decision.color}
                stroke="#070b12"
                strokeWidth="2"
              />
            </svg>

            {/* Live price overlay — HTML, menempel presisi di marker */}
            <div
              className="pointer-events-none absolute z-10 -translate-x-1/2 whitespace-nowrap rounded-chip border border-line bg-abyss/95 px-2 py-0.5 font-mono text-[11px] font-bold tabular-nums backdrop-blur"
              style={{
                left: `${(markerX / W) * 100}%`,
                top: `${Math.max(markerY - 26, 2) / H}%`,
                color: decision.color,
                borderColor: `${decision.color}44`,
              }}
            >
              {(() => {
                const price = 3350 + (pos / 100) * 18;
                return price.toFixed(2);
              })()}
            </div>
          </div>

          {/* Slider */}
          <div className="space-y-2">
            <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-widest text-ink-faint">
              <span>Simulated price progress</span>
              <span className="text-ink">{pos}%</span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              value={pos}
              onChange={(e) => setPos(Number(e.target.value))}
              className="w-full cursor-pointer accent-[#4d8dff]"
              aria-label="Simulate price progress"
            />
          </div>

          {/* Decision readout */}
          <AnimatePresence mode="wait">
            <motion.div
              key={decision.id}
              className="rounded-chip border p-5"
              style={{
                borderColor: `${decision.color}44`,
                backgroundColor: `${decision.color}0d`,
              }}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
            >
              <div className="grid gap-4 sm:grid-cols-3">
                <div>
                  <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-ink-faint">
                    Structure
                  </div>
                  <div className="mt-1 font-mono text-sm font-bold" style={{ color: decision.color }}>
                    {decision.structure}
                  </div>
                </div>
                <div>
                  <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-ink-faint">
                    Momentum
                  </div>
                  <div className="mt-1 font-mono text-sm font-bold" style={{ color: decision.color }}>
                    {decision.momentum}
                  </div>
                </div>
                <div>
                  <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-ink-faint">
                    Decision
                  </div>
                  <div className="mt-1 font-mono text-sm font-bold" style={{ color: decision.color }}>
                    {decision.label}
                  </div>
                </div>
              </div>
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Footer */}
        <div className="border-t border-line-soft bg-abyss/50 px-6 py-4 md:px-8">
          <p className="text-center text-xs leading-relaxed text-ink-dim">
            <span className="font-semibold text-accent">
              Conceptual feature.
            </span>{" "}
            Not a guarantee of better returns. This demonstrates Lumine's
            structure-aware trade management philosophy.
          </p>
        </div>
      </motion.div>
    </div>
  );
}
