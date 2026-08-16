import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useMarketBars, useOrders, usePositions } from "@/api/hooks";
import { usePerformanceMetrics } from "@/hooks/usePerformanceMetrics";
import { PerformanceIndicator } from "@/components/monitoring/performance-indicator";
import type { Timeframe } from "@/components/charts/candlestick-chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useSSE } from "@/hooks/useSSE";
import { useCommitteeStreams } from "@/hooks/useCommitteeStreams";
import { buildAuthHeaders, getHmacCredentials } from "@/lib/api/auth";

// lightweight-charts (~500 kB) stays out of the entry eval window: the chart
// only mounts after market bars resolve, so its chunk loads during idle.
const LazyCandlestickChart = lazy(() =>
  import("@/components/charts/candlestick-chart").then((m) => ({
    default: m.CandlestickChart,
  }))
);
import { ActivityLog } from "@/components/terminal/activity-log";
import { CommitteeFeed } from "@/components/terminal/committee-feed";
import { QuotePanel } from "@/components/terminal/quote-panel";
import { RiskGauges } from "@/components/terminal/risk-gauges";
import { WhatIfPanel } from "@/components/terminal/what-if-panel";
import { ModifyOrderDialog } from "@/components/orders/modify-order-dialog";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { NumericText } from "@/components/ui/numeric-text";
import type { OrderStatus, PositionFixture, OrderFixture } from "@/data/fixtures";
import { useMarketStore, type MarketTick } from "@/stores";
import { useActivityStore } from "@/stores/activityStore";
import { useStreamStore } from "@/stores/streamStore";
import { useUiStore } from "@/stores/uiStore";

const ORDER_STATUS_TONE: Record<OrderStatus, "ok" | "warn" | "danger" | "info"> = {
  RECEIVED: "info",
  VALIDATED: "info",
  RISK_CHECK: "warn",
  ACTIVE: "info",
  FILLED: "ok",
  CANCELLED: "warn",
  REJECTED: "danger",
};

const TERMINAL_ORDER_STATUSES: OrderStatus[] = ["FILLED", "CANCELLED", "REJECTED"];

/** Instruments for the ticker tape (Bloomberg-style bottom/top strip). */
const TICKER_SYMBOLS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USOIL", "BTCUSD", "NAS100", "SPX500"];

const TIMEFRAME_KEYS: Partial<Record<string, Timeframe>> = {
  "5": "5m",
  "15": "15m",
  "60": "1H",
  "240": "4H",
};

interface MarketDataEvent {
  tick?: MarketTick;
  /** Market libur (weekend/holiday) — stream hidup tanpa ticks. */
  market_closed?: {
    reason: string;
    next_open: string;
    message: string;
  };
}

function PositionsTable({ positions }: { positions: PositionFixture[] }) {
  return (
    <DataTable
      data={positions}
      getRowId={(row) => row.id}
      className="data-testid-positions-table"
      maxHeight={400}
      columns={[
        {
          key: "symbol",
          header: "Symbol",
          cell: (row) => <span className="font-mono text-xs">{row.symbol}</span>,
        },
        {
          key: "side",
          header: "Side",
          cell: (row) => <Badge tone={row.side === "LONG" ? "ok" : "danger"} label={row.side} />,
        },
        {
          key: "qty",
          header: "Qty",
          cell: (row) => (
            <span className="font-mono tabular-nums">
              {row.quantity != null ? row.quantity.toFixed(2) : "—"}
            </span>
          ),
        },
        {
          key: "avg",
          header: "Avg entry",
          cell: (row) => <NumericText value={row.avg_entry_price} decimals={2} tone="neutral" />,
        },
        {
          key: "current",
          header: "Current",
          cell: (row) => <NumericText value={row.current_price} decimals={2} tone="neutral" />,
        },
        {
          key: "pnl",
          header: "U/P&L",
          cell: (row) => (
            <NumericText
              value={row.unrealized_pnl}
              decimals={2}
              showSign
              tone={row.unrealized_pnl >= 0 ? "up" : "down"}
            />
          ),
        },
      ]}
    />
  );
}

