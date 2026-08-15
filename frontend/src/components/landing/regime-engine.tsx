import { cn } from "@/lib/utils";
import { MARKET_REGIME } from "@/data/landing/performance";

interface RegimeBarProps {
  regime: string;
  strength: number;
  description: string;
}

function RegimeBar({ regime, strength, description }: RegimeBarProps) {
  const getColor = () => {
    if (strength >= 70) return "bg-accent";
    if (strength >= 50) return "bg-up";
    if (strength >= 30) return "bg-warn";
    return "bg-ink-faint";
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-xs font-semibold uppercase tracking-widest text-ink">
          {regime}
        </span>
        <span className="font-mono text-xs text-ink-dim">{strength}%</span>
      </div>
      <div className="relative h-2 overflow-hidden rounded-full bg-raised">
        <div
          className={cn("h-full transition-all duration-500", getColor())}
          style={{ width: `${strength}%` }}
        />
      </div>
      <p className="text-[11px] leading-relaxed text-ink-dim">{description}</p>
    </div>
  );
}

interface RegimeEngineProps {
  className?: string;
}

export function RegimeEngine({ className }: RegimeEngineProps) {
  const regimes = MARKET_REGIME;

  return (
    <div className={cn("w-full max-w-4xl space-y-6", className)}>
      <div className="space-y-3 text-center">
        <div className="flex items-center justify-center gap-2">
          <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
          <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
            Market Regime Engine
          </span>
          <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
        </div>
        <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
          Markets Change.
          <br />
          Lumine Adapts.
        </h3>
        <p className="mx-auto max-w-2xl text-sm leading-relaxed text-ink-dim">
          Markets transition between trending, ranging, high volatility, and risk regimes.
        </p>
      </div>

      <div className="rounded-panel border border-line bg-raised shadow-panel">
        <div className="space-y-6 p-6 md:p-8">
          <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
            Current Market Regime
          </div>
          <div className="space-y-5">
            {regimes.map((regime, i) => (
              <RegimeBar key={i} {...regime} />
            ))}
          </div>
        </div>

        <div className="border-t border-warn/20 bg-warn/5 px-4 py-2 md:px-6">
          <span className="font-mono text-[9px] font-semibold uppercase tracking-widest text-warn">
            SIMULATED DATA
          </span>
        </div>
      </div>
    </div>
  );
}
