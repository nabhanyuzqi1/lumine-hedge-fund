import { Badge } from "@/components/ui/badge";

export interface DecisionView {
  action: string;
  confidence: number;
  timestamp: string;
  rationale?: string;
}

const ACTION_TONE: Record<string, "ok" | "danger" | "neutral"> = {
  buy: "ok",
  sell: "danger",
  hold: "neutral",
};

/**
 * DecisionCard (F-05): the Investment Committee's consolidated decision.
 * Pure presentational — fed by SSE ic-decisions events or committee feed.
 */
export function DecisionCard({ decision }: { decision: DecisionView }) {
  const tone = ACTION_TONE[decision.action] ?? "neutral";
  return (
    <div
      className="rounded-panel border border-border-subtle bg-bg-raised p-3"
      data-testid="decision-card"
    >
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-text-primary">Committee Decision</p>
        <Badge tone={tone} label={decision.action} />
      </div>
      <p className="mt-1 font-mono text-lg text-text-primary">
        {Math.round(decision.confidence * 100)}% confidence
      </p>
      {decision.rationale && (
        <p className="mt-1 text-[11px] leading-relaxed text-text-tertiary">{decision.rationale}</p>
      )}
      <p className="mt-1 font-mono text-[10px] text-text-tertiary">{decision.timestamp}</p>
    </div>
  );
}
