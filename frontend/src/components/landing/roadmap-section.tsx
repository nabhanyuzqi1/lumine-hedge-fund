import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { ROADMAP } from "@/data/landing/roadmap";

/**
 * RoadmapSection — compact progress bar (UI/UX V2, Miller ≤7 units).
 * 1 baris: 6 segmen berwarna (status) + label fase + 1 baris summary.
 * Detail per fase dihilangkan — arah pengembangan langsung terbaca.
 */

const STATUS_COLOR: Record<string, string> = {
  COMPLETE: "bg-up",
  IN_PROGRESS: "bg-accent",
  PLANNED: "bg-line",
};

const STATUS_LABEL: Record<string, string> = {
  COMPLETE: "Complete",
  IN_PROGRESS: "In Progress",
  PLANNED: "Planned",
};

interface RoadmapSectionProps {
  className?: string;
  showHeader?: boolean;
}

export function RoadmapSection({ className, showHeader = true }: RoadmapSectionProps) {
  const counts = ROADMAP.reduce<Record<string, number>>(
    (acc, p) => {
      acc[p.status] = (acc[p.status] ?? 0) + 1;
      return acc;
    },
    {}
  );

  return (
    <div className={cn("w-full max-w-4xl space-y-6", className)}>
      {showHeader && (
        <div className="space-y-3 text-center">
          <div className="flex items-center justify-center gap-2">
            <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
              Roadmap
            </span>
            <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
          </div>
          <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
            Built in phases. Verified at every step.
          </h3>
        </div>
      )}

      <motion.div
        className="rounded-panel border border-line bg-raised/50 p-6 shadow-panel backdrop-blur"
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.6, ease: "easeOut" }}
      >
        {/* Summary — 1 baris */}
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
            Development Status
          </div>
          <div className="flex items-center gap-4 font-mono text-[10px]">
            <span className="flex items-center gap-1.5 text-up">
              <span className="h-1.5 w-1.5 rounded-full bg-up" />
              {counts.COMPLETE ?? 0} complete
            </span>
            <span className="flex items-center gap-1.5 text-accent">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" />
              {counts.IN_PROGRESS ?? 0} in progress
            </span>
            <span className="flex items-center gap-1.5 text-ink-faint">
              <span className="h-1.5 w-1.5 rounded-full bg-line" />
              {counts.PLANNED ?? 0} planned
            </span>
          </div>
        </div>

        {/* Progress bar — 6 segmen */}
        <div className="flex gap-1">
          {ROADMAP.map((phase, i) => (
            <motion.div
              key={phase.phase}
              className="group relative flex-1 cursor-default"
              initial={{ opacity: 0, scaleY: 0.4 }}
              whileInView={{ opacity: 1, scaleY: 1 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.4, delay: i * 0.06 }}
            >
              <div
                className={cn(
                  "h-2.5 rounded-sm transition-opacity group-hover:opacity-80",
                  STATUS_COLOR[phase.status]
                )}
                style={{ opacity: phase.status === "PLANNED" ? 0.45 : 1 }}
              />
              <div className="mt-2 text-center">
                <div className="font-mono text-[8px] font-semibold uppercase tracking-wider text-ink-faint">
                  P{phase.phase}
                </div>
                <div className="font-display text-[10px] font-semibold leading-tight text-ink-dim transition-colors group-hover:text-ink">
                  {phase.title}
                </div>
              </div>
              {/* Tooltip status */}
              <div className="pointer-events-none absolute -top-7 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-chip border border-line bg-abyss px-2 py-0.5 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                <span
                  className={cn(
                    "font-mono text-[8px] font-semibold uppercase tracking-widest",
                    phase.status === "COMPLETE"
                      ? "text-up"
                      : phase.status === "IN_PROGRESS"
                        ? "text-accent"
                        : "text-ink-faint"
                  )}
                >
                  {STATUS_LABEL[phase.status]}
                </span>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>

      {/* Footer disclaimer */}
      <div className="rounded-chip border border-accent/30 bg-accent/5 p-4 backdrop-blur">
        <p className="text-center text-xs leading-relaxed text-ink-dim">
          <span className="font-semibold text-accent">Honest roadmap.</span> Future
          phases are marked appropriately. We do not imply that unfinished features
          already exist.
        </p>
      </div>
    </div>
  );
}
