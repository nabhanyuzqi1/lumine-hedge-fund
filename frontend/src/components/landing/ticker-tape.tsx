/**
 * TickerTape — Bloomberg-style marquee strip under the hero.
 * Reuses the `tape-scroll` keyframes from index.css (40s linear loop).
 * SIMULATED market data — clearly labeled.
 */

interface TickerItem {
  symbol: string;
  price: string;
  change: string;
  up: boolean;
}

const TICKER: TickerItem[] = [
  { symbol: "XAUUSD", price: "3350.20", change: "+0.42%", up: true },
  { symbol: "XAGUSD", price: "39.84", change: "+0.91%", up: true },
  { symbol: "EURUSD", price: "1.0842", change: "-0.15%", up: false },
  { symbol: "GBPUSD", price: "1.2715", change: "+0.08%", up: true },
  { symbol: "USOIL", price: "78.42", change: "-0.63%", up: false },
  { symbol: "BTCUSD", price: "61240", change: "+1.24%", up: true },
  { symbol: "US10Y", price: "4.212", change: "+0.03%", up: true },
  { symbol: "USDJPY", price: "149.62", change: "-0.22%", up: false },
];

function TickerRow({ items }: { items: TickerItem[] }) {
  return (
    <div className="flex shrink-0 items-center">
      {items.map((item, i) => (
        <span
          key={`${item.symbol}-${i}`}
          className="mx-6 inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.15em]"
        >
          <span className="text-ink">{item.symbol}</span>
          <span className="text-ink-dim">{item.price}</span>
          <span className={item.up ? "text-up" : "text-down"}>
            {item.change}
          </span>
          <span className="ml-4 h-px w-6 bg-line" />
        </span>
      ))}
    </div>
  );
}

export function TickerTape() {
  return (
    <div className="relative overflow-hidden border-b border-line bg-abyss/80 py-2.5">
      <div className="flex w-max animate-[tape-scroll_40s_linear_infinite]">
        <TickerRow items={TICKER} />
        <TickerRow items={TICKER} />
      </div>
      {/* Edge fades */}
      <div className="pointer-events-none absolute inset-y-0 left-0 w-16 bg-gradient-to-r from-abyss to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-abyss to-transparent" />
    </div>
  );
}
