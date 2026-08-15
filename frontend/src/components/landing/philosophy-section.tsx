import { cn } from "@/lib/utils";

/**
 * PhilosophySection — Section 20 of master prompt.
 * Cinematic minimalist philosophy section.
 * Large typography with the core philosophy statements.
 */

interface PhilosophySectionProps {
  className?: string;
}

export function PhilosophySection({ className }: PhilosophySectionProps) {
  return (
    <div className={cn("w-full max-w-5xl space-y-20 py-20", className)}>
      {/* Statement 1 */}
      <div className="space-y-6 text-center">
        <div className="font-display text-3xl font-bold leading-tight text-ink-dim md:text-5xl lg:text-6xl">
          Markets are uncertain.
        </div>
      </div>

      {/* Statement 2 */}
      <div className="space-y-6 text-center">
        <div className="font-display text-3xl font-bold leading-tight text-ink-dim md:text-5xl lg:text-6xl">
          Models can be wrong.
        </div>
      </div>

      {/* Statement 3 */}
      <div className="space-y-6 text-center">
        <div className="font-display text-3xl font-bold leading-tight text-ink-dim md:text-5xl lg:text-6xl">
          Strategies decay.
        </div>
      </div>

      {/* Statement 4 */}
      <div className="space-y-6 text-center">
        <div className="font-display text-3xl font-bold leading-tight text-ink-dim md:text-5xl lg:text-6xl">
          Risk is not optional.
        </div>
      </div>

      {/* Final statement */}
      <div className="space-y-8 text-center">
        <div className="mx-auto h-px w-24 bg-gradient-to-r from-transparent via-accent to-transparent" />
        <div className="font-display text-4xl font-bold leading-tight text-ink md:text-6xl lg:text-7xl">
          We engineer systems
          <br />
          that adapt to uncertainty.
        </div>
        <div className="mx-auto h-px w-24 bg-gradient-to-r from-transparent via-accent to-transparent" />
      </div>
    </div>
  );
}
