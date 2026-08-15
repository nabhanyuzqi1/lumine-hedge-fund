import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { ROADMAP } from "@/data/landing/roadmap";

/**
 * RoadmapSection — Section 21 of master prompt.
 * "From Research to Autonomous Intelligence."
 * Shows development roadmap with honest status indicators.
 */

interface PhaseCardProps {
  phase: number;
  title: string;
  subtitle: string;
  description: string;
  status: "COMPLETE" | "IN_PROGRESS" | "PLANNED";
  milestones: string[];
}

function PhaseCard({ phase, title, subtitle, description, status, milestones }: PhaseCardProps) {
  const statusColors = {
    COMPLETE: "border-up bg-up/10 text-up",
    IN_PROGRESS: "border-accent bg-accent/10 text-accent",
    PLANNED: "border-line-soft bg-raised/30 text-ink-faint",
  };

  const statusLabels = {
    COMPLETE: "Complete",
    IN_PROGRESS: "In Progress",
    PLANNED: "Planned",
  };

  return (
    <div className="group rounded-panel border border-line bg-raised shadow-panel transition-all hover:border-accent/30 hover:shadow-lg">
      {/* Header */}
      <div className="border-b border-line-soft p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <span className="font-mono text-sm font-bold text-accent">
                Phase {phase}
              </span>
              <div className={cn("rounded-chip border px-2 py-0.5", statusColors[status])}>
                <span className="font-mono text-[9px] font-semibold uppercase tracking-widest">
                  {statusLabels[status]}
                </span>
              </div>
            </div>
            <h4 className="font-display text-xl font-bold text-ink">{title}</h4>
            <p className="text-sm text-ink-dim">{subtitle}</p>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="space-y-4 p-6">
        <p className="text-sm leading-relaxed text-ink-dim">{description}</p>

        {/* Milestones */}
        <div className="space-y-2">
          <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
            Key Milestones
          </div>
          <ul className="space-y-1.5">
            {milestones.map((milestone, i) => (
              <li key={i} className="flex items-start gap-2">
                <svg
                  className="mt-0.5 h-4 w-4 shrink-0 text-accent opacity-50"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 5l7 7-7 7"
                  />
                </svg>
                <span className="text-xs leading-relaxed text-ink-dim">{milestone}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

interface RoadmapSectionProps {
  className?: string;
  showHeader?: boolean;
}

export function RoadmapSection({ className, showHeader = true }: RoadmapSectionProps) {
  return (
    <div className={cn("w-full max-w-4xl space-y-6", className)}>
      {/* Header */}
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

      {/* Phases */}
      <div className="space-y-6">
        {ROADMAP.map((phase, i) => (
          <motion.div
            key={phase.phase}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ duration: 0.5, delay: (i % 3) * 0.1 }}
          >
            <PhaseCard {...phase} />
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
