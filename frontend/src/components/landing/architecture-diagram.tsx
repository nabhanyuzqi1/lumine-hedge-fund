import { cn } from "@/lib/utils";

/**
 * ArchitectureDiagram — Section 18 of master prompt.
 * System architecture visualization showing data flow from market to execution.
 */

interface ArchitectureDiagramProps {
  className?: string;
}

export function ArchitectureDiagram({ className }: ArchitectureDiagramProps) {
  return (
    <div className={cn("w-full max-w-4xl space-y-6", className)}>
      <div className="space-y-3 text-center">
        <div className="flex items-center justify-center gap-2">
          <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
          <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
            System Architecture
          </span>
          <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
        </div>
        <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
          Built as Infrastructure,
          <br />
          Not a Script.
        </h3>
      </div>

      <div className="rounded-panel border border-line bg-raised shadow-panel">
        <div className="overflow-x-auto p-6 md:p-8">
          <div className="flex min-w-max flex-col items-center gap-4 font-mono text-xs">
            {/* Market Data */}
            <div className="rounded-chip border border-accent/30 bg-accent/10 px-6 py-3 backdrop-blur">
              <span className="font-semibold uppercase tracking-widest text-accent">
                Market Data
              </span>
            </div>

            <div className="h-6 w-px bg-accent" />

            {/* Data Engine */}
            <div className="rounded-chip border border-line bg-raised px-6 py-3">
              <span className="font-semibold uppercase tracking-widest text-ink">
                Data Engine
              </span>
            </div>

            <div className="h-6 w-px bg-accent" />

            {/* Agents layer */}
            <div className="flex gap-4">
              {["Technical", "Macro", "News", "Structure"].map((agent) => (
                <div
                  key={agent}
                  className="rounded-chip border border-line-soft bg-raised/50 px-4 py-2"
                >
                  <span className="text-[10px] uppercase tracking-widest text-ink-dim">
                    {agent}
                  </span>
                </div>
              ))}
            </div>

            <div className="h-6 w-px bg-accent" />

            {/* Master Intelligence */}
            <div className="rounded-chip border border-accent bg-accent/20 px-6 py-3 backdrop-blur">
              <span className="font-bold uppercase tracking-widest text-accent">
                Master Intelligence
              </span>
            </div>

            <div className="h-6 w-px bg-accent" />

            {/* Deterministic Validator */}
            <div className="rounded-chip border border-line bg-raised px-6 py-3">
              <span className="font-semibold uppercase tracking-widest text-ink">
                Deterministic Validator
              </span>
            </div>

            <div className="h-6 w-px bg-accent" />

            {/* Risk Engine */}
            <div className="rounded-chip border border-accent/30 bg-accent/10 px-6 py-3 backdrop-blur">
              <span className="font-bold uppercase tracking-widest text-accent">
                Risk Engine
              </span>
            </div>

            <div className="h-6 w-px bg-accent" />

            {/* Execution Engine */}
            <div className="rounded-chip border border-line bg-raised px-6 py-3">
              <span className="font-semibold uppercase tracking-widest text-ink">
                Execution Engine
              </span>
            </div>

            <div className="h-6 w-px bg-accent" />

            {/* Performance */}
            <div className="rounded-chip border border-up/30 bg-up/10 px-6 py-3 backdrop-blur">
              <span className="font-semibold uppercase tracking-widest text-up">
                Performance
              </span>
            </div>

            <div className="h-6 w-px bg-accent" />

            {/* Feedback Loop */}
            <div className="rounded-chip border border-line-soft bg-raised/50 px-6 py-3">
              <span className="text-[10px] uppercase tracking-widest text-ink-dim">
                Feedback Loop
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
