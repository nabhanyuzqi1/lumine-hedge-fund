import { Suspense, lazy, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useMarketBars, useOrders, usePositions } from "@/api/hooks";
import { usePerformanceMetrics } from "@/hooks/usePerformanceMetrics";
import { PerformanceIndicator } from "@/components/monitoring/performance-indicator";
import type { Timeframe } from "@/components/charts/candlestick-chart";
import { ChartCard } from "@/components/charts/chart-card";

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
import type { OrderFixture, OrderStatus, PositionFixture } from "@/data/fixtures";
import { useDemoStreams } from "@/hooks/useDemoStreams";
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

function PositionsTable({ positions }: { positions: PositionFixture[] }) {
  return (
    <DataTable
      data={positions}
      getRowId={(row) => row.id}
      className="data-testid-positions-table"
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
          cell: (row) => <span className="font-mono tabular-nums">{row.quantity.toFixed(2)}</span>,
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
      columns={[
        {
          key: "id",
          header: "Order",
          cell: (row) => (
            <button
              type="button"
              onClick={() => navigate(`/orders/${row.id}`)}
              className="font-mono text-xs text-accent hover:underline"
            >
              {row.id}
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
          cell: (row) => <span className="font-mono tabular-nums">{row.quantity.toFixed(2)}</span>,
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
                className="rounded-chip border border-border-subtle px-2 py-0.5 text-[10px] text-text-secondary hover:bg-bg-raised hover:text-text-primary"
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

function TradingWorkspace() {
  const selectedSymbol = useUiStore((s) => s.selectedSymbol);
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
  const [modifyTarget, setModifyTarget] = useState<OrderFixture | null>(null);

  const bars = useMarketBars(selectedSymbol, timeframe);
  const positions = usePositions();
  const orders = useOrders();
  const demo = useDemoStreams(true, selectedSymbol);

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
            <div className="h-72 animate-pulse rounded-panel border border-border-subtle" />
          }
        >
          <LazyCandlestickChart
            bars={bars.data ?? []}
            lastTick={demo.lastTick}
            timeframe={timeframe}
            onTimeframeChange={setTimeframe}
          />
        </Suspense>
        <Card>
          <CardHeader>
            <CardTitle>Positions</CardTitle>
            <CardDescription>{positions.data?.length ?? 0} open · demo portfolio</CardDescription>
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
 * `/` — Terminal (F-Sprint 5). Trading workspace shows the full grid
 * (chart, quote, positions, orders, risk, committee, activity). Research /
 * Risk / Ops workspaces show placeholder tiles until their surfaces ship in
 * later sprints. Rail switching changes pane visibility only — data stores
 * and streams are never unmounted, so live state persists across switches.
 */
/**
 * `/` — Terminal (F-Sprint 5). Trading workspace shows the full grid
 * (chart, quote, positions, orders, risk, committee, activity). Research /
 * Risk / Ops workspaces show placeholder tiles until their surfaces ship in
 * later sprints. Rail switching changes pane visibility only — data stores
 * and streams are never unmounted, so live state persists across switches.
 */
export function TerminalPage() {
  const { fps, memoryMB: memMB } = usePerformanceMetrics();

  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-4 p-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Terminal</h1>
          <p className="text-sm text-text-secondary">
            XAUUSD · live demo streams — backend Phase 9 pending
          </p>
        </div>
        <div className="flex items-center gap-2">
          <PerformanceIndicator fps={fps} memoryMB={memMB} />
        </div>
      </header>

      <TradingWorkspace />
    </div>
  );
}
