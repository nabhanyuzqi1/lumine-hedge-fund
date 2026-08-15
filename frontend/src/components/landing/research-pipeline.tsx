import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/**
 * Strategy Lifecycle — simple 6-row checklist (V2.5).
 * Scroll-driven stepper was removed (auto-advancing content felt
 * uncontrolled). Now: one compact vertical list, every stage visible
 * at once — zero interaction required, zero ambiguity.
 * Progress state shown with a left accent + status dot per row.
 */

interface Stage {
  number: string;
  title: string;
  description: string;
  state: "complete" | "active" | "pending";
}

const STAGES: Stage[] = [
  {
    number: "01",
    title: "Observe",
    description: "Continuous data ingestion and regime detection.",
    state: "complete",
  },
  {
    number: "02",
    title: "Research",
    description: "Strategy hypotheses from observed market patterns.",
    state: "complete",
  },
  {
    number: "03",
    title: "Validate",
    description: "Statistical testing — hypothesis, correlation, stability.",
    state: "active",
  },
  {
    number: "04",
    title: "Simulate",
    description: "Backtesting, walk-forward and out-of-sample runs.",
    state: "pending",
  },
  {
    number: "05",
    title: "Paper",
    description: "Live paper trading with zero capital risk.",
    state: "pending",
  },
  {
    number: "06",
    title: "Deploy",
    description: "Controlled capital with strict risk limits.",
    state: "pending",
  },
];

const STATE_STYLE: Record<Stage["state"], { dot: string; label: string }> = {
  complete: { dot: "bg-up", label: "text-up" },
  active: { dot: "bg-accent animate-pulse", label: "text-accent" },
  pending: { dot: "bg-line", label: "text-ink-faint" },
};

const STATE_LABEL: Record<Stage["state"], string> = {
  complete: "Done",
  active: "Current",
  pending: "Pending",
};

interface ResearchPipelineProps {
  className?: string;
  showHeader?: boolean;
}

export function ResearchPipeline({ className, showHeader = true }: ResearchPipelineProps) {
  return (
    <div className={cn("mx-auto w-full max-w-4xl space-y-6", className)}>
      {showHeader && (
        <div className="space-y-3 text-center">
          <div className="flex items-center justify-center gap-2">
            <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
              Strategy Lifecycle
            </span>
            <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
          </div>
          <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
            From Hypothesis to Capital.
          </h3>
          <p className="mx-auto max-w-2xl text-sm leading-relaxed text-ink-dim">
            Every strategy must survive this lifecycle before real capital is deployed.
          </p>
        </div>
      )}

      {/* Simple vertical checklist */}
      <motion.div
        className="overflow-hidden rounded-panel border border-line bg-raised shadow-panel"
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.6, ease: "easeOut" }}
      >
        {STAGES.map((stage, i) => {
          const style = STATE_STYLE[stage.state];
          return (
            <motion.div
              key={stage.number}
              className={cn(
                "flex items-center gap-4 px-5 py-3.5 md:gap-6 md:px-6",
                i > 0 && "border-t border-line-soft"
              )}
              initial={{ opacity: 0, x: -12 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.35, delay: i * 0.05 }}
            >
              {/* Number */}
              <span
                className={cn(
                  "w-8 shrink-0 font-mono text-sm font-bold",
                  stage.state === "active" ? "text-accent" : "text-ink-faint"
                )}
              >
                {stage.number}
              </span>

              {/* Title + description */}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2.5">
                  <span className="font-display text-sm font-semibold text-ink">
                    {stage.title}
                  </span>
                  <span className="flex items-center gap-1.5 font-mono text-[8px] font-semibold uppercase tracking-[0.18em] text-ink-faint">
                    <span className={cn("h-1 w-1 rounded-full", style.dot)} />
                    {STATE_LABEL[stage.state]}
                  </span>
                </div>
                <p className="mt-0.5 truncate text-xs leading-relaxed text-ink-dim md:text-[13px]">
                  {stage.description}
                </p>
              </div>
            </motion.div>
          );
        })}
      </motion.div>
    </div>
  );
}
