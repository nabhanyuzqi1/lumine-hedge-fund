import { useMarketStore } from "@/stores";

/**
 * TickerTape — Bloomberg-style marquee strip under the hero.
 * Shows realtime prices from MT5 EA via WebSocket.
 * Falls back to simulated prices if no live data available.
 */

interface TickerItem {
  symbol: string;
  price: string;
  change: string;
  up: boolean;
  isLive?: boolean;
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

// Symbols to fetch from market store (prioritized)
const LIVE_SYMBOLS = ["XAUUSD", "BTCUSD", "EURUSD", "GBPUSD"];

// Base prices for change calculation (simulated baseline)
const BASE_PRICES: Record<string, number> = {
  XAUUSD: 3350.2,
  BTCUSD: 61240,
  EURUSD: 1.0842,
  GBPUSD: 1.2715,
};

export function TickerTape() {
  // Get live ticks from market store
  const ticks = useMarketStore((state) => state.ticks);
  
  // Build ticker items with live data when available
  const tickerItems: TickerItem[] = CONTEXT_ITEMS.map((item) => {
    const liveTick = ticks[item.symbol];
    if (liveTick) {
      const mid = (liveTick.bid + liveTick.ask) / 2;
      const basePrice = BASE_PRICES[item.symbol] || mid;
      const changePct = ((mid - basePrice) / basePrice) * 100;
      return {
        symbol: item.symbol,
        price: mid.toFixed(item.symbol === "BTCUSD" ? 1 : item.symbol.includes("JPY") ? 3 : 2),
        change: `${changePct >= 0 ? "+" : ""}${changePct.toFixed(2)}%`,
        up: changePct >= 0,
        isLive: true,
      };
    }
    return item;
  });
  
  // Check if we have any live data
  const hasLiveData = LIVE_SYMBOLS.some((sym) => ticks[sym]);
  
  // XAUUSD primary - use live data if available
  const xauTick = ticks["XAUUSD"];
  const xau = xauTick ? (xauTick.bid + xauTick.ask) / 2 : 3350.2;
  const xauBase = BASE_PRICES["XAUUSD"];
  const xauChangePct = ((xau - xauBase) / xauBase) * 100;
  const xauUp = xauChangePct >= 0;

  return (
    <div className="relative overflow-hidden border-b border-line bg-abyss/80 py-2.5">
      <div className="flex w-max animate-[tape-scroll_40s_linear_infinite]">
        {/* XAUUSD — primary, highlighted */}
        <span className="mx-6 inline-flex shrink-0 items-center gap-2.5 font-mono text-[11px] uppercase tracking-[0.15em]">
          <span className="inline-flex items-center gap-1.5">
            <span className={`h-1.5 w-1.5 rounded-full ${xauTick ? "bg-accent animate-pulse" : "bg-warn"}`} />
            <span className="font-bold text-ink">XAUUSD</span>
          </span>
          <span className="font-bold tabular-nums text-ink">{xau.toFixed(2)}</span>
          <span className={xauUp ? "text-up" : "text-down"}>
            {xauUp ? "▲" : "▼"} {Math.abs(xauChangePct).toFixed(2)}%
          </span>
          <span className="ml-4 h-px w-6 bg-line" />
        </span>

        {/* Context instruments */}
        {[...tickerItems, ...tickerItems].map((item, i) => (
          <span
            key={`${item.symbol}-${i}`}
            className="mx-6 inline-flex shrink-0 items-center gap-2 font-mono text-[10px] uppercase tracking-[0.15em]"
          >
            {item.isLive && <span className="h-1 w-1 rounded-full bg-accent" />}
            <span className="text-ink">{item.symbol}</span>
            <span className={item.isLive ? "text-ink tabular-nums" : "text-ink-dim"}>{item.price}</span>
            <span className={item.up ? "text-up" : "text-down"}>
              {item.change}
            </span>
            <span className="ml-4 h-px w-6 bg-line" />
          </span>
        ))}
      </div>

      {/* Feed label - show live status */}
      <div className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 rounded-chip border border-warn/25 bg-abyss/90 px-2 py-0.5">
        <span className={`font-mono text-[8px] font-semibold uppercase tracking-[0.2em] ${hasLiveData ? "text-accent" : "text-warn"}`}>
          {hasLiveData ? "Live Feed" : "Simulated Feed"}
        </span>
      </div>

      {/* Edge fades */}
      <div className="pointer-events-none absolute inset-y-0 left-0 w-16 bg-gradient-to-r from-abyss to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-abyss to-transparent" />
    </div>
  );
}
