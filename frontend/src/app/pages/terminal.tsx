import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

import { useMarketBars, useOrders, usePositions } from "@/api/hooks";
import { useMarketWS } from "@/hooks/useMarketWS";
import { usePerformanceMetrics } from "@/hooks/usePerformanceMetrics";
import { PerformanceIndicator } from "@/components/monitoring/performance-indicator";
import type { Timeframe } from "@/components/charts/candlestick-chart";
import type { PriceLine } from "@/components/charts/candlestick-chart";
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
import { CommitteeDecisionSummary } from "@/components/terminal/committee-summary";
import { AIInsightHint } from "@/components/terminal/ai-insight-panel";
import { useDXY } from "@/api/hooks";
import { HintHeader, InfoHint } from "@/components/ui/info-hint";
import { QuotePanel } from "@/components/terminal/quote-panel";
import { RiskGauges } from "@/components/terminal/risk-gauges";
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

const TIMEFRAME_KEYS: Record<string, Timeframe> = {
  "5": "5m",
  "1": "5m",
  "5m": "5m",
  "15": "15m",
  "60": "1H",
  "240": "4H",
  "1H": "1H",
  "4H": "4H",
};

interface MarketDataEvent {
  tick?: MarketTick;
  market_closed?: {
    reason: string;
    next_open: string;
    message: string;
  };
}

