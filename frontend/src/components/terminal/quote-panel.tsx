import { useShallow } from "zustand/react/shallow";

import { useQuote } from "@/api/hooks";
import { NumericText } from "@/components/ui/numeric-text";
import { useMarketStore } from "@/stores/marketStore";

/**
 * Quote panel: REST/fixture quote overlaid by the live tick from the
 * market store when streaming (demo) is active — the tick wins.
 */
export function QuotePanel({ symbol }: { symbol: string }) {
  const quote = useQuote(symbol);
  const liveTick = useMarketStore(useShallow((s) => s.getTick(symbol)));
  const history = useMarketStore(useShallow((s) => s.getHistory(symbol)));

  const bid = liveTick?.bid ?? quote.data?.bid;
  const ask = liveTick?.ask ?? quote.data?.ask;
  const last = liveTick?.last ?? quote.data?.last;
  const spread = bid !== undefined && ask !== undefined ? ask - bid : undefined;
  const high = liveTick ? Math.max(...history.map((t) => t.ask), liveTick.ask) : undefined;
  const low = liveTick ? Math.min(...history.map((t) => t.bid), liveTick.bid) : undefined;

  const rows: Array<{ label: string; node: React.ReactNode }> = [
    {
      label: "Last",
      node:
        last !== undefined ? (
          <NumericText value={last} decimals={2} tone="neutral" />
        ) : (
          <span>—</span>
        ),
    },
    {
      label: "Bid / Ask",
      node:
        bid !== undefined && ask !== undefined ? (
          <span className="flex gap-1.5 font-mono tabular-nums">
            <NumericText value={bid} decimals={2} tone="up" />
            <span className="text-text-tertiary">/</span>
            <NumericText value={ask} decimals={2} tone="down" />
          </span>
        ) : (
          <span>—</span>
        ),
    },
    {
      label: "Spread",
      node:
        spread !== undefined ? (
          <NumericText value={spread} decimals={2} tone="neutral" />
        ) : (
          <span>—</span>
        ),
    },
    {
      label: "Session H / L",
      node:
        high !== undefined && low !== undefined ? (
          <span className="flex gap-1.5 font-mono tabular-nums">
            <NumericText value={high} decimals={2} tone="up" />
            <span className="text-text-tertiary">/</span>
            <NumericText value={low} decimals={2} tone="down" />
          </span>
        ) : (
          <span>—</span>
        ),
    },
  ];

  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2" data-testid="quote-panel">
      {rows.map(({ label, node }) => (
        <div key={label} className="flex items-baseline justify-between gap-2">
          <dt className="text-[11px] uppercase tracking-wider text-text-secondary">{label}</dt>
          <dd className="min-w-0 text-right text-sm">{node}</dd>
        </div>
      ))}
    </dl>
  );
}
