import { useState } from "react";

import { useQuery } from "@tanstack/react-query";

import { get } from "@/api/client";
import { ResearchChart, type SeriesPoint } from "@/components/charts/research-chart";
import { ResearchWorkspaceSwitcher } from "@/components/research/workspace-switcher";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/** ResearchPage (19 Aug 2026 · Phase 5): Paper Trading / Research.
 *
 * Bandingkan PAPER (simulasi/sandbox) vs REAL (akun live MT5) — jawab
 * "apakah keputusan AI bagus tapi eksekusi real berbeda?". Sumber:
 * backend /research/summary (orders by portfolio_id, positions by book)
 * dan /research/series (P&L kumulatif per book).
 *
 * 22 Aug 2026: tambah ResearchWorkspaceSwitcher — tab eksplisit antar
 * Portfolio Dashboard (/app/dashboard) dan Research Lab (/app/research).
 */

interface BookMetrics {
  orders_filled: number;
  positions_total: number;
  positions_closed: number;
  win_rate_pct: number;
  realized_pnl: number;
}

interface ResearchSummary {
  paper: BookMetrics;
  real: BookMetrics;
}

interface ResearchSeries {
  paper: SeriesPoint[];
  real: SeriesPoint[];
  paper_final_pnl: number;
  real_final_pnl: number;
  insight: string;
}

// 25 Aug 2026: multipair — hook menerima symbol (ALL = semua pair).
const RESEARCH_SYMBOLS = ["ALL", "XAUUSD", "BTCUSD"] as const;

function useResearchSummary(symbol: string = "ALL") {
  return useQuery({
    queryKey: ["research-summary", symbol],
    queryFn: () =>
      get<ResearchSummary>(
        symbol === "ALL" ? "/research/summary" : `/research/summary?symbol=${symbol}`,
      ),
    refetchInterval: 30_000,
  });
}

function useResearchSeries(symbol: string = "ALL") {
  return useQuery({
    queryKey: ["research-series", symbol],
    queryFn: () =>
      get<ResearchSeries>(
        symbol === "ALL" ? "/research/series" : `/research/series?symbol=${symbol}`,
      ),
    refetchInterval: 30_000,
  });
}

function MetricRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-xs text-ink-faint">{label}</span>
      <span className="font-mono text-sm tabular-nums text-ink">{value}</span>
    </div>
  );
}

function BookCard({
  title,
  tone,
  data,
}: {
  title: string;
  tone: "accent" | "amber";
  data: BookMetrics | undefined;
}) {
  const border = tone === "accent" ? "border-accent/40" : "border-amber/40";
  const badge =
    tone === "accent" ? "bg-accent/10 text-accent" : "bg-amber/10 text-amber";
  return (
    <Card className={border}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <span className={`rounded-chip px-2 py-0.5 text-[10px] font-medium ${badge}`}>
            {title}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-0.5">
        <MetricRow label="Orders filled" value={data?.orders_filled ?? "—"} />
        <MetricRow label="Positions total" value={data?.positions_total ?? "—"} />
        <MetricRow label="Positions closed" value={data?.positions_closed ?? "—"} />
        <MetricRow label="Win rate" value={`${data?.win_rate_pct ?? "—"}%`} />
        <MetricRow label="Realized P&L" value={`$${data?.realized_pnl ?? "—"}`} />
      </CardContent>
    </Card>
  );
}

export default function ResearchPage() {
  // 25 Aug 2026: selector pair — research per-symbol (multipair).
  const [symbol, setSymbol] = useState<string>("ALL");
  const { data, isError, isLoading } = useResearchSummary(symbol);
  const { data: seriesData } = useResearchSeries(symbol);

  return (
    <div className="mx-auto w-full max-w-[1200px] space-y-4 p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Research Lab</h1>
          <p className="text-xs text-ink-faint">
            Perbandingan keputusan AI di simulasi (paper/sandbox) terhadap eksekusi akun
            live (real). Refresh 30 detik.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Pair filter: ALL / XAUUSD / BTCUSD */}
          <div
            role="group"
            aria-label="Filter pair research"
            className="flex items-center rounded-md border border-border-subtle bg-bg-overlay p-0.5"
          >
            {RESEARCH_SYMBOLS.map((s) => (
              <button
                key={s}
                type="button"
                aria-pressed={s === symbol}
                onClick={() => setSymbol(s)}
                className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                  s === symbol
                    ? "bg-accent text-white shadow-sm"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                {s === "ALL" ? "Semua" : s}
              </button>
            ))}
          </div>
          <ResearchWorkspaceSwitcher />
        </div>
      </div>

      {isLoading ? (
        <div className="rounded-chip border border-line bg-bg px-4 py-6 text-center text-sm text-ink-faint">
          Memuat summary research…
        </div>
      ) : isError ? (
        <div className="rounded-chip border border-line bg-bg px-4 py-6 text-center text-sm text-ink-faint">
          Gagal memuat summary research.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <BookCard title="PAPER (sandbox)" tone="amber" data={data?.paper} />
          <BookCard title="REAL (MT5 live)" tone="accent" data={data?.real} />
        </div>
      )}

      <ResearchChart
        paper={seriesData?.paper ?? []}
        real={seriesData?.real ?? []}
        waitingLabel="Menunggu posisi tertutup…"
      />

      {seriesData?.insight ? (
        <div className="rounded-chip border border-accent/30 bg-accent/5 px-3 py-2 text-xs text-ink">
          <span className="font-medium text-accent">Insight: </span>
          {seriesData.insight}
        </div>
      ) : null}

      <p className="text-[11px] text-ink-faint">
        Paper = simulasi (portfolio_id=&quot;paper&quot;, book=&quot;paper&quot;); Real =
        akun MT5 live (portfolio_id=&quot;default&quot;, book=&quot;default&quot;).
        Kalau win-rate paper jauh di atas real → keputusan AI bagus tapi eksekusi/slippage
        berbeda.
      </p>
    </div>
  );
}
