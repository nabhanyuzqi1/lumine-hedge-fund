import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { NumericText } from "@/components/ui/numeric-text";
import { useSSE } from "@/hooks/useSSE";
import { useMarketStore, usePortfolioStore, useStreamStore } from "@/stores";
import type { MarketTick } from "@/stores";
import { useMemo } from "react";
import { useShallow } from "zustand/react/shallow";

interface MarketDataEvent {
  tick: MarketTick;
}

// VITE_API_BASE_URL mengandung /api/v1 (client.ts convention) — strip suffix
// agar SSE url = origin + /api/v1/streams/...
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1").replace(
  /\/api\/v1\/?$/,
  ""
);

/** SSE stream monitor page — live Phase 9 streams → Zustand → table. */
export function StreamsPage() {
  const upsertTick = useMarketStore((state) => state.upsertTick);
  const tick = useMarketStore(useShallow((state) => state.getTick("XAUUSD")));
  const positionsById = usePortfolioStore((state) => state.positions);
  const positions = useMemo(() => Object.values(positionsById), [positionsById]);
  const setStreamState = useStreamStore((state) => state.setStreamState);

  const { status, stale, error } = useSSE<MarketDataEvent>({
    url: `${API_BASE_URL}/api/v1/streams/market-data?symbol=XAUUSD`,
    enabled: true,
    onEvent: (envelope) => {
      if (envelope.data?.tick) {
        upsertTick(envelope.data.tick);
      }
    },
    onLifecycle: (event) => {
      setStreamState("market-data/XAUUSD", {
        status: event.type === "stream_open" || event.type === "stream_resumed" ? "open" : "closed",
      });
    },
    onError: (err) => {
      setStreamState("market-data/XAUUSD", { status: "error", error: err.message });
    },
  });

  return (
    <main className="min-h-screen bg-abyss p-6 text-ink">
      <div className="mx-auto max-w-5xl space-y-6">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Realtime streams</h1>
          <p className="text-text-secondary">SSE → Zustand → virtualized table</p>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-text-secondary">
                Stream status
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Badge
                tone={status === "open" ? "ok" : stale ? "warn" : "danger"}
                label={stale ? "stale" : status}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-text-secondary">XAUUSD last</CardTitle>
            </CardHeader>
            <CardContent>
              {tick ? (
                <NumericText value={tick.last} decimals={2} />
              ) : (
                <span className="text-text-muted">—</span>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-text-secondary">Spread</CardTitle>
            </CardHeader>
            <CardContent>
              {tick ? (
                <NumericText value={tick.ask - tick.bid} decimals={4} />
              ) : (
                <span className="text-text-muted">—</span>
              )}
            </CardContent>
          </Card>
        </div>

        {error && (
          <div className="rounded-panel bg-bg-raised p-3 text-sm text-danger">
            Stream error: {error.message}
          </div>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Positions</CardTitle>
          </CardHeader>
          <CardContent>
            <DataTable
              columns={[
                { key: "symbol", header: "Symbol", cell: (row) => row.symbol },
                { key: "side", header: "Side", cell: (row) => row.side },
                { key: "quantity", header: "Qty", cell: (row) => row.quantity },
                { key: "entry", header: "Entry", cell: (row) => row.avg_entry_price.toFixed(2) },
                {
                  key: "pnl",
                  header: "Unrealized P&L",
                  cell: (row) => row.unrealized_pnl.toFixed(2),
                },
              ]}
              data={positions}
              getRowId={(row) => row.id}
              emptyMessage="No open positions"
            />
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
