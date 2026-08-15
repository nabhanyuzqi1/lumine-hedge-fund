import { motion, AnimatePresence, useScroll, useMotionValueEvent } from "framer-motion";
import { useRef, useState } from "react";
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

  // Scroll-driven: stage maju otomatis saat user scroll melewati section.
  const sectionRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start 0.85", "end 0.45"],
  });
  useMotionValueEvent(scrollYProgress, "change", (v) => {
    const next = Math.min(
      PIPELINE_STAGES.length - 1,
      Math.max(0, Math.floor(v * PIPELINE_STAGES.length))
    );
    setActive(next);
  });

  return (
    <div ref={sectionRef} className={cn("mx-auto w-full max-w-4xl space-y-6", className)}>
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
          {/* Horizontal timeline: dots + connecting line */}
          <div className="relative">
            {/* Connecting line */}
            <div className="absolute left-0 right-0 top-[11px] h-px bg-line" />
            <motion.div
              className="absolute left-0 top-[11px] h-px bg-accent"
              initial={{ width: 0 }}
              whileInView={{ width: `${(active / (PIPELINE_STAGES.length - 1)) * 100}%` }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.6, ease: "easeOut" }}
            />
            {/* Stage dots */}
            <div className="relative grid grid-cols-6">
              {PIPELINE_STAGES.map((s, i) => {
                const isActive = active === i;
                const isDone = i < active;
                return (
                  <motion.button
                    key={s.number}
                    type="button"
                    className="group flex cursor-pointer flex-col items-center gap-2"
                    initial={{ opacity: 0, y: 10 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-40px" }}
                    transition={{ duration: 0.3, delay: i * 0.05 }}
                    onClick={() => setActive(i)}
                    aria-pressed={isActive}
                    aria-label={`Stage ${s.number}: ${s.title}`}
                  >
                    <span
                      className={cn(
                        "flex h-[22px] w-[22px] items-center justify-center rounded-full border-2 font-mono text-[9px] font-bold transition-all duration-200",
                        isActive
                          ? "scale-110 border-accent bg-accent text-white"
                          : isDone
                            ? "border-up bg-up/10 text-up"
                            : "border-line bg-raised text-ink-faint group-hover:border-ink-faint"
                      )}
                    >
                      {isDone ? "✓" : s.number}
                    </span>
                    <span
                      className={cn(
                        "font-display text-[9px] font-semibold uppercase tracking-wider transition-colors md:text-[10px]",
                        isActive ? "text-accent" : isDone ? "text-ink-dim" : "text-ink-faint"
                      )}
                    >
                      {s.title}
                    </span>
                  </motion.button>
                );
              })}
            </div>
          </div>

          {/* Active stage detail — satu deskripsi saja */}
          <AnimatePresence mode="wait">
            <motion.div
              key={stage.number}
              className="mt-6 rounded-chip border border-line-soft bg-abyss/40 p-5"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
            >
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs uppercase tracking-[0.25em] text-accent">
                  Stage {stage.number}
                </span>
                <span className="h-px w-6 bg-line" />
                <h4 className="font-display text-lg font-bold text-ink">
                  {stage.title}
                </h4>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-ink-dim">
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
