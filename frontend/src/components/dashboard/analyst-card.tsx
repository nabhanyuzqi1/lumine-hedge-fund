import type { SignalPoint } from "@/data/fixtures";
import { Badge } from "@/components/ui/badge";

const ANALYST_LABEL: Record<string, string> = {
  technical_analyst: "Technical",
  macro_analyst: "Macro",
  news_analyst: "News",
  smc_analyst: "SMC",
};

const DIRECTION_TONE: Record<string, "ok" | "danger" | "neutral"> = {
  bullish: "ok",
  bearish: "danger",
  neutral: "neutral",
};

/**
 * AnalystCard (F-05): one analyst's directional view with confidence.
 * Pure presentational — fed by SignalPanel or SSE events.
 */
export function AnalystCard({ signal }: { signal: SignalPoint }) {
  const direction = signal.direction ?? "neutral";
  return (
    <div
      className="flex items-center justify-between rounded-chip border border-border-subtle bg-bg-base px-2.5 py-1.5"
      data-testid={`analyst-card-${signal.analyst}`}
    >
      <div className="min-w-0">
        <p className="truncate text-xs font-medium text-text-primary">
          {ANALYST_LABEL[signal.analyst] ?? signal.analyst}
        </p>
        <p className="truncate text-[11px] text-text-tertiary">{signal.rationale}</p>
      </div>
      <div className="ml-2 flex shrink-0 items-center gap-2">
        <Badge tone={DIRECTION_TONE[direction]} label={direction} />
        <span className="font-mono text-xs text-text-secondary">
          {Math.round((signal.confidence ?? 0) * 100)}%
        </span>
      </div>
    </div>
  );
}
