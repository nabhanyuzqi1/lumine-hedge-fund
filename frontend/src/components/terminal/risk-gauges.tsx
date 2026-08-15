import { usePortfolioSummary, usePositionList } from "@/hooks/api/usePortfolio";
import { NumericText } from "@/components/ui/numeric-text";

interface Gauge {
  label: string;
  value: number | null;
  cap: number;
  tone: "ok" | "warn" | "danger";
  suffix: string;
}

const TONE_HEX: Record<Gauge["tone"], string> = {
  ok: "bg-up",
  warn: "bg-warn",
  danger: "bg-danger",
};

function toneFor(value: number, cap: number): Gauge["tone"] {
  const ratio = value / cap;
  if (ratio >= 0.85) return "danger";
  if (ratio >= 0.6) return "warn";
  return "ok";
}

/**
 * Risk gauges — ZERO-DEMO: semua angka dari backend real
 * (portfolio summary + positions dari PostgreSQL/MT5).
 * Kalau data tidak tersedia → tampil "—" (bukan angka fiktif).
 */
export function RiskGauges() {
  const summary = usePortfolioSummary("default");
  const positions = usePositionList("default");

  const nav = summary.data?.nav ?? null;
  const marginUsed = summary.data?.margin_used ?? null;
  const openPnl = summary.data?.open_pnl ?? null;
  const closedPnl = summary.data?.closed_pnl ?? null;

  // Gross notional dari positions (volume × current_price), pakai harga
  // current_price backend (live/fallback last close).
  const notional =
    positions.data?.reduce(
      (acc, p) => acc + (p.volume ?? 0) * (p.current_price ?? p.entry_price ?? 0),
      0
    ) ?? null;

  const exposure = nav && notional ? (notional / nav) * 100 : null;
  const leverage = nav && notional ? notional / nav : null;
  const marginPct = nav && marginUsed != null ? (marginUsed / nav) * 100 : null;
  const netPnl = openPnl != null && closedPnl != null ? openPnl + closedPnl : null;

  const gauges: Gauge[] = [
    {
      label: "Exposure",
      value: exposure != null ? Math.round(exposure * 10) / 10 : null,
      cap: 15,
      tone: exposure != null ? toneFor(exposure, 15) : "ok",
      suffix: "%",
    },
    {
      label: "Leverage",
      value: leverage != null ? Math.round(leverage * 10) / 10 : null,
      cap: 5,
      tone: leverage != null ? toneFor(leverage, 5) : "ok",
      suffix: "x",
    },
    {
      label: "Margin used",
      value: marginPct != null ? Math.round(marginPct) : null,
      cap: 100,
      tone: marginPct != null ? toneFor(marginPct, 100) : "ok",
      suffix: "%",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-3" data-testid="risk-gauges">
      {gauges.map(({ label, value, cap, tone, suffix }) => {
        const pct = value != null ? Math.min(100, (value / cap) * 100) : 0;
        return (
          <div key={label}>
            <div className="mb-1 flex items-baseline justify-between">
              <span className="text-[11px] uppercase tracking-wider text-text-secondary">
                {label}
              </span>
              <span className="font-mono text-sm tabular-nums text-text-primary">
                {value != null ? (
                  <>
                    {value}
                    {suffix}
                    <span className="text-text-tertiary">
                      {" "}
                      / {cap}
                      {suffix}
                    </span>
                  </>
                ) : (
                  <span className="text-text-tertiary">—</span>
                )}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-raised" aria-hidden>
              <div
                className={`h-full rounded-full ${TONE_HEX[tone]}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
      <div className="col-span-2 flex items-baseline justify-between border-t border-border-subtle pt-2">
        <span className="text-[11px] uppercase tracking-wider text-text-secondary">
          Net P&L (session)
        </span>
        <span className="font-mono text-sm tabular-nums">
          {netPnl != null ? (
            <NumericText value={netPnl} decimals={2} />
          ) : (
            <span className="text-text-tertiary">—</span>
          )}
        </span>
      </div>
    </div>
  );
}
