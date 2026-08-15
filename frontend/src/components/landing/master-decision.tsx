import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { SAMPLE_MASTER_DECISION } from "@/data/landing/agents";
import type { AgentAnalysis } from "@/data/landing/agents";

/**
 * MasterDecision — Shows how multiple agents feed into one decision.
 * Section 9 of master prompt: "Many Signals. One Decision."
 * SIMULATED DATA — clearly labeled.
 */

interface BiasIndicatorProps {
  bias: "BULLISH" | "BEARISH" | "NEUTRAL";
  confidence: number;
  size?: "sm" | "md" | "lg";
}

function BiasIndicator({ bias, confidence, size = "md" }: BiasIndicatorProps) {
  const colors = {
    BULLISH: "text-up border-up/30 bg-up/10",
    BEARISH: "text-down border-down/30 bg-down/10",
    NEUTRAL: "text-ink-dim border-line bg-raised/50",
  };

  const sizes = {
    sm: "px-2 py-0.5 text-[9px]",
    md: "px-2.5 py-1 text-[10px]",
    lg: "px-3 py-1.5 text-xs",
  };

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-chip border font-mono font-semibold uppercase tracking-widest",
        colors[bias],
        sizes[size]
      )}
    >
      <span>{bias}</span>
      <span className="opacity-60">{confidence.toFixed(0)}%</span>
    </div>
  );
}

interface AgentAnalysisRowProps {
  analysis: AgentAnalysis;
}

function AgentAnalysisRow({ analysis }: AgentAnalysisRowProps) {
  return (
    <div className="flex flex-col gap-2 rounded-chip border border-line-soft bg-raised/30 p-3 backdrop-blur transition-colors hover:border-line hover:bg-raised/50">
      <div className="flex items-center justify-between gap-3">
        <span className="font-display text-xs font-semibold text-ink">
          {analysis.agent}
        </span>
        <BiasIndicator
          bias={analysis.bias}
          confidence={analysis.confidence}
          size="sm"
        />
      </div>
      <p className="text-[11px] leading-relaxed text-ink-dim">
        {analysis.reasoning}
      </p>
    </div>
  );
}

interface MasterDecisionProps {
  className?: string;
  showHeader?: boolean;
  variant?: "full" | "compact";
}

export function MasterDecision({
  className,
  showHeader = true,
  variant = "full",
}: MasterDecisionProps) {
  const decision = SAMPLE_MASTER_DECISION;

  return (
    <div className={cn("w-full max-w-4xl space-y-6", className)}>
      {/* Header */}
      {showHeader && (
        <div className="space-y-3 text-center">
          <div className="flex items-center justify-center gap-2">
            <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
              Lumine Decision
            </span>
            <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
          </div>
          <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
            Many Signals. One Decision.
          </h3>
          <p className="mx-auto max-w-2xl text-sm leading-relaxed text-ink-dim">
            The Master Agent evaluates agreement, disagreement, confidence, and
            market regime before deciding. It does not blindly follow one analyst.
          </p>
        </div>
      )}

      {/* Decision card */}
      <motion.div
        className="rounded-panel border border-line bg-raised shadow-panel"
        initial={{ opacity: 0, y: 28 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.7, ease: "easeOut" }}
      >
        {/* Decision header */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line-soft p-4 md:p-6">
          <div className="flex items-center gap-3">
            <div className="font-mono text-xs uppercase tracking-widest text-ink-faint">
              Asset
            </div>
            <div className="font-mono text-lg font-bold text-ink">
              {decision.asset}
            </div>
          </div>
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, delay: 0.3 }}
          >
            <BiasIndicator
              bias={decision.bias}
              confidence={decision.confidence}
              size="lg"
            />
          </motion.div>
        </div>

        {/* Agent analyses — full variant only */}
        {variant === "full" && (
          <div className="space-y-3 p-4 md:p-6">
            <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
              Agent Analyses
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {decision.analyses.map((analysis, i) => (
                <motion.div
                  key={analysis.agent}
                  initial={{ opacity: 0, y: 14 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: "-40px" }}
                  transition={{ duration: 0.45, delay: i * 0.1 }}
                >
                  <AgentAnalysisRow analysis={analysis} />
                </motion.div>
              ))}
            </div>
          </div>
        )}

        {/* Consensus */}
        <div className="border-t border-line-soft bg-abyss/50 p-4 md:p-6">
          <div className="flex flex-wrap items-center gap-4">
            <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
              Consensus
            </div>
            <div className="inline-flex items-center gap-2 rounded-chip border border-accent/30 bg-accent/10 px-3 py-1.5">
              <div className="h-1.5 w-1.5 rounded-full bg-accent" />
              <span className="font-mono text-xs font-semibold uppercase tracking-widest text-accent">
                {decision.consensus}
              </span>
            </div>
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-ink-dim">
            {decision.masterThesis}
          </p>
        </div>

        {/* SIMULATED label */}
        <div className="border-t border-warn/20 bg-warn/5 px-4 py-2 md:px-6">
          <span className="font-mono text-[9px] font-semibold uppercase tracking-widest text-warn">
            SIMULATED DATA
          </span>
        </div>
      </motion.div>
    </div>
  );
}
