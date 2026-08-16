import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";
import { SAMPLE_MASTER_DECISION, AGENTS } from "@/data/landing/agents";
import {
  TechnicalIcon,
  MacroIcon,
  NewsIcon,
  StructureIcon,
} from "./agent-icons";

/**
 * DecisionFlow — Decision & Risk section (V2.5).
 * Visual pipeline: 3 columns (desktop) / stacked (mobile):
 *   [1] SIGNALS → [2] MASTER THESIS → [3] RISK GATES ✓
 * One concept per column; the arrow carries the eye left→right.
 */

const AGENT_ICONS: Record<string, (p: { size?: number }) => ReactNode> = {
  technical: TechnicalIcon,
  macro: MacroIcon,
  news: NewsIcon,
  structure: StructureIcon,
};

const GATE_KEYS = ["decision.positionSizing", "decision.maxExposure", "decision.dailyLossLimit", "decision.killSwitch"];

function StepBadge({ n, label }: { n: string; label: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent font-mono text-[11px] font-bold text-white">
        {n}
      </span>
      <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
        {label}
      </span>
    </div>
  );
}

function ArrowRight() {
  return (
    <div className="hidden items-center md:flex">
      <svg
        className="h-5 w-5 shrink-0 animate-pulse text-accent"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M13 7l5 5-5 5M6 12h12"
        />
      </svg>
    </div>
  );
}

function ArrowDown() {
  return (
    <div className="flex justify-center md:hidden">
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

interface DecisionFlowProps {
  className?: string;
}

export function DecisionFlow({ className }: DecisionFlowProps) {
  const { t } = useTranslation();
  const decision = SAMPLE_MASTER_DECISION;

  return (
    <div className={cn("w-full", className)}>
      {/* Pipeline header */}
      <div className="mb-4 flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-[0.25em] text-ink-faint">
          {t("decision.pipelineTitle")}
        </span>
        <span className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.2em] text-up">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-up" />
          {t("decision.live")}
        </span>
      </div>

      {/* 3-step pipeline */}
      <div className="flex flex-col items-stretch gap-3 md:flex-row md:items-center md:gap-3">
        {/* Step 1 — Signals */}
        <motion.div
          className="flex-1 rounded-panel border border-line bg-raised/60 p-5 backdrop-blur"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-40px" }}
          transition={{ duration: 0.5 }}
        >
          <StepBadge n="1" label={t("decision.signals")} />
          <div className="mt-4 flex flex-wrap gap-2">
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
                  className="inline-flex items-center gap-1.5 rounded-chip border border-line-soft bg-abyss/40 px-2.5 py-1"
                  initial={{ opacity: 0, scale: 0.9 }}
                  whileInView={{ opacity: 1, scale: 1 }}
                  viewport={{ once: true, margin: "-40px" }}
                  transition={{ duration: 0.3, delay: 0.1 + i * 0.06 }}
                >
                  <span style={{ color }}>{Icon && <Icon size={14} />}</span>
                  <span className="font-display text-[9px] font-semibold uppercase tracking-wide text-ink">
                    {analysis.agent}
                  </span>
                  <span className={cn("font-mono text-[9px] font-bold", biasColor)}>
                    {analysis.bias} {analysis.confidence.toFixed(0)}%
                  </span>
                </motion.span>
              );
            })}
          </div>
        </motion.div>

        <ArrowRight />
        <ArrowDown />

        {/* Step 2 — Master thesis */}
        <motion.div
          className="flex-1 rounded-panel border border-accent/25 bg-raised/60 p-5 backdrop-blur"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-40px" }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <StepBadge n="2" label={t("decision.masterThesis")} />
          <div className="mt-4 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-sm font-bold text-ink">
                {decision.asset}
              </span>
              <span
                className={cn(
                  "rounded-chip border px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-widest",
                  decision.bias === "BULLISH"
                    ? "border-up/30 bg-up/10 text-up"
                    : decision.bias === "BEARISH"
                      ? "border-down/30 bg-down/10 text-down"
                      : "border-line bg-raised/50 text-ink-dim"
                )}
              >
                {decision.bias} · {decision.confidence.toFixed(0)}%
              </span>
            </div>
            <p className="text-xs leading-relaxed text-ink-dim">
              <span className="font-semibold text-accent">{decision.consensus}:</span>{" "}
              {decision.masterThesis}
            </p>
          </div>
        </motion.div>

        <ArrowRight />
        <ArrowDown />

        {/* Step 3 — Risk gates */}
        <motion.div
          className="flex-1 rounded-panel border border-line bg-raised/60 p-5 backdrop-blur"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-40px" }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <StepBadge n="3" label={t("decision.riskGates")} />
                    <div className="mt-4 space-y-2">
                      {GATE_KEYS.map((gateKey, i) => (
                        <motion.div
                          key={gateKey}
                          className="flex items-center gap-2 rounded-chip border border-line-soft bg-abyss/40 px-2.5 py-1.5"
                          initial={{ opacity: 0, x: 8 }}
                          whileInView={{ opacity: 1, x: 0 }}
                          viewport={{ once: true, margin: "-40px" }}
                          transition={{ duration: 0.3, delay: 0.25 + i * 0.05 }}
                        >
                          <svg
                            className="h-3 w-3 shrink-0 text-up"
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
                          <span className="font-mono text-[10px] font-semibold uppercase tracking-wide text-ink">
                            {t(gateKey)}
                          </span>
                        </motion.div>
                      ))}

            {/* Result */}
            <motion.div
              className="flex items-center justify-center gap-2 rounded-chip border border-up/30 bg-up/10 py-2"
              initial={{ opacity: 0, scale: 0.92 }}
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
                              {t("decision.approved")}
                            </span>
            </motion.div>
          </div>
        </motion.div>
      </div>

      <p className="mt-4 text-center font-mono text-[9px] uppercase tracking-[0.2em] text-warn">
              {t("decision.simulatedData")}
            </p>
    </div>
  );
}
