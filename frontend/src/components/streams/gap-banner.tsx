import { useShallow } from "zustand/react/shallow";

import { useStreamStore } from "@/stores/streamStore";

/**
 * Realtime degradation banner (GAP F-02): shown whenever any subscribed SSE
 * channel is stale, erroring, or reconnecting. Renders nothing when all
 * streams are live — calm by default, loud on degradation.
 */
export function GapBanner() {
  const streams = useStreamStore(useShallow((s) => s.getAllStreams()));
  const degraded = streams.filter((s) => s.status === "error" || s.status === "stale");
  const reconnecting = streams.filter((s) => s.status === "connecting");

  if (degraded.length === 0 && reconnecting.length === 0) {
    return null;
  }

  const degradedNames = degraded.map((s) => s.key).join(", ");
  const reconnectingNames = reconnecting.map((s) => s.key).join(", ");
  const detail = [degradedNames && `gap: ${degradedNames}`, reconnectingNames && `reconnecting: ${reconnectingNames}`]
    .filter(Boolean)
    .join(" · ");

  return (
    <div
      role="status"
      data-testid="stream-gap-banner"
      className="flex items-center gap-2 border-b border-border-subtle bg-amber-500/10 px-3 py-1 text-[11px] text-amber-300"
    >
      <span aria-hidden="true">⚠</span>
      <span>Realtime feed degraded — {detail}.</span>
    </div>
  );
}