function OrdersTable({
  orders,
  onModify,
}: {
  orders: OrderFixture[];
  onModify?: (order: OrderFixture) => void;
}) {
  const navigate = useNavigate();
  const killSwitchActive = useUiStore((s) => s.killSwitchActive);
  return (
    <DataTable
      data={orders}
      getRowId={(row) => row.id}
      className="data-testid-orders-table"
            maxHeight={400}
            columns={[
              {
                key: "id",
                header: "Order",
                cell: (row) => (
            <button
              type="button"
              onClick={() => navigate(`/orders/${row.id}`)}
              title={row.id}
              className="max-w-[10ch] truncate whitespace-nowrap font-mono text-xs text-accent hover:underline"
            >
              {row.id.slice(0, 8)}…
            </button>
          ),
        },
        {
          key: "symbol",
          header: "Symbol",
          cell: (row) => <span className="font-mono text-xs">{row.symbol}</span>,
        },
        {
          key: "side",
          header: "Side",
          cell: (row) => <Badge tone={row.side === "BUY" ? "ok" : "danger"} label={row.side} />,
        },
        {
          key: "qty",
          header: "Qty",
          cell: (row) => (
            <span className="font-mono tabular-nums">
              {row.quantity != null ? row.quantity.toFixed(2) : "—"}
            </span>
          ),
        },
        {
          key: "status",
          header: "Status",
          cell: (row) => <Badge tone={ORDER_STATUS_TONE[row.status]} label={row.status} />,
        },
        {
          key: "pnl",
          header: "P&L",
          cell: (row) => (
            <NumericText
              value={row.pnl}
              decimals={2}
              showSign
              tone={row.pnl >= 0 ? "up" : "down"}
            />
          ),
        },
        {
          key: "actions",
          header: "",
          cell: (row) => {
            const modifiable = onModify && !TERMINAL_ORDER_STATUSES.includes(row.status) && !killSwitchActive;
            return modifiable ? (
              <button
                type="button"
                onClick={() => onModify(row)}
                className="rounded-chip border border-line px-2 py-0.5 text-[10px] text-ink-dim hover:bg-raised hover:text-ink"
                data-testid={`modify-order-${row.id}`}
              >
                Modify
              </button>
            ) : null;
          },
        },
      ]}
    />
  );
}

/** Bloomberg-style ticker tape: last price per instrument from the market store. */
function TickerTape() {
  const ticks = useMarketStore((s) => s.ticks);
  return (
    <div
      className="flex items-center gap-0 overflow-x-auto border-y border-line bg-bg font-mono text-[10px] tabular-nums"
      data-testid="ticker-tape"
      role="marquee"
      aria-label="Market ticker"
    >
      {TICKER_SYMBOLS.map((symbol) => {
        const tick = ticks[symbol];
        return (
          <span key={symbol} className="flex items-center gap-1.5 whitespace-nowrap border-r border-line px-3 py-1">
            <span className="text-ink-dim">{symbol}</span>
            <span className="text-ink">{tick?.last?.toFixed(tick.last < 100 ? 3 : 2) ?? "—"}</span>
            {tick && (
              <span className="text-ink-faint">
                {tick.bid?.toFixed(2)}/{tick.ask?.toFixed(2)}
              </span>
            )}
          </span>
        );
      })}
    </div>
  );
}

