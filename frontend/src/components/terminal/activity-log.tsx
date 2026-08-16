import { useShallow } from "zustand/react/shallow";

import { Badge } from "@/components/ui/badge";
import { type LogLevel, useActivityStore } from "@/stores/activityStore";

const LEVEL_TONE: Record<LogLevel, "info" | "ok" | "warn" | "danger"> = {
  info: "info",
  warn: "warn",
  danger: "danger",
};

/**
 * Stream/event activity log (W1 right column + W3 run detail): ring-buffer
 * entries from the activity store, newest first. SSE handlers and demo
 * streams both `appendLog` — identical code path.
 */
export function ActivityLog({ limit = 24 }: { limit?: number }) {
  const entries = useActivityStore(useShallow((s) => s.getEntries()));
  const shown = [...entries].reverse().slice(0, limit);

  if (shown.length === 0) {
    return (
      <p className="py-6 text-center text-xs text-text-tertiary" data-testid="activity-empty">
        No stream activity yet
      </p>
    );
  }

  return (
    <ul className="max-h-[320px] space-y-1 overflow-auto overscroll-none" data-testid="activity-log">
      {shown.map((entry) => (
        <li key={entry.id} className="flex items-start gap-2 rounded-md px-1.5 py-1">
          <Badge tone={LEVEL_TONE[entry.level]} label={entry.stream} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs text-text-secondary">{entry.message}</p>
            <p className="font-mono text-[10px] tabular-nums text-text-tertiary">
              {new Date(entry.timestamp).toISOString().slice(11, 19)}Z
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}
