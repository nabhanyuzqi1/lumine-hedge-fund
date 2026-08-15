import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/**
 * ValidationPipeline — Section 13 of master prompt.
 * "A Strategy Is Not an Edge Until It Survives Validation."
 * Shows the backtesting and out-of-sample validation process.
 */

interface ValidationStageProps {
  stage: string;
  description: string;
  isActive?: boolean;
}

function ValidationStage({
  stage,
  description,
  isActive,
}: ValidationStageProps) {
  return (
    <div
      className={cn(
        "rounded-chip border px-4 py-3 transition-all",
        isActive
          ? "border-accent bg-accent/10 shadow-lg"
          : "border-line-soft bg-raised/30"
      )}
    >
      <div className="space-y-1">
        <div
          className={cn(
            "font-mono text-xs font-bold uppercase tracking-widest",
            isActive ? "text-accent" : "text-ink"
          )}
        >
          {stage}
        </div>
        <div className="text-[11px] leading-relaxed text-ink-dim">
          {description}
        </div>
      </div>
    </div>
  );
}

const VALIDATION_STAGES: ValidationStageProps[] = [
  {
    stage: "Train",
    description:
      "Strategy developed on training period. Parameters optimized on in-sample data.",
    isActive: false,
  },
  {
    stage: "Validation",
    description:
      "First checkpoint: strategy tested on validation set without parameter changes.",
    isActive: false,
  },
  {
    stage: "Out-of-Sample",
    description:
      "Critical test: completely unseen data. This is where most strategies fail.",
    isActive: true,
  },
  {
    stage: "Paper Trading",
    description:
      "Real-time validation in live market conditions with zero capital risk.",
    isActive: false,
  },
  {
    stage: "Live",
    description:
      "Controlled capital deployment with strict risk limits and ongoing monitoring.",
    isActive: false,
  },
];

const VALIDATION_CHECKS = [
  "Historical backtesting across multiple market regimes",
  "Walk-forward analysis to prevent overfitting",
  "Out-of-sample testing on completely unseen data",
  "Monte Carlo simulation for robustness assessment",
  "Transaction costs, spread, and slippage modeling",
  "Execution assumptions validated against real fills",
  "Performance consistency across different timeframes",
  "Regime-specific performance breakdown and analysis",
];

interface ValidationPipelineProps {
  className?: string;
  showHeader?: boolean;
}

export function ValidationPipeline({ className, showHeader = true }: ValidationPipelineProps) {
  return (
    <div className={cn("w-full max-w-4xl space-y-6", className)}>
      {/* Header */}
      {showHeader && (
        <div className="space-y-3 text-center">
          <div className="flex items-center justify-center gap-2">
            <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
              Validation Pipeline
            </span>
            <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
          </div>
          <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
            A Strategy Is Not an Edge
            <br />
            Until It Survives Validation.
          </h3>
        </div>
      )}

      {/* Validation flow */}
      <div className="space-y-3">
        {VALIDATION_STAGES.map((stage, i) => (
          <motion.div
            key={i}
            className="space-y-2"
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ duration: 0.4, delay: i * 0.08 }}
          >
            <ValidationStage {...stage} />
            {i < VALIDATION_STAGES.length - 1 && (
              <div className="flex justify-center">
                <svg
                  className="h-6 w-6 text-accent opacity-50"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 14l-7 7m0 0l-7-7m7 7V3"
                  />
                </svg>
              </div>
            )}
          </motion.div>
        ))}
      </div>

      {/* Validation checklist */}
      <div className="rounded-panel border border-line bg-raised shadow-panel">
        <div className="space-y-4 p-6 md:p-8">
          <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
            Validation Requirements
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {VALIDATION_CHECKS.map((check, i) => (
              <div key={i} className="flex items-start gap-2">
                <svg
                  className="mt-0.5 h-4 w-4 shrink-0 text-accent"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
                <span className="text-[11px] leading-relaxed text-ink-dim">
                  {check}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-line-soft bg-abyss/50 px-6 py-4 md:px-8">
          <p className="text-center text-xs leading-relaxed text-ink-dim">
            Out-of-sample performance is the only honest measure of edge.
          </p>
        </div>
      </div>
    </div>
  );
}
