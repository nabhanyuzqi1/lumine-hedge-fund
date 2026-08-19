import { useDXY } from "@/api/hooks";

/**
 * DXYBadge (19 Aug 2026 P1) — DXY (US Dollar Index) contextual info di
 * Terminal header. Menampilkan price + source + stale state (bukan
 * placeholder). Emas bergerak inverse terhadap DXY → konteks penting.
 */
export function DXYBadge() {
  const { data, isError, isFetching } = useDXY();

  if (isError) {
    return (
      <span
        className="rounded-chip border border-line bg-bg px-2 py-0.5 font-mono text-[10px] text-ink-faint"
        title="DXY feed error"
      >
        DXY — error
      </span>
    );
  }

  const price = data?.price;
  return (
    <span
      className="rounded-chip border border-line bg-bg px-2 py-0.5 font-mono text-[10px] text-ink"
      title={data?.source ? `DXY (US Dollar Index) — source: ${data.source}` : "DXY (US Dollar Index)"}
    >
      <span className="text-ink-faint">DXY</span>{" "}
      {price != null ? price.toFixed(2) : "—"}
      {isFetching ? <span className="ml-1 text-ink-faint">·</span> : null}
    </span>
  );
}
