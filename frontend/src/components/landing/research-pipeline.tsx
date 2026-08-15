import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/**
 * ResearchPipeline — Section 12 of master prompt.
 * "From Hypothesis to Capital."
 * Shows the complete research lifecycle before strategies reach production.
 */

interface PipelineStageProps {
  number: string;
  title: string;
  description: string;
  status?: "complete" | "in-progress" | "pending";
}

function PipelineStage({
  number,
  title,
  description,
  status = "pending",
}: PipelineStageProps) {
  const statusColors = {
    complete: "border-up bg-up/10",
    "in-progress": "border-accent bg-accent/10 animate-pulse",
    pending: "border-line-soft bg-raised/30",
  };

  return (
    <div className="flex gap-4">
      {/* Number badge */}
      <div className="flex shrink-0 flex-col items-center gap-2">
        <div
          className={cn(
            "flex h-10 w-10 items-center justify-center rounded-full border-2 font-mono text-sm font-bold transition-all",
            statusColors[status]
          )}
        >
          {number}
        </div>
        {/* Connector line */}
        <div className="h-full w-px bg-gradient-to-b from-line via-line-soft to-transparent" />
      </div>

      {/* Content */}
      <div className="flex-1 space-y-2 pb-8">
        <h4 className="font-display text-base font-bold text-ink">{title}</h4>
        <p className="text-sm leading-relaxed text-ink-dim">{description}</p>
      </div>
    </div>
  );
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
            rigorous research and validation lifecycle.
          </p>
        </div>
      )}

      {/* Pipeline stages */}
      <motion.div
        className="rounded-panel border border-line bg-raised shadow-panel"
        initial={{ opacity: 0, y: 28 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.7, ease: "easeOut" }}
      >
        <div className="p-6 md:p-8">
          {PIPELINE_STAGES.map((stage, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -16 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.45, delay: i * 0.08 }}
            >
              <PipelineStage {...stage} />
            </motion.div>
          ))}
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
