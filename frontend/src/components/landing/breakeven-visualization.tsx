import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/**
 * BreakEvenVisualization — Section 11 of master prompt.
 * "Break-Even Should Understand Structure."
 * Shows Lumine's signature dynamic trade management feature.
 */

interface BreakEvenVisualizationProps {
  className?: string;
  showHeader?: boolean;
}

export function BreakEvenVisualization({
  className,
  showHeader = true,
}: BreakEvenVisualizationProps) {
  return (
    <div className={cn("w-full max-w-4xl space-y-6", className)}>
      {/* Header */}
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
            A profitable position does not automatically justify moving its stop
            to entry. Lumine evaluates market structure, momentum, volatility, and
            nearby levels before adjusting risk.
          </p>
        </div>
      )}

      {/* Visualization card */}
      <motion.div
        className="rounded-panel border border-line bg-raised shadow-panel"
        initial={{ opacity: 0, y: 28 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.7, ease: "easeOut" }}
      >
        <div className="space-y-6 p-6 md:p-8">
          {/* Decision tree */}
          <div className="space-y-4">
            {/* Entry */}
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 border-accent bg-accent/10">
                <span className="font-mono text-xs font-bold text-accent">
                  ENTRY
                </span>
              </div>
              <div className="flex-1 text-sm text-ink-dim">
                Position opened at target entry price
              </div>
            </div>

            {/* Vertical line */}
            <div className="ml-5 h-8 w-px bg-line" />

            {/* +1R reached */}
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 border-up bg-up/10">
                <span className="font-mono text-xs font-bold text-up">+1R</span>
              </div>
              <div className="flex-1 text-sm text-ink-dim">
                Position reaches 1× initial risk in profit
              </div>
            </div>

            {/* Branch split */}
            <div className="ml-5 space-y-4">
              {/* Branch 1: Strong structure */}
              <div className="flex gap-3">
                <div className="flex flex-col items-center">
                  <div className="h-4 w-px bg-line" />
                  <div className="h-2 w-2 rounded-full bg-line" />
                  <div className="h-12 w-px bg-line" />
                </div>
                <div className="flex-1 space-y-2">
                  <div className="rounded-chip border border-line-soft bg-raised/50 px-3 py-2">
                    <div className="font-mono text-[10px] font-semibold uppercase tracking-widest text-accent">
                      Strong Structure
                    </div>
                    <div className="mt-1 text-[11px] text-ink-dim">
                      Structure intact, momentum sustained, no major resistance
                      nearby
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <svg
                      className="h-4 w-4 text-accent"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 5l7 7-7 7"
                      />
                    </svg>
                    <span className="font-mono text-xs font-bold uppercase tracking-widest text-up">
                      Hold SL
                    </span>
                  </div>
                </div>
              </div>

              {/* Branch 2: Weakening momentum */}
              <div className="flex gap-3">
                <div className="flex flex-col items-center">
                  <div className="h-2 w-2 rounded-full bg-line" />
                  <div className="h-12 w-px bg-line" />
                </div>
                <div className="flex-1 space-y-2">
                  <div className="rounded-chip border border-line-soft bg-raised/50 px-3 py-2">
                    <div className="font-mono text-[10px] font-semibold uppercase tracking-widest text-warn">
                      Weakening Momentum
                    </div>
                    <div className="mt-1 text-[11px] text-ink-dim">
                      Momentum slowing, volume declining, approaching resistance
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <svg
                      className="h-4 w-4 text-accent"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 5l7 7-7 7"
                      />
                    </svg>
                    <span className="font-mono text-xs font-bold uppercase tracking-widest text-accent">
                      Move to BE
                    </span>
                  </div>
                </div>
              </div>

              {/* Branch 3: Structure break */}
              <div className="flex gap-3">
                <div className="flex flex-col items-center">
                  <div className="h-2 w-2 rounded-full bg-line" />
                  <div className="h-8 w-px bg-line" />
                </div>
                <div className="flex-1 space-y-2">
                  <div className="rounded-chip border border-line-soft bg-raised/50 px-3 py-2">
                    <div className="font-mono text-[10px] font-semibold uppercase tracking-widest text-down">
                      Structure Break
                    </div>
                    <div className="mt-1 text-[11px] text-ink-dim">
                      Key support broken, trend reversal signal, invalidation
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <svg
                      className="h-4 w-4 text-accent"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 5l7 7-7 7"
                      />
                    </svg>
                    <span className="font-mono text-xs font-bold uppercase tracking-widest text-down">
                      Exit
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
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
