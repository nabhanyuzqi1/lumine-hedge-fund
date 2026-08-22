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

function useResearchSummary() {
  return useQuery({
    queryKey: ["research-summary"],
    queryFn: () => get<ResearchSummary>("/research/summary"),
    refetchInterval: 30_000,
  });
}

function useResearchSeries() {
  return useQuery({
    queryKey: ["research-series"],
    queryFn: () => get<ResearchSeries>("/research/series"),
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
  const { data, isError, isLoading } = useResearchSummary();
  const { data: seriesData } = useResearchSeries();

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
        <ResearchWorkspaceSwitcher />
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
