import { useShallow } from "zustand/react/shallow";

import { useStreamStore } from "@/stores/streamStore";
import { StreamStatusDot } from "./stream-status-dot";

/**
 * Compact per-stream status row (GAP F-02). Consumes the same store the
 * TopBar aggregate reads, so both stay in sync with the SSE layer.
 */
export function StreamStatusList() {
  const streams = useStreamStore(useShallow((s) => s.getAllStreams()));

  if (streams.length === 0) {
    return (
      <span className="text-[11px] text-text-tertiary" data-testid="stream-status-empty">
        no streams subscribed
      </span>
    );
  }

  return (
    <span
      className="inline-flex items-center gap-2"
      data-testid="stream-status-list"
    >
      {streams.map((state) => (
        <StreamStatusDot key={state.key} state={state} showLabel />
      ))}
    </span>
  );
}
