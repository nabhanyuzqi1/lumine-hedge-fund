import React from "react";

import { useQuery } from "@tanstack/react-query";

import { get } from "@/api/client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface BacktestTrade {
  symbol: string;
  side: string;
  entry_ts: string;
  exit_ts: string | null;
  entry_price: number;
  exit_price: number;
  pnl_pct: number;
}

interface BacktestMetrics {
  // Backend mengirim sebagai STRING ("0.0235") — dideklarasi number |
  // string; render mem-parse Number defensif (18 Aug 2026).
  total_return_pct: number | string;
  max_drawdown_pct: number | string;
  win_rate_pct: number | string;
  trade_count: number;
  sharpe_like: number | string;
}

interface BacktestResult {
  symbol: string;
  timeframe: string;
  equity: number[];
  trades: BacktestTrade[];
  metrics: BacktestMetrics | null;
}

function EquitySparkline({ equity }: { equity: number[] }) {
  if (equity.length < 2) return <div className="h-16 text-xs text-ink-faint flex items-center">No equity data</div>;

  const min = Math.min(...equity);
  const max = Math.max(...equity);
  const range = max - min || 1;
  const w = 400;
  const h = 64;
  const pts = equity
    .map((v, i) => {
      const x = (i / (equity.length - 1)) * w;
      const y = h - ((v - min) / range) * (h - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");

  const last = equity[equity.length - 1]!;
  const first = equity[0]!;
  const up = last >= first;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-16" preserveAspectRatio="none">
      <polyline
        points={pts}
        fill="none"
        stroke={up ? "#22c55e" : "#ef4444"}
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function BacktestTab() {
  const [symbol, setSymbol] = React.useState("XAUUSD");
  const [timeframe, setTimeframe] = React.useState("1h");
  const [stopPct, setStopPct] = React.useState("0.02");
  const [runKey, setRunKey] = React.useState(0);

  const { data, isLoading, isError, error } = useQuery<BacktestResult>({
    queryKey: ["backtest", symbol, timeframe, stopPct, runKey],
    queryFn: () =>
      get<BacktestResult>(`/backtest/run?symbol=${symbol}&timeframe=${timeframe}&stop_pct=${stopPct}`),
    enabled: runKey > 0,
  });

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center gap-2">
        <h2 className="font-mono text-sm font-semibold text-ink">Strategy Backtest</h2>
        <Badge tone="neutral" label="BETA" />
      </div>

      {/* Controls */}
      <Card>
        <CardHeader>
          <CardTitle>Parameters</CardTitle>
          <CardDescription>Run a historical backtest on price data from the database</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-ink-dim">
              Symbol
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="mt-1 block rounded-chip border border-line bg-bg px-2 py-1 font-mono text-xs text-ink"
              >
                {["XAUUSD", "XAGUSD", "EURUSD", "BTCUSD", "USOIL"].map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </label>
            <label className="text-xs text-ink-dim">
              Timeframe
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="mt-1 block rounded-chip border border-line bg-bg px-2 py-1 font-mono text-xs text-ink"
              >
                {["5m", "15m", "30m", "1h", "4h"].map((tf) => (
                  <option key={tf} value={tf}>{tf}</option>
                ))}
              </select>
            </label>
            <label className="text-xs text-ink-dim">
              Stop Loss %
              <input
                type="number"
                step="0.005"
                min="0.001"
                max="0.1"
                value={stopPct}
                onChange={(e) => setStopPct(e.target.value)}
                className="mt-1 block w-24 rounded-chip border border-line bg-bg px-2 py-1 font-mono text-xs text-ink"
              />
            </label>
            <button
              type="button"
              disabled={isLoading}
              onClick={() => setRunKey((k) => k + 1)}
              className="rounded-chip bg-accent px-4 py-1.5 text-xs font-medium text-white hover:bg-accent/90 disabled:opacity-50"
            >
              {isLoading ? "Running…" : "Run Backtest"}
            </button>
          </div>
        </CardContent>
      </Card>

      {isError && (
        <div className="rounded-chip border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">
          Backtest failed: {(error as Error)?.message ?? "unknown error"}
        </div>
      )}

      {data && (
        <>
          {/* Metrics */}
          <Card>
            <CardHeader>
              <CardTitle>Results — {data.symbol} {data.timeframe}</CardTitle>
              <CardDescription>{data.metrics?.trade_count ?? 0} trades</CardDescription>
            </CardHeader>
            <CardContent>
              {data.metrics ? (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
                  {(() => {
                    // Backend kirim metrics sebagai STRING ("0.0235") —
                    // toFixed langsung crash (RouteErrorBoundary → superadmin
                    // blank). Parse Number defensif (18 Aug 2026).
                    const m = data.metrics;
                    const num = (v: unknown): number => {
                      const n = typeof v === "number" ? v : Number.parseFloat(String(v ?? "0"));
                      return Number.isFinite(n) ? n : 0;
                    };
                    const totalReturn = num(m.total_return_pct);
                    const maxDd = num(m.max_drawdown_pct);
                    const winRate = num(m.win_rate_pct);
                    const sharpe = num(m.sharpe_like);
                    return [
                      { label: "Total Return", value: `${totalReturn.toFixed(2)}%`, tone: totalReturn >= 0 ? "ok" : "danger" },
                      { label: "Max Drawdown", value: `${maxDd.toFixed(2)}%`, tone: "warn" },
                      { label: "Win Rate", value: `${winRate.toFixed(1)}%`, tone: "neutral" },
                      { label: "Trade Count", value: String(m.trade_count ?? 0), tone: "neutral" },
                      { label: "Sharpe-like", value: sharpe.toFixed(2), tone: sharpe >= 1 ? "ok" : "neutral" },
                    ];
                  })().map((m) => (
                    <div key={m.label} className="rounded-chip border border-line bg-raised p-3">
                      <p className="text-[11px] text-ink-faint">{m.label}</p>
                      <p className={`font-mono text-sm font-semibold ${m.tone === "ok" ? "text-ok" : m.tone === "danger" ? "text-danger" : m.tone === "warn" ? "text-warn" : "text-ink"}`}>
                        {m.value}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-ink-faint">No metrics available — not enough data</p>
              )}
            </CardContent>
          </Card>

          {/* Equity Curve */}
          {data.equity.length > 1 && (
            <Card>
              <CardHeader>
                <CardTitle>Equity Curve</CardTitle>
                <CardDescription>Cumulative returns over backtest period</CardDescription>
              </CardHeader>
              <CardContent>
                <EquitySparkline equity={data.equity} />
              </CardContent>
            </Card>
          )}

          {/* Trades Table */}
          {data.trades.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Trade Log</CardTitle>
                <CardDescription>Last {Math.min(data.trades.length, 50)} trades</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-line text-left font-mono text-[10px] uppercase tracking-wider text-ink-faint">
                        <th className="pb-2 pr-3">Side</th>
                        <th className="pb-2 pr-3">Entry</th>
                        <th className="pb-2 pr-3">Exit</th>
                        <th className="pb-2 pr-3">Entry $</th>
                        <th className="pb-2 pr-3">Exit $</th>
                        <th className="pb-2">P&L %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.trades.slice(0, 50).map((t, i) => (
                        <tr key={i} className="border-b border-line/50">
                          <td className="py-1 pr-3">
                            <Badge tone={t.side === "long" ? "ok" : "danger"} label={t.side.toUpperCase()} />
                          </td>
                          <td className="py-1 pr-3 font-mono text-ink-dim">{t.entry_ts ? new Date(t.entry_ts).toLocaleDateString() : "—"}</td>
                          <td className="py-1 pr-3 font-mono text-ink-dim">{t.exit_ts ? new Date(t.exit_ts).toLocaleDateString() : "open"}</td>
                          <td className="py-1 pr-3 font-mono">{t.entry_price.toFixed(2)}</td>
                          <td className="py-1 pr-3 font-mono">{t.exit_price.toFixed(2)}</td>
                          <td className={`py-1 font-mono font-semibold ${t.pnl_pct >= 0 ? "text-ok" : "text-danger"}`}>
                            {t.pnl_pct >= 0 ? "+" : ""}{(t.pnl_pct * 100).toFixed(3)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
