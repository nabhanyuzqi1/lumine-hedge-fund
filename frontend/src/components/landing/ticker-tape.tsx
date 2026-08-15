import { useEffect, useState } from "react";

/**
 * TickerTape — Bloomberg-style marquee strip under the hero.
 * XAUUSD is the primary instrument (Lumine's focus) with a simulated
 * realtime price that ticks every ~2s. Other instruments are static
 * context. Clearly labeled SIMULATED FEED.
 */

interface TickerItem {
  symbol: string;
  price: string;
  change: string;
  up: boolean;
}

const CONTEXT_ITEMS: TickerItem[] = [
  { symbol: "XAGUSD", price: "39.84", change: "+0.91%", up: true },
  { symbol: "EURUSD", price: "1.0842", change: "-0.15%", up: false },
  { symbol: "GBPUSD", price: "1.2715", change: "+0.08%", up: true },
  { symbol: "USOIL", price: "78.42", change: "-0.63%", up: false },
  { symbol: "BTCUSD", price: "61240", change: "+1.24%", up: true },
  { symbol: "US10Y", price: "4.212", change: "+0.03%", up: true },
  { symbol: "USDJPY", price: "149.62", change: "-0.22%", up: false },
];

export function TickerTape() {
  // Simulated realtime XAUUSD price (random walk around 3350).
  const [xau, setXau] = useState(3350.2);

  useEffect(() => {
    const id = setInterval(() => {
      setXau((prev) => {
        const drift = (Math.random() - 0.48) * 1.6;
        return Math.max(3340, Math.min(3362, prev + drift));
      });
    }, 2000);
    return () => clearInterval(id);
  }, []);

  const changePct = ((xau - 3350.2) / 3350.2) * 100;
  const xauUp = changePct >= 0;

  return (
    <div className="relative overflow-hidden border-b border-line bg-abyss/80 py-2.5">
      <div className="flex w-max animate-[tape-scroll_40s_linear_infinite]">
        {/* XAUUSD — primary, highlighted */}
        <span className="mx-6 inline-flex shrink-0 items-center gap-2.5 font-mono text-[11px] uppercase tracking-[0.15em]">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
            <span className="font-bold text-ink">XAUUSD</span>
          </span>
          <span className="font-bold tabular-nums text-ink">{xau.toFixed(2)}</span>
          <span className={xauUp ? "text-up" : "text-down"}>
            {xauUp ? "▲" : "▼"} {Math.abs(changePct).toFixed(2)}%
          </span>
          <span className="ml-4 h-px w-6 bg-line" />
        </span>

        {/* Context instruments */}
        {[...CONTEXT_ITEMS, ...CONTEXT_ITEMS].map((item, i) => (
          <span
            key={`${item.symbol}-${i}`}
            className="mx-6 inline-flex shrink-0 items-center gap-2 font-mono text-[10px] uppercase tracking-[0.15em]"
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

      {/* SIMULATED feed label */}
      <div className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 rounded-chip border border-warn/25 bg-abyss/90 px-2 py-0.5">
        <span className="font-mono text-[8px] font-semibold uppercase tracking-[0.2em] text-warn">
          Simulated Feed
        </span>
      </div>

      {/* Edge fades */}
      <div className="pointer-events-none absolute inset-y-0 left-0 w-16 bg-gradient-to-r from-abyss to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-abyss to-transparent" />
    </div>
  );
}
