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
 * DecisionFlow — Decision & Risk section, redesigned for laypeople.
 * Satu alur linear bernomor, 3 langkah + hasil:
 *   ① SIGNALS → ② MASTER THESIS → ③ RISK GATES → ✓ APPROVED
 * Max 5 unit informasi (Miller). Setiap langkah punya label jelas.
 */

const AGENT_ICONS: Record<string, (p: { size?: number }) => ReactNode> = {
  technical: TechnicalIcon,
  macro: MacroIcon,
  news: NewsIcon,
  structure: StructureIcon,
};

const GATES = ["Position Sizing", "Max Exposure", "Daily Loss Limit", "Kill Switch"];

function StepArrow() {
  return (
    <div className="flex justify-center py-1">
      <svg
        className="h-4 w-4 animate-bounce text-accent"
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
  );
}

function StepLabel({ n, label }: { n: string; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent font-mono text-[10px] font-bold text-white">
        {n}
      </span>
      <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
        {label}
      </span>
    </div>
  );
}

interface DecisionFlowProps {
  className?: string;
}

export function DecisionFlow({ className }: DecisionFlowProps) {
  const decision = SAMPLE_MASTER_DECISION;

  return (
    <div className={cn("w-full max-w-3xl", className)}>
      {/* ① SIGNALS */}
      <motion.div
        className="rounded-panel border border-line bg-raised/50 p-5 backdrop-blur"
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-40px" }}
        transition={{ duration: 0.5 }}
      >
        <StepLabel n="1" label="Empat analis mengirim sinyal" />
        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
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
                initial={{ opacity: 0, y: 8 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ duration: 0.35, delay: i * 0.07 }}
              >
                <span style={{ color }}>{Icon && <Icon size={16} />}</span>
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
      </motion.div>

      <StepArrow />

      {/* ② MASTER THESIS */}
      <motion.div
        className="rounded-panel border border-line bg-raised/50 p-5 backdrop-blur"
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-40px" }}
        transition={{ duration: 0.5, delay: 0.1 }}
      >
        <StepLabel n="2" label="Master Intelligence merumuskan tesis" />
        <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs uppercase tracking-widest text-ink-faint">
              Asset
            </span>
            <span className="font-mono text-xl font-bold text-ink">
              {decision.asset}
            </span>
          </div>
          <div
            className={cn(
              "inline-flex items-center gap-2 rounded-chip border px-3 py-1.5 font-mono text-xs font-bold uppercase tracking-widest",
              decision.bias === "BULLISH"
                ? "border-up/30 bg-up/10 text-up"
                : decision.bias === "BEARISH"
                  ? "border-down/30 bg-down/10 text-down"
                  : "border-line bg-raised/50 text-ink-dim"
            )}
          >
            {decision.bias} · {decision.confidence.toFixed(0)}%
          </div>
        </div>
        <div className="mt-3 rounded-chip border border-accent/20 bg-accent/5 px-4 py-3">
          <p className="text-sm leading-relaxed text-ink-dim">
            <span className="font-semibold text-accent">{decision.consensus}:</span>{" "}
            {decision.masterThesis}
          </p>
        </div>
      </motion.div>

      <StepArrow />

      {/* ③ RISK GATES */}
      <motion.div
        className="rounded-panel border border-line bg-raised/50 p-5 backdrop-blur"
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-40px" }}
        transition={{ duration: 0.5, delay: 0.2 }}
      >
        <StepLabel n="3" label="Tesis melewati gerbang risiko" />
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {GATES.map((gate, i) => (
            <motion.div
              key={gate}
              className="flex items-center gap-2 rounded-chip border border-line-soft bg-abyss/40 px-3 py-1.5"
              initial={{ opacity: 0, y: 8 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.35, delay: 0.3 + i * 0.08 }}
            >
              <svg
                className="h-3.5 w-3.5 text-up"
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
              <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-ink">
                {gate}
              </span>
            </motion.div>
          ))}
        </div>

        {/* Result */}
        <motion.div
          className="mt-4 flex items-center justify-center gap-2.5 rounded-chip border border-up/30 bg-up/10 py-3"
          initial={{ opacity: 0, scale: 0.92 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true, margin: "-40px" }}
          transition={{ duration: 0.5, delay: 0.7 }}
        >
          <svg className="h-4 w-4 text-up" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={3}
              d="M5 13l4 4L19 7"
            />
          </svg>
          <span className="font-mono text-xs font-bold uppercase tracking-[0.22em] text-up">
            Approved — siap dieksekusi
          </span>
        </motion.div>
      </motion.div>

      <p className="mt-4 text-center font-mono text-[9px] uppercase tracking-[0.2em] text-warn">
        SIMULATED DATA
      </p>
    </div>
  );
}
