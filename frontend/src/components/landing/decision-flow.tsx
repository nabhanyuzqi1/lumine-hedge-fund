import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { SAMPLE_MASTER_DECISION, AGENTS } from "@/data/landing/agents";
import {
  TechnicalIcon,
  MacroIcon,
  NewsIcon,
  StructureIcon,
} from "./agent-icons";

/**
 * DecisionFlow — Decision & Risk section.
 * Satu panel utuh, 3 baris linear yang langsung terbaca:
 *   [1] SIGNALS → [2] MASTER THESIS → [3] RISK GATES → APPROVED
 * Kerapian: satu container, divider antar baris, step number di kiri.
 */

const AGENT_ICONS: Record<string, (p: { size?: number }) => ReactNode> = {
  technical: TechnicalIcon,
  macro: MacroIcon,
  news: NewsIcon,
  structure: StructureIcon,
};

const GATES = ["Position Sizing", "Max Exposure", "Daily Loss Limit", "Kill Switch"];

interface DecisionFlowProps {
  className?: string;
}

export function DecisionFlow({ className }: DecisionFlowProps) {
  const decision = SAMPLE_MASTER_DECISION;

  return (
    <motion.div
      className={cn(
        "overflow-hidden rounded-panel border border-line bg-raised shadow-panel",
        className
      )}
      initial={{ opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.7, ease: "easeOut" }}
    >
      {/* Panel header */}
      <div className="flex items-center justify-between border-b border-line-soft bg-abyss/40 px-5 py-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.25em] text-ink-faint">
          Decision Pipeline
        </span>
        <span className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.2em] text-up">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-up" />
          Live
        </span>
      </div>

      {/* Row 1 — Signals */}
      <div className="grid gap-4 px-5 py-4 md:grid-cols-[120px_1fr] md:gap-6">
        <div className="flex items-center gap-2.5 md:flex-col md:items-start md:gap-1.5">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent font-mono text-[10px] font-bold text-white">
            1
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-faint">
            Signals
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {decision.analyses.map((analysis, i) => {
            const agent = AGENTS.find((a) => a.name === analysis.agent);
            const Icon = agent ? AGENT_ICONS[agent.id] : null;
            const color = agent?.color ?? "#A7B3C5";
            const biasColor =
              analysis.bias === "BULLISH"
                ? "text-up"
                : analysis.bias === "BEARISH"
                  ? "text-down"
                  : "text-ink-dim";
            return (
              <motion.span
                key={analysis.agent}
                className="inline-flex items-center gap-2 rounded-chip border border-line-soft bg-abyss/40 px-3 py-1.5"
                initial={{ opacity: 0, y: 6 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ duration: 0.3, delay: 0.1 + i * 0.06 }}
              >
                <span style={{ color }}>{Icon && <Icon size={15} />}</span>
                <span className="font-display text-[10px] font-semibold uppercase tracking-wider text-ink">
                  {analysis.agent}
                </span>
                <span className={cn("font-mono text-[10px] font-bold", biasColor)}>
                  {analysis.bias} {analysis.confidence.toFixed(0)}%
                </span>
              </motion.span>
            );
          })}
        </div>
      </div>

      <div className="mx-5 h-px bg-line-soft" />

      {/* Row 2 — Master thesis */}
      <div className="grid gap-4 px-5 py-4 md:grid-cols-[120px_1fr] md:gap-6">
        <div className="flex items-center gap-2.5 md:flex-col md:items-start md:gap-1.5">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent font-mono text-[10px] font-bold text-white">
            2
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-faint">
            Master Thesis
          </span>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs uppercase tracking-widest text-ink-faint">
              Asset
            </span>
            <span className="font-mono text-lg font-bold text-ink">{decision.asset}</span>
          </div>
          <div
            className={cn(
              "inline-flex items-center gap-2 rounded-chip border px-3 py-1 font-mono text-xs font-bold uppercase tracking-widest",
              decision.bias === "BULLISH"
                ? "border-up/30 bg-up/10 text-up"
                : decision.bias === "BEARISH"
                  ? "border-down/30 bg-down/10 text-down"
                  : "border-line bg-raised/50 text-ink-dim"
            )}
          >
            {decision.bias} · {decision.confidence.toFixed(0)}%
          </div>
          <p className="w-full text-sm leading-relaxed text-ink-dim">
            <span className="font-semibold text-accent">{decision.consensus}:</span>{" "}
            {decision.masterThesis}
          </p>
        </div>
      </div>

      <div className="mx-5 h-px bg-line-soft" />

      {/* Row 3 — Risk gates + result */}
      <div className="grid gap-4 px-5 py-4 md:grid-cols-[120px_1fr] md:gap-6">
        <div className="flex items-center gap-2.5 md:flex-col md:items-start md:gap-1.5">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent font-mono text-[10px] font-bold text-white">
            3
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-faint">
            Risk Gates
          </span>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {GATES.map((gate, i) => (
              <motion.span
                key={gate}
                className="inline-flex items-center gap-1.5 rounded-chip border border-line-soft bg-abyss/40 px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-wider text-ink"
                initial={{ opacity: 0, y: 6 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ duration: 0.3, delay: 0.2 + i * 0.06 }}
              >
                <svg
                  className="h-3 w-3 text-up"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={3}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
                {gate}
              </motion.span>
            ))}
          </div>
          <motion.div
            className="inline-flex items-center gap-2 rounded-chip border border-up/30 bg-up/10 px-3 py-1.5"
            initial={{ opacity: 0, scale: 0.9 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ duration: 0.4, delay: 0.5 }}
          >
            <svg className="h-3.5 w-3.5 text-up" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={3}
                d="M5 13l4 4L19 7"
              />
            </svg>
            <span className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-up">
              Approved
            </span>
          </motion.div>
        </div>
      </div>

      {/* Panel footer */}
      <div className="border-t border-warn/20 bg-warn/5 px-5 py-2">
        <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-warn">
          SIMULATED DATA
        </span>
      </div>
    </motion.div>
  );
}