function PositionsTable({ positions, symbol }: { positions: PositionFixture[]; symbol: string }) {
  const { t } = useTranslation();
  return (
    <div>
      <div className="mb-1 flex items-center justify-end">
        <AIInsightHint symbol={symbol} />
      </div>
      <DataTable
        data={positions}
        getRowId={(row) => row.id}
        className="data-testid-positions-table"
        maxHeight={400}
        emptyMessage={t("terminal.emptyPositions")}
        columns={[
        {
          key: "symbol",
          header: t("terminal.colSymbol"),
          cell: (row) => <span className="font-mono text-xs">{row.symbol}</span>,
        },
        {
          key: "side",
          header: t("terminal.colSide"),
          cell: (row) => <SideBadge side={row.side} />,
        },
        {
          key: "qty",
          header: t("terminal.colQty"),
          cell: (row) => (
            <span className="font-mono tabular-nums">
              {row.quantity != null ? row.quantity.toFixed(2) : "—"}
            </span>
          ),
        },
        {
          key: "avg",
          header: t("terminal.colAvgEntry"),
          cell: (row) => <NumericText value={row.avg_entry_price} decimals={2} tone="neutral" />,
        },
        {
          key: "current",
          header: t("terminal.colCurrent"),
          cell: (row) => <NumericText value={row.current_price} decimals={2} tone="neutral" />,
        },
        {
                  key: "pnl",
                  header: (
                    <HintHeader
                      label={t("terminal.colPnl") ?? "P&L"}
                      hint="Unrealized P&L = (harga sekarang − harga entry) × qty. Positif = floating profit."
                    />
                  ),
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
            </div>
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
  const { t } = useTranslation();
  return (
    <DataTable
      data={orders}
      getRowId={(row) => row.id}
      className="data-testid-orders-table"
      maxHeight={400}
      columns={[
        {
          key: "id",
          header: t("terminal.colOrder"),
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
          header: t("terminal.colSymbol"),
          cell: (row) => <span className="font-mono text-xs">{row.symbol}</span>,
        },
        {
          key: "side",
          header: t("terminal.colSide"),
          cell: (row) => <SideBadge side={row.side} />,
        },
        {
          key: "qty",
          header: t("terminal.colQty"),
          cell: (row) => (
            <span className="font-mono tabular-nums">
              {row.quantity != null ? row.quantity.toFixed(2) : "—"}
            </span>
          ),
        },
        {
          key: "status",
          header: t("terminal.colStatus"),
          cell: (row) => <Badge tone={ORDER_STATUS_TONE[row.status]} label={row.status} />,
        },
        {
                  key: "pnl",
                  header: (
                    <HintHeader
                      label={t("terminal.colPnl") ?? "P&L"}
                      hint="Unrealized P&L = (harga sekarang − harga entry) × qty. Positif = floating profit."
                    />
                  ),
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
  // 21 Aug 2026 A7 (temuan user): DXY harus bareng pair lain di tape,
  // bukan badge terpisah di atas workspace. Data DXY dari /market/dxy
  // (worker 60s), bukan SSE MT5 — jadi di-poll via useDXY di sini.
  const { data: dxy } = useDXY();
  const fmt = (v: number | undefined | null) =>
    v == null ? "—" : v.toFixed(v < 100 ? 3 : 2);
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
            <span className="text-ink">{fmt(tick?.last)}</span>
            {tick && (
              <span className="text-ink-faint">
                {tick.bid?.toFixed(2)}/{tick.ask?.toFixed(2)}
              </span>
            )}
          </span>
        );
      })}
      <span className="flex items-center gap-1.5 whitespace-nowrap border-r border-line px-3 py-1" data-testid="ticker-dxy">
        <span className="text-ink-dim">DXY</span>
        <span className="text-ink">{fmt(dxy?.price)}</span>
      </span>
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
  const { t } = useTranslation();
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
      <div className="flex items-center gap-1.5 rounded-chip border border-line bg-raised px-2 py-1">
        <span className="font-mono text-[10px] text-ink-faint">{"</"}</span>
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder={t("terminal.commandSymbol")}
                    aria-label="Symbol command line"
          className="w-28 bg-transparent font-mono text-[11px] uppercase tracking-wider text-ink outline-none placeholder:text-ink-faint"
        />
      </div>
      <span className="font-mono text-[10px] text-ink-faint">{t("terminal.commandHint")}</span>
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
  const { t } = useTranslation();
  const selectedSymbol = useUiStore((s) => s.selectedSymbol);
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
    // T5b: Heikin-Ashi toggle — state di sini agar persist antar timeframe.
    const [heikinAshi, setHeikinAshi] = useState(false);
    // T5c: replay mode — index bar aktif + playing flag.
    const [replayIndex, setReplayIndex] = useState<number | null>(null);
    const [replayPlaying, setReplayPlaying] = useState(false);
    const replayTimer = useRef<ReturnType<typeof setInterval> | null>(null);
    const [modifyTarget, setModifyTarget] = useState<OrderFixture | null>(null);
  const lastTick = useMarketStore((s) => s.ticks[selectedSymbol] ?? null);

  const bars = useMarketBars(selectedSymbol, timeframe);

  // T5c: replay — play interval maju 1 bar per tick (400ms).
  useEffect(() => {
    if (!replayPlaying) return;
    replayTimer.current = setInterval(() => {
      setReplayIndex((prev) => {
        const total = bars.data?.length ?? 0;
        if (prev == null) return total > 0 ? 0 : null;
        return prev + 1 >= total ? null : prev + 1;
      });
    }, 400);
    return () => {
      if (replayTimer.current) clearInterval(replayTimer.current);
    };
  }, [replayPlaying, bars.data?.length]);
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

  // ── WebSocket market stream (v2, 17 Aug 2026) ─────────────────────────
  // Primary transport: WS lebih ringan + realtime per tick. Kalau WS gagal
  // (status "error"/"closed" tanpa reconnect dalam 2× backoff), SSE tetap
  // jalan sebagai fallback — keduanya menulis ke store yang sama, tanpa
  // duplikasi (upsertTick idempoten per symbol).
  const wsConnected = useMarketWS({
    symbol: selectedSymbol,
    enabled: true,
    onTick: (tick) => {
      upsertTick(tick);
      setStreamState(streamKey, { status: "open" });
    },
    onClosed: (reason) => {
      setStreamState(streamKey, { status: "closed", error: reason });
      appendLog({ stream: "market", message: `Market closed: ${reason}`, level: "warn" });
    },
    onStatusChange: (status) => {
      if (status === "open") {
        appendLog({ stream: "market", message: `WS stream open: ${selectedSymbol}`, level: "info" });
      }
    },
  });

  // SSE fallback: aktif HANYA kalau WS tidak tersambung (primary down).
  useSSE<MarketDataEvent>({
    url: streamUrl,
    enabled:
      (Object.keys(sseHeaders).length > 0 || !getHmacCredentials()) && !wsConnected,
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
        <ChartCard title={t("terminal.quote")} description={selectedSymbol}>
          <QuotePanel symbol={selectedSymbol} />
        </ChartCard>
        <ChartCard title={t("terminal.risk")} description={t("terminal.riskDescription")}>
          <RiskGauges />
        </ChartCard>
        <Card>
                  <CardHeader>
                    <CardTitle>
                      <span className="inline-flex items-center gap-1">
                        {t("terminal.committee")}
                        <InfoHint
                          text="Committee Live Agent Activity"
                          label="Penjelasan Committee Live Agent Activity"
                          node={
                            <div className="space-y-1.5">
                              <p className="font-medium text-ink">
                                Committee Live Agent Activity
                              </p>
                              <p>
                                Feed realtime dari decision cycle AI: setiap cycle
                                berjalan (~5 menit, durasi 2–4 menit), agent
                                berurutan tampil di sini:{" "}
                                <span className="text-ink">
                                  Analyst (technical/macro/news/SMC)
                                </span>{" "}
                                → <span className="text-ink">IC Forum</span> →{" "}
                                <span className="text-ink">CIO Proposer</span> →{" "}
                                <span className="text-ink">Risk Assessor</span> →
                                eksekusi/penolakan.
                              </p>
                              <p className="text-ink-dim">
                                Di antara cycle feed kosong — itu normal. Verdict
                                terakhir (direction + confidence) tersedia di ikon
                                “?” AI Insight pada tabel di bawah.
                              </p>
                            </div>
                          }
                        />
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <CommitteeDecisionSummary />
                    <CommitteeFeed />
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle>{t("terminal.activity")}</CardTitle>
                    <CardDescription>{t("terminal.activityDescription")}</CardDescription>
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
                      waitingLabel={t("terminal.waitingLiveData")}
                      heikinAshi={heikinAshi}
                      onHeikinAshiChange={setHeikinAshi}
                      replayIndex={replayIndex}
                      priceLines={buildPriceLines(positions.data ?? [])}
                    />
        </Suspense>

        {/* T5c: Replay controls — scrub historis bars_* + export */}
        <div className="flex flex-wrap items-center gap-2 rounded-panel border border-line bg-bg-overlay/60 px-3 py-2">
          <button
            type="button"
            onClick={() => {
              if (replayIndex == null) {
                setReplayIndex(0);
                setReplayPlaying(true);
              } else {
                setReplayIndex(null);
                setReplayPlaying(false);
              }
            }}
            className={cn(
              "rounded border px-2 py-1 font-mono text-[11px] transition-colors",
              replayIndex != null
                ? "border-accent/50 bg-accent/10 text-accent"
                : "border-border-subtle text-text-muted hover:text-text-primary"
            )}
          >
            {replayIndex != null ? "Exit Replay" : "▶ Replay"}
          </button>
          {replayIndex != null && (
            <>
              <button
                type="button"
                onClick={() => setReplayPlaying((p) => !p)}
                className="rounded border border-border-subtle px-2 py-1 font-mono text-[11px] text-text-muted hover:text-text-primary"
              >
                {replayPlaying ? "⏸ Pause" : "▶ Play"}
              </button>
              <button
                type="button"
                onClick={() =>
                  setReplayIndex((prev) => {
                    const total = bars.data?.length ?? 0;
                    if (prev == null) return 0;
                    return Math.min(prev + 20, Math.max(total - 1, 0));
                  })
                }
                className="rounded border border-border-subtle px-2 py-1 font-mono text-[11px] text-text-muted hover:text-text-primary"
              >
                +20
              </button>
              <input
                type="range"
                min={0}
                max={Math.max((bars.data?.length ?? 1) - 1, 0)}
                value={replayIndex ?? 0}
                onChange={(e) => {
                  setReplayIndex(Number(e.target.value));
                  setReplayPlaying(false);
                }}
                className="h-1 w-40 cursor-pointer accent-accent"
                aria-label="Replay scrubber"
              />
              <span className="font-mono text-[10px] text-text-muted tabular-nums">
                {replayIndex ?? 0} / {Math.max((bars.data?.length ?? 1) - 1, 0)}
              </span>
            </>
          )}
        </div>
        <Card>
          <CardHeader>
            <CardTitle>{t("terminal.positions")}</CardTitle>
            <CardDescription>{t("terminal.positionsDescription", { count: positions.data?.length ?? 0 })}</CardDescription>
          </CardHeader>
          <CardContent>
            {positions.isLoading ? (
              <div className="space-y-2">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="h-8 animate-pulse rounded bg-raised" />
                ))}
              </div>
            ) : (
              <PositionsTable positions={positions.data ?? []} symbol={selectedSymbol} />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("terminal.orders")}</CardTitle>
            <CardDescription>{t("terminal.ordersDescription")}</CardDescription>
          </CardHeader>
          <CardContent>
            {orders.isLoading ? (
              <div className="space-y-2">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="h-8 animate-pulse rounded bg-raised" />
                ))}
              </div>
            ) : (
              <OrdersTable orders={orders.data ?? []} onModify={setModifyTarget} />
            )}
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
 * T5b: price lines dari posisi aktif — Entry (biru), SL (merah),
 * TP (hijau). Hanya untuk symbol yang sedang ditampilkan.
 */
function buildPriceLines(positions: PositionFixture[]): PriceLine[] {
  const lines: PriceLine[] = [];
  for (const p of positions) {
    if (p.symbol.toUpperCase() !== "XAUUSD") continue;
    if (p.avg_entry_price != null && Number.isFinite(p.avg_entry_price)) {
      lines.push({
        price: p.avg_entry_price,
        title: "Entry",
        color: "#3b82f6",
      });
    }
    if (p.stop_loss != null && Number.isFinite(p.stop_loss)) {
      lines.push({ price: p.stop_loss as number, title: "SL", color: "#ef4444" });
    }
    if (p.take_profit != null && Number.isFinite(p.take_profit)) {
      lines.push({ price: p.take_profit as number, title: "TP", color: "#22c55e" });
    }
  }
  return lines;
}

/**
 * `/app/terminal` — Bloomberg-style institutional terminal.
 * Live data: REST bars/positions/orders + Phase 9 SSE market-data stream
 * (HMAC-signed). No demo streams — when the stream is unavailable the
 * chart renders REST bars only and the connection badge shows the state.
 */
/**
 * SideBadge (19 Aug 2026 A2): konsisten BUY/SELL untuk posisi & order.
 * DB simpan lowercase "buy"/"sell"; SEBELUMNYA Positions cek "LONG" dan
 * Orders cek "BUY" → mismatch → semua tampil tone salah/ambigu.
 * Map: buy|long → BUY (ok), sell|short → SELL (danger).
 */
function SideBadge({ side }: { side?: string }) {
  const s = (side ?? "").toUpperCase();
  const isBuy = s === "BUY" || s === "LONG";
  const label = isBuy ? "BUY" : s === "SELL" || s === "SHORT" ? "SELL" : side ?? "—";
  return <Badge tone={isBuy ? "ok" : "danger"} label={label} />;
}

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
        {/* 21 Aug 2026 A7: DXYBadge dihapus — DXY sekarang di TickerTape
            bareng pair lain (temuan user). */}
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