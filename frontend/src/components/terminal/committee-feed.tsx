import { useShallow } from "zustand/react/shallow";

import { Badge } from "@/components/ui/badge";
import { type CommitteeActivity, useCommitteeStore } from "@/stores/committeeStore";

const TYPE_TONE: Record<CommitteeActivity["type"], "info" | "ok" | "warn" | "danger"> = {
  analyst_output: "info",
  ic_decision: "ok",
  cio_proposal: "warn",
  risk_assessment: "danger",
};

const TYPE_LABEL: Record<CommitteeActivity["type"], string> = {
  analyst_output: "Analyst",
  ic_decision: "IC",
  cio_proposal: "CIO",
  risk_assessment: "Risk",
};

/**
 * Live committee feed (W1 right panel, W3 run detail): newest first,
 * optionally filtered by a workflow run. Decoration `timestamp` — the
 * SSE contract's `meta.timestamp` replaces it once live.
 */
export function CommitteeFeed({
  workflowRunId,
  limit = 30,
}: {
  workflowRunId?: string;
  limit?: number;
}) {
  const activities = useCommitteeStore(useShallow((s) => s.getActivities()));
  const filtered = workflowRunId
    ? activities.filter((a) => a.workflow_run_id === workflowRunId)
    : activities;

  const shown = [...filtered].reverse().slice(0, limit);

  if (shown.length === 0) {
      return (
        <div data-testid="committee-empty" className="space-y-2">
          <p className="py-3 text-center text-xs text-text-tertiary">
            Belum ada aktivitas komite pada sesi ini.
          </p>
        </div>
      );
    }

  return (
    <ul
      className="max-h-72 space-y-2 overflow-y-auto overscroll-none pr-1"
      data-testid="committee-feed"
    >
      {shown.map((activity) => (
        <li
          key={activity.id}
          className="rounded-md border border-border-subtle bg-bg-raised px-2.5 py-2"
        >
          <div className="flex items-center justify-between gap-2">
            <Badge tone={TYPE_TONE[activity.type]} label={TYPE_LABEL[activity.type]} />
            <span className="font-mono text-[10px] tabular-nums text-text-tertiary">
              {new Date(activity.timestamp).toISOString().slice(11, 19)}Z
            </span>
          </div>
          {activity.agent && (
            <p className="mt-1 text-xs font-medium text-text-primary">{activity.agent}</p>
          )}
          {activity.decision && (
            <p className="mt-0.5 text-xs text-text-secondary">{activity.decision}</p>
          )}
          {activity.confidence !== undefined && (
            <p className="mt-0.5 font-mono text-xs tabular-nums text-text-secondary">
              confidence <span className="text-accent">{activity.confidence.toFixed(2)}</span>
            </p>
          )}
          {activity.workflow_run_id && workflowRunId === undefined && (
            <p className="mt-1 truncate font-mono text-[10px] text-text-tertiary">
              {activity.workflow_run_id}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
