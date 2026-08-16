import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

/**
 * Strategy Lifecycle — simple 6-row checklist (V2.5).
 * Scroll-driven stepper was removed (auto-advancing content felt
 * uncontrolled). Now: one compact vertical list, every stage visible
 * at once — zero interaction required, zero ambiguity.
 * Progress state shown with a left accent + status dot per row.
 */

interface Stage {
  number: string;
  titleKey: string;
  descKey: string;
  state: "complete" | "active" | "pending";
}

const STAGES: Stage[] = [
  { number: "01", titleKey: "research.stage01Title", descKey: "research.stage01Description", state: "complete" },
  { number: "02", titleKey: "research.stage02Title", descKey: "research.stage02Description", state: "complete" },
  { number: "03", titleKey: "research.stage03Title", descKey: "research.stage03Description", state: "active" },
  { number: "04", titleKey: "research.stage04Title", descKey: "research.stage04Description", state: "pending" },
  { number: "05", titleKey: "research.stage05Title", descKey: "research.stage05Description", state: "pending" },
  { number: "06", titleKey: "research.stage06Title", descKey: "research.stage06Description", state: "pending" },
];

const STATE_STYLE: Record<Stage["state"], { dot: string; label: string }> = {
  complete: { dot: "bg-up", label: "text-up" },
  active: { dot: "bg-accent animate-pulse", label: "text-accent" },
  pending: { dot: "bg-line", label: "text-ink-faint" },
};

const STATE_LABEL: Record<Stage["state"], string> = {
  complete: "research.stateDone",
  active: "research.stateCurrent",
  pending: "research.statePending",
};

interface ResearchPipelineProps {
  className?: string;
  showHeader?: boolean;
}

export function ResearchPipeline({ className, showHeader = true }: ResearchPipelineProps) {
  const { t } = useTranslation();
  return (
    <div className={cn("mx-auto w-full max-w-4xl space-y-6", className)}>
      {showHeader && (
        <div className="space-y-3 text-center">
          <div className="flex items-center justify-center gap-2">
            <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
              {t("research.strategyLifecycle")}
            </span>
            <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
          </div>
          <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
            {t("research.fromHypothesis")}
          </h3>
          <p className="mx-auto max-w-2xl text-sm leading-relaxed text-ink-dim">
            {t("research.lifecycleDescription")}
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
                                      {t(stage.titleKey)}
                                    </span>
                                    <span className="flex items-center gap-1.5 font-mono text-[8px] font-semibold uppercase tracking-[0.18em] text-ink-faint">
                                      <span className={cn("h-1 w-1 rounded-full", style.dot)} />
                                      {t(STATE_LABEL[stage.state])}
                                    </span>
                                  </div>
                                  <p className="mt-0.5 truncate text-xs leading-relaxed text-ink-dim md:text-[13px]">
                                    {t(stage.descKey)}
                                  </p>
              </div>
            </motion.div>
          );
        })}
      </motion.div>
    </div>
  );
}
