const ITEMS = [
  { sym: "XAUUSD", bid: "3,412.84", chg: "+0.42%", dir: "up" },
  { sym: "EURUSD", bid: "1.08312", chg: "-0.18%", dir: "down" },
  { sym: "US30", bid: "44,218.6", chg: "+0.11%", dir: "up" },
  { sym: "GBPUSD", bid: "1.29764", chg: "+0.03%", dir: "up" },
  { sym: "USDJPY", bid: "151.483", chg: "-0.26%", dir: "down" },
  { sym: "NAS100", bid: "21,784.2", chg: "+0.64%", dir: "up" },
  { sym: "WTI", bid: "74.21", chg: "-0.85%", dir: "down" },
  { sym: "BTCUSD", bid: "68,902.5", chg: "+1.12%", dir: "up" },
];

function TapeItem({ item }) {
  const color = item.dir === "up" ? "var(--color-up)" : "var(--color-down)";
  return (
    <span className="inline-flex items-center gap-2 px-5 font-mono text-[11px] tracking-wide">
      <span className="text-ink-dim">{item.sym}</span>
      <span className="text-ink">{item.bid}</span>
      <span style={{ color }}>{item.chg}</span>
    </span>
  );
}

export default function Ticker() {
  const doubled = [...ITEMS, ...ITEMS];
  return (
    <div
      className="relative overflow-hidden border-y border-line bg-abyss/80"
      role="marquee"
      aria-label="Live market tape — simulated feed"
    >
      <div className="tape-track flex w-max py-2">
        {doubled.map((item, i) => (
          <TapeItem key={`${item.sym}-${i}`} item={item} />
        ))}
      </div>
      <div className="pointer-events-none absolute inset-y-0 left-0 w-16 bg-gradient-to-r from-abyss to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-abyss to-transparent" />
    </div>
  );
}