/** Command bar: symbol entry, session clock, SSE status (Bloomberg <GO> style). */
function CommandBar({
  onSymbolChange,
  sseStatus,
}: {
  onSymbolChange: (s: string) => void;
  sseStatus: "open" | "closed" | "error" | "connecting";
}) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const submit = useCallback(() => {
    const value = input.trim().toUpperCase();
    if (value) onSymbolChange(value);
    setInput("");
    inputRef.current?.blur();
  }, [input, onSymbolChange]);

  // Keyboard-first: "/" or "G" focuses the command line; Enter executes.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && document.activeElement !== inputRef.current) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-line pb-2">
      {/* Header inside dihapus (duplikat TopBar) — CommandBar murni fungsional */}
      <div className="flex items-center gap-1.5 rounded-chip border border-line bg-raised px-2 py-1">
        <span className="font-mono text-[10px] text-ink-faint">{"</"}</span>
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="SYMBOL"
          aria-label="Symbol command line"
          className="w-28 bg-transparent font-mono text-[11px] uppercase tracking-wider text-ink outline-none placeholder:text-ink-faint"
        />
      </div>
      <span className="font-mono text-[10px] text-ink-faint">
        {/* key hints */}
        / focus · 5/15/60/240 timeframe · Enter GO
      </span>
      <span
        className="ml-auto h-1.5 w-1.5 rounded-full"
        aria-label={`SSE ${sseStatus}`}
        style={{
          background:
            sseStatus === "open" ? "var(--color-emerald)" : sseStatus === "error" ? "var(--color-soft-red)" : "var(--color-amber)",
        }}
      />
    </header>
  );
}

function TradingWorkspace() {
  const selectedSymbol = useUiStore((s) => s.selectedSymbol);
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
  const [modifyTarget, setModifyTarget] = useState<OrderFixture | null>(null);
  const lastTick = useMarketStore((s) => s.ticks[selectedSymbol] ?? null);

  const bars = useMarketBars(selectedSymbol, timeframe);
  const positions = usePositions();
  const orders = useOrders();
  const upsertTick = useMarketStore((state) => state.upsertTick);
  const setStreamState = useStreamStore((s) => s.setStreamState);
  const appendLog = useActivityStore.getState().appendLog;
  const streamKey = `market-data/${selectedSymbol}`;

  // Live market stream via Phase 9 SSE (HMAC-signed, fetch-based).
  // VITE_API_BASE_URL mengandung /api/v1 (client.ts convention) — strip
  // suffix agar SSE url = origin + /api/v1/streams/...
  const apiOrigin = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/api\/v1\/?$/, "");
  const streamUrl = `${apiOrigin}/api/v1/streams/market-data?symbol=${selectedSymbol}`;
  const [sseHeaders, setSseHeaders] = useState<Record<string, string>>({});

  useEffect(() => {
    let active = true;
    const creds = getHmacCredentials();
    if (!creds) {
      setSseHeaders({});
      return;
    }
    const path = `/api/v1/streams/market-data?symbol=${selectedSymbol}`;
    buildAuthHeaders("GET", path, "", creds.apiKey, creds.apiSecret).then((headers) => {
      if (active) setSseHeaders(headers);
    });
    return () => {
      active = false;
    };
  }, [selectedSymbol]);

  useSSE<MarketDataEvent>({
    url: streamUrl,
    enabled: Object.keys(sseHeaders).length > 0 || !getHmacCredentials(),
    headers: sseHeaders,
    onEvent: (envelope) => {
      if (envelope.data?.tick) {
        upsertTick(envelope.data.tick);
      }
      // Market libur (weekend/holiday) — stream hidup tapi tanpa ticks.
      if (envelope.data?.market_closed) {
        setStreamState(streamKey, { status: "closed", error: envelope.data.market_closed?.message });
        appendLog({ stream: "market", message: `Market closed: ${envelope.data.market_closed?.message}`, level: "warn" });
      }
    },
    onLifecycle: (event) => {
      setStreamState(streamKey, {
        status: event.type === "stream_open" || event.type === "stream_resumed" ? "open" : "closed",
      });
      if (event.type === "stream_open") {
        appendLog({ stream: "market", message: `SSE stream open: ${selectedSymbol}`, level: "info" });
      }
    },
    onError: (err) => {
      setStreamState(streamKey, { status: "error", error: err.message });
      appendLog({ stream: "market", message: `SSE error: ${err.message}`, level: "warn" });
    },
  });

  const streamState = useStreamStore((s) => s.streams[streamKey]);
  void streamState;

  // Timeframe keyboard shortcuts (Bloomberg: <1><GO> etc.).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;
      const tf = TIMEFRAME_KEYS[e.key];
      if (tf) setTimeframe(tf);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  usePerformanceMetrics(); // Initialize metrics collection

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3 xl:grid-cols-5">
      <div className="min-w-0 space-y-4 lg:col-span-1 xl:col-span-2">
        <ChartCard title="Quote" description={selectedSymbol}>
          <QuotePanel symbol={selectedSymbol} />
        </ChartCard>
        <ChartCard title="Risk" description="Session limits">
          <RiskGauges />
        </ChartCard>
        <WhatIfPanel />
        <Card>
          <CardHeader>
            <CardTitle>Committee</CardTitle>
            <CardDescription>Live agent activity</CardDescription>
          </CardHeader>
          <CardContent>
            <CommitteeFeed />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Activity</CardTitle>
            <CardDescription>Stream events</CardDescription>
          </CardHeader>
          <CardContent>
            <ActivityLog limit={12} />
          </CardContent>
        </Card>
      </div>

      <div className="min-w-0 space-y-4 lg:col-span-2 xl:col-span-3">
        <Suspense
          fallback={
            <div className="h-72 animate-pulse rounded-panel border border-line" />
          }
        >
          <LazyCandlestickChart
            bars={bars.data ?? []}
            lastTick={lastTick}
            timeframe={timeframe}
            onTimeframeChange={setTimeframe}
          />
        </Suspense>
        <Card>
          <CardHeader>
            <CardTitle>Positions</CardTitle>
            <CardDescription>{positions.data?.length ?? 0} open</CardDescription>
          </CardHeader>
          <CardContent>
            <PositionsTable positions={positions.data ?? []} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Orders</CardTitle>
            <CardDescription>Click an order to open its lifecycle detail</CardDescription>
          </CardHeader>
          <CardContent>
            <OrdersTable orders={orders.data ?? []} onModify={setModifyTarget} />
          </CardContent>
        </Card>
      </div>
      {modifyTarget && (
        <ModifyOrderDialog
          order={modifyTarget}
          open
          onOpenChange={(open) => {
            if (!open) setModifyTarget(null);
          }}
        />
      )}
    </div>
  );
}

