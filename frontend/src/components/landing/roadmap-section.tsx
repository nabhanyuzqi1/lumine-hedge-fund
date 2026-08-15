import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { ROADMAP } from "@/data/landing/roadmap";

/**
 * RoadmapSection — compact horizontal timeline.
 * Density audit: 6 fase besar + milestones → chips ringkas dengan
 * status. Detail dihilangkan; visitor cukup melihat arah pengembangan.
 */

const STATUS_STYLE: Record<string, string> = {
  COMPLETE: "border-up/30 bg-up/10 text-up",
  IN_PROGRESS: "border-accent/30 bg-accent/10 text-accent",
  PLANNED: "border-line-soft bg-raised/30 text-ink-faint",
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
            From Research to
            <br />
            Autonomous Intelligence.
          </h3>
        </div>
      )}

      {/* Compact timeline */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {ROADMAP.map((phase, i) => (
          <motion.div
            key={phase.phase}
            className="rounded-panel border border-line bg-raised/50 p-4 backdrop-blur transition-colors hover:border-line hover:bg-raised"
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ duration: 0.4, delay: (i % 3) * 0.08 }}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[10px] font-bold uppercase tracking-widest text-accent">
                Phase {phase.phase}
              </span>
              <span
                className={cn(
                  "rounded-chip border px-2 py-0.5 font-mono text-[8px] font-semibold uppercase tracking-widest",
                  STATUS_STYLE[phase.status]
                )}
              >
                {STATUS_LABEL[phase.status]}
              </span>
            </div>
            <div className="mt-2 font-display text-sm font-semibold text-ink">
              {phase.title}
            </div>
            <div className="mt-0.5 text-[11px] leading-relaxed text-ink-dim">
              {phase.subtitle}
            </div>
          </motion.div>
        ))}
      </div>

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
