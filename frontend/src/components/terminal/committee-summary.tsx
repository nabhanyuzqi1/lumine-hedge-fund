import { useShallow } from "zustand/react/shallow";

import { Badge } from "@/components/ui/badge";
import { useCommitteeStore } from "@/stores/committeeStore";

/**
 * CommitteeDecisionSummary (19 Aug 2026 — ara #25): ringkasan verdict
 * komite terakhir. Menampilkan final decision (direction + confidence)
 * dari IC + CIO + risk terakhir. Detail lengkap di trace (workflow run).
 */
export function CommitteeDecisionSummary() {
  const activities = useCommitteeStore(useShallow((s) => s.getActivities()));

  const latest = (type: string) =>
    [...activities].reverse().find((a) => a.type === type);

  const ic = latest("ic_decision");
  const cio = latest("cio_proposal");
  const risk = latest("risk_assessment");

  const hasAny = ic || cio || risk;
  if (!hasAny) return null;

  return (
    <div
      className="mb-2 grid grid-cols-3 gap-2 rounded-md border border-border-subtle bg-bg-raised px-2.5 py-2"
      data-testid="committee-summary"
    >
      <SummaryCell label="IC Decision" value={ic?.decision} confidence={ic?.confidence} tone="ok" />
      <SummaryCell label="CIO Proposal" value={cio?.decision} confidence={cio?.confidence} tone="warn" />
      <SummaryCell label="Risk" value={risk?.decision} tone="danger" />
    </div>
  );
}

function SummaryCell({
  label,
  value,
  confidence,
  tone,
}: {
  label: string;
  value?: string;
  confidence?: number;
  tone: "ok" | "warn" | "danger";
}) {
  const dir = (value ?? "").toString().toUpperCase();
  return (
    <div className="min-w-0">
      <p className="text-[10px] uppercase tracking-wide text-text-tertiary">{label}</p>
      <div className="mt-0.5 flex items-baseline gap-1.5">
        <Badge tone={tone} label={dir || "—"} />
        {confidence !== undefined && (
          <span className="font-mono text-[11px] tabular-nums text-text-secondary">
            {confidence.toFixed(2)}
          </span>
        )}
      </div>
    </div>
  );
}
