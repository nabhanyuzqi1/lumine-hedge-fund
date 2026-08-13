import type { StreamState } from "@/stores/streamStore";

const STATUS_COLOR: Record<StreamState["status"], string> = {
  idle: "bg-text-tertiary",
  connecting: "bg-amber-400",
  open: "bg-emerald-400",
  stale: "bg-amber-500",
  error: "bg-danger",
  closed: "bg-text-tertiary",
};

const STATUS_LABEL: Record<StreamState["status"], string> = {
  idle: "idle",
  connecting: "connecting",
  open: "live",
  stale: "stale",
  error: "error",
  closed: "closed",
};

interface StreamStatusDotProps {
  state: StreamState;
  /** Show the stream key label next to the dot (default: false). */
  showLabel?: boolean;
}

/**
 * Per-stream connection indicator (GAP F-02). Replaces the aggregate n/6
 * health number with one dot per SSE channel, color-coded by status.
 */
export function StreamStatusDot({ state, showLabel = false }: StreamStatusDotProps) {
  return (
    <span
      className="inline-flex items-center gap-1.5"
      data-testid={`stream-dot-${state.key}`}
      title={`${state.key}: ${STATUS_LABEL[state.status]}${
        state.error ? ` — ${state.error}` : ""
      }`}
    >
      <span
        className={`h-2 w-2 rounded-full ${STATUS_COLOR[state.status]}`}
        aria-hidden="true"
      />
      {showLabel && (
        <span className="text-[11px] text-text-secondary">{state.key}</span>
      )}
    </span>
  );
}