/**
 * `/app/terminal` — Bloomberg-style institutional terminal.
 * Live data: REST bars/positions/orders + Phase 9 SSE market-data stream
 * (HMAC-signed). No demo streams — when the stream is unavailable the
 * chart renders REST bars only and the connection badge shows the state.
 */
export function TerminalPage() {
  const { fps, memoryMB: memMB } = usePerformanceMetrics();
  const selectedSymbol = useUiStore((s) => s.selectedSymbol);
  const setSelectedSymbol = useUiStore((s) => s.setSelectedSymbol);
  const streamState = useStreamStore((s) => s.streams[`market-data/${selectedSymbol}`]);
  const sseStatus = (streamState?.status ?? "connecting") as
    | "open"
    | "closed"
    | "error"
    | "connecting";

  // Committee live feed: connect 4 SSE channel (analyst/ic/cio/risk) →
  // committeeStore → CommitteeFeed. Tanpa ini feed kosong selamanya.
  useCommitteeStreams();

  return (
    <>
      <div className="mx-auto w-full max-w-[1600px] space-y-2 p-3 md:p-4">
        <CommandBar onSymbolChange={setSelectedSymbol} sseStatus={sseStatus} />
        <TickerTape />
        <div className="flex items-center justify-between pt-1">
          <div className="flex items-center gap-2">
            <PerformanceIndicator fps={fps} memoryMB={memMB} />
          </div>
        </div>

        <TradingWorkspace />
      </div>
    </>
  );
}
