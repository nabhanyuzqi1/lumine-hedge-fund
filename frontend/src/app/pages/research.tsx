import { useQuery } from "@tanstack/react-query";

import { get } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * ResearchPage (19 Aug 2026 — Phase 5): Paper Trading / Research.
 *
 * Bandingkan PAPER (simulasi/sandbox) vs REAL (akun live MT5) — jawab
 * "apakah keputusan AI bagus tapi eksekusi real berbeda?". Sumber:
 * backend /research/summary (orders by portfolio_id, positions by book).
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

function useResearchSummary() {
  return useQuery({
    queryKey: ["research-summary"],
    queryFn: () => get<ResearchSummary>("/research/summary"),
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
        <MetricRow label="Closed" value={data?.positions_closed ?? "—"} />
        <MetricRow label="Win rate" value={`${data?.win_rate_pct ?? 0}%`} />
        <MetricRow
          label="Realized P&L"
          value={data ? `$${data.realized_pnl.toFixed(2)}` : "—"}
        />
      </CardContent>
    </Card>
  );
}

export function ResearchPage() {
  const { data, isError } = useResearchSummary();

  return (
    <div className="mx-auto w-full max-w-[1200px] space-y-4 p-4">
      <div>
        <h1 className="text-lg font-semibold text-ink">Research — Paper vs Real</h1>
        <p className="text-xs text-ink-faint">
          Perbandingan keputusan AI di simulasi (paper/sandbox) terhadap eksekusi akun
          live (real). Refresh 30 detik.
        </p>
      </div>

      {isError ? (
        <div className="rounded-chip border border-line bg-bg px-4 py-6 text-center text-sm text-ink-faint">
          Gagal memuat summary research.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <BookCard title="PAPER (sandbox)" tone="amber" data={data?.paper} />
          <BookCard title="REAL (MT5 live)" tone="accent" data={data?.real} />
        </div>
      )}

      <p className="text-[11px] text-ink-faint">
        Paper = simulasi (portfolio_id=&quot;paper&quot;, book=&quot;paper&quot;); Real =
        akun MT5 live (portfolio_id=&quot;default&quot;, book=&quot;default&quot;).
        Kalau win-rate paper jauh di atas real → keputusan AI bagus tapi eksekusi/slippage
        berbeda.
      </p>
    </div>
  );
}
