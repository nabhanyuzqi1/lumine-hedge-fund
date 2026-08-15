import { cn } from "@/lib/utils";
import { SAMPLE_TRADE_AUDIT } from "@/data/landing/trades";

interface AuditRowProps {
  label: string;
  value: string | number;
  valueColor?: string;
}

function AuditRow({ label, value, valueColor = "text-ink" }: AuditRowProps) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-line-soft py-2 last:border-0">
      <span className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
        {label}
      </span>
      <span className={cn("font-mono text-xs font-semibold", valueColor)}>
        {value}
      </span>
    </div>
  );
}

interface AuditLogProps {
  className?: string;
}

export function AuditLog({ className }: AuditLogProps) {
  const audit = SAMPLE_TRADE_AUDIT;

  const formatTimestamp = (iso: string) => {
    const date = new Date(iso);
    return date.toISOString().replace("T", " ").slice(0, 19) + " UTC";
  };

  const getBiasColor = (bias: string) => {
    if (bias === "BULLISH") return "text-up";
    if (bias === "BEARISH") return "text-down";
    return "text-ink-dim";
  };

  return (
    <div className={cn("w-full max-w-4xl space-y-6", className)}>
      <div className="space-y-3 text-center">
        <div className="flex items-center justify-center gap-2">
          <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
          <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
            Auditability
          </span>
          <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
        </div>
        <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
          Every Decision Leaves a Trace.
        </h3>
        <p className="mx-auto max-w-2xl text-sm leading-relaxed text-ink-dim">
          From signal to execution, every decision is logged with complete context.
        </p>
      </div>

      <div className="rounded-panel border border-line bg-raised shadow-panel">
        <div className="border-b border-line-soft bg-abyss/50 p-4 md:p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
                Trade ID
              </div>
              <div className="font-mono text-lg font-bold text-accent">
                {audit.tradeId}
              </div>
            </div>
            <div className="rounded-chip border border-accent/30 bg-accent/10 px-3 py-1.5">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-accent">
                {audit.side}
              </span>
            </div>
          </div>
        </div>

        <div className="grid gap-6 p-4 md:grid-cols-2 md:p-6">
          <div className="space-y-4">
            <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
              Trade Context
            </div>
            <div className="space-y-0">
              <AuditRow label="Timestamp" value={formatTimestamp(audit.timestamp)} />
              <AuditRow label="Asset" value={audit.asset} valueColor="text-accent" />
              <AuditRow label="Regime" value={audit.regime} />
              <AuditRow label="Confidence" value={`${audit.confidence.toFixed(1)}%`} valueColor="text-accent" />
              <AuditRow label="Risk %" value={`${audit.riskPercent.toFixed(2)}%`} />
            </div>
          </div>

          <div className="space-y-4">
            <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
              Agent Analyses
            </div>
            <div className="space-y-0">
              <AuditRow label="Technical" value={audit.technical} valueColor={getBiasColor(audit.technical)} />
              <AuditRow label="Macro" value={audit.macro} valueColor={getBiasColor(audit.macro)} />
              <AuditRow label="News" value={audit.news} valueColor={getBiasColor(audit.news)} />
              <AuditRow label="Structure" value={audit.structure} valueColor={getBiasColor(audit.structure)} />
              <AuditRow label="Master Thesis" value={audit.masterThesis} valueColor={getBiasColor(audit.masterThesis)} />
            </div>
          </div>

          <div className="space-y-4 md:col-span-2">
            <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
              Execution Parameters
            </div>
            <div className="grid gap-0 sm:grid-cols-3">
              <AuditRow label="Entry" value={audit.entry.toFixed(2)} />
              <AuditRow label="Stop" value={audit.stop.toFixed(2)} />
              <AuditRow label="Target" value={audit.target.toFixed(2)} />
            </div>
          </div>
        </div>

        <div className="border-t border-line-soft bg-abyss/50 px-4 py-3 md:px-6">
          <div className="flex items-center justify-between gap-4">
            <span className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
              Status
            </span>
            <div className="rounded-chip border border-warn/30 bg-warn/10 px-2.5 py-1">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-warn">
                {audit.status}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-chip border border-accent/30 bg-accent/5 p-4 backdrop-blur">
        <p className="text-center text-xs leading-relaxed text-ink-dim">
          <span className="font-semibold text-accent">
            Institutional-grade auditability.
          </span>{" "}
          Every trade links back to the models, prompts, and data that produced it.
        </p>
      </div>
    </div>
  );
}
