import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import { cn } from "@/lib/utils";

/**
 * ResearchPipeline — Section 22 of UI/UX Rebuild V2.
 * Interactive stepper: click a stage to inspect its detail.
 */

interface PipelineStageProps {
  number: string;
  title: string;
  description: string;
  status?: "complete" | "in-progress" | "pending";
}

const PIPELINE_STAGES: PipelineStageProps[] = [
  {
    number: "01",
    title: "Observe",
    description:
      "Continuous market data ingestion and regime detection. Agents monitor technical, macro, news, and structural conditions.",
    status: "complete",
  },
  {
    number: "02",
    title: "Research",
    description:
      "Agents generate strategy hypotheses based on observed patterns, correlations, and market conditions. Committee deliberates trade-offs.",
    status: "in-progress",
  },
  {
    number: "03",
    title: "Validate",
    description:
      "Statistical testing: hypothesis tests, correlation analysis, regime stability checks. Strategies must pass quantitative validation.",
    status: "pending",
  },
  {
    number: "04",
    title: "Simulate",
    description:
      "Backtesting on historical data, walk-forward analysis, out-of-sample testing. Monte Carlo simulation for robustness.",
    status: "pending",
  },
  {
    number: "05",
    title: "Paper",
    description:
      "Real-time paper trading in live market conditions with zero capital risk. Performance tracked against simulated expectations.",
    status: "pending",
  },
  {
    number: "06",
    title: "Deploy",
    description:
      "Controlled capital deployment with strict risk limits. Strategies earn the right to production through rigorous validation.",
    status: "pending",
  },
];

interface ResearchPipelineProps {
  className?: string;
  showHeader?: boolean;
}

export function ResearchPipeline({ className, showHeader = true }: ResearchPipelineProps) {
  const [active, setActive] = useState(0);
  const stage = PIPELINE_STAGES[active];

  return (
    <div className={cn("w-full max-w-4xl space-y-6", className)}>
      {/* Header */}
      {showHeader && (
        <div className="space-y-3 text-center">
          <div className="flex items-center justify-center gap-2">
            <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
              Research Pipeline
            </span>
            <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
          </div>
          <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
            From Hypothesis to Capital.
          </h3>
          <p className="mx-auto max-w-2xl text-sm leading-relaxed text-ink-dim">
            Every strategy must earn the right to reach production through a
            rigorous research and validation lifecycle. Click a stage to inspect it.
          </p>
        </div>
      )}

      {/* Interactive stepper */}
      <motion.div
        className="rounded-panel border border-line bg-raised shadow-panel"
        initial={{ opacity: 0, y: 28 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.7, ease: "easeOut" }}
      >
        <div className="p-6 md:p-8">
          {/* Stage chips */}
          <div className="grid grid-cols-3 gap-2 md:grid-cols-6">
            {PIPELINE_STAGES.map((s, i) => {
              const isActive = active === i;
              const isDone = i < active;
              return (
                <motion.button
                  key={s.number}
                  type="button"
                  className="flex cursor-pointer flex-col items-center gap-1.5 rounded-chip border px-2 py-3 transition-all duration-200"
                  style={{
                    borderColor: isActive
                      ? "var(--color-accent)"
                      : isDone
                        ? "var(--color-up)"
                        : "var(--color-line-soft)",
                    backgroundColor: isActive
                      ? "rgba(77,141,255,0.12)"
                      : isDone
                        ? "rgba(52,211,153,0.06)"
                        : "var(--color-raised)",
                  }}
                  initial={{ opacity: 0, y: 12 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: "-40px" }}
                  transition={{ duration: 0.35, delay: i * 0.06 }}
                  onClick={() => setActive(i)}
                  aria-pressed={isActive}
                >
                  <span
                    className={cn(
                      "font-mono text-[10px] font-bold",
                      isActive
                        ? "text-accent"
                        : isDone
                          ? "text-up"
                          : "text-ink-faint"
                    )}
                  >
                    {s.number}
                  </span>
                  <span
                    className={cn(
                      "font-display text-[10px] font-semibold uppercase tracking-wider md:text-xs",
                      isActive ? "text-ink" : "text-ink-dim"
                    )}
                  >
                    {s.title}
                  </span>
                </motion.button>
              );
            })}
          </div>

          {/* Active stage detail */}
          <AnimatePresence mode="wait">
            <motion.div
              key={stage.number}
              className="mt-6 rounded-chip border border-line-soft bg-abyss/40 p-5"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm font-bold text-accent">
                    {stage.number}
                  </span>
                  <h4 className="font-display text-lg font-bold text-ink">
                    {stage.title}
                  </h4>
                </div>
                <span
                  className={cn(
                    "rounded-chip border px-2 py-0.5 font-mono text-[8px] font-semibold uppercase tracking-widest",
                    stage.status === "complete"
                      ? "border-up/30 bg-up/10 text-up"
                      : stage.status === "in-progress"
                        ? "border-accent/30 bg-accent/10 text-accent"
                        : "border-line-soft bg-raised/30 text-ink-faint"
                  )}
                >
                  {stage.status === "complete"
                    ? "Complete"
                    : stage.status === "in-progress"
                      ? "In Progress"
                      : "Pending"}
                </span>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-ink-dim">
                {stage.description}
              </p>
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Footer notice */}
        <div className="border-t border-line-soft bg-abyss/50 px-6 py-4 md:px-8">
          <p className="text-center text-xs leading-relaxed text-ink-dim">
            <span className="font-semibold text-accent">
              No shortcuts to production.
            </span>{" "}
            A strategy is not an edge until it survives validation.
          </p>
        </div>
      </motion.div>
    </div>
  );
}
