import { useState } from "react";
import { useParams } from "react-router-dom";

import { useCancelOrder, useOrder } from "@/api/hooks";
import { ModifyOrderDialog } from "@/components/orders/modify-order-dialog";
import { OrderLifecycleTimeline } from "@/components/orders/order-lifecycle-timeline";
import { ActivityLog } from "@/components/terminal/activity-log";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { NumericText } from "@/components/ui/numeric-text";
import { useToast } from "@/components/ui/toast";
import type { OrderStatus } from "@/data/fixtures";
import { useUiStore } from "@/stores/uiStore";

const TERMINAL_ORDER_STATUSES: OrderStatus[] = ["FILLED", "CANCELLED", "REJECTED"];

const ORDER_STATUS_TONE: Record<OrderStatus, "ok" | "warn" | "danger" | "info"> = {
  RECEIVED: "info",
  VALIDATED: "info",
  RISK_CHECK: "warn",
  ACTIVE: "info",
  FILLED: "ok",
  CANCELLED: "warn",
  REJECTED: "danger",
};

/**
 * `/orders/:orderId` — Order detail (W2). Header card with live P&L, status,
 * side badge, and cancel action. Cancel is disabled under kill switch or when
 * the order is already terminal. A confirmation dialog gates the mutation.
 */
export function OrderDetailPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const order = useOrder(orderId ?? "");
  const cancel = useCancelOrder();
  const killSwitchActive = useUiStore((s) => s.killSwitchActive);
  const { toast } = useToast();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [modifyOpen, setModifyOpen] = useState(false);

  const data = order.data;
  const isTerminal = data ? TERMINAL_ORDER_STATUSES.includes(data.status) : false;
  const canCancel = data && !isTerminal && !killSwitchActive;
  const canModify = data && !isTerminal && !killSwitchActive;

  const handleCancel = async () => {
    if (!orderId) return;
    await cancel.mutateAsync(orderId);
    setConfirmOpen(false);
    toast({
      variant: "success",
      title: "Order cancelled",
      description: `${orderId} has been marked CANCELLED.`,
    });
  };

  if (!orderId) {
    return (
      <div className="p-4">
        <p className="text-sm text-text-secondary">No order id provided.</p>
      </div>
    );
  }

  if (order.isLoading) {
    return (
      <div className="p-4">
        <p className="text-sm text-text-secondary">Loading order…</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-4">
        <p className="text-sm text-text-secondary">Order not found.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-[1200px] space-y-4 p-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Order {orderId}</h1>
          <p className="text-sm text-text-secondary">
            {data.symbol} · {data.type} · {new Date(data.created_at).toISOString()}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={!canModify}
            onClick={() => setModifyOpen(true)}
            data-testid="modify-order-button"
          >
            Modify
          </Button>
          <Button
            variant="danger"
            size="sm"
            disabled={!canCancel}
            onClick={() => setConfirmOpen(true)}
            data-testid="cancel-order-button"
          >
            Cancel order
          </Button>
        </div>
      </header>

      {killSwitchActive && (
        <p className="text-xs text-warn" data-testid="kill-switch-disabled-hint">
          Kill switch active — write operations disabled.
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Order summary</CardTitle>
            <CardDescription>
              <Badge
                tone={(["BUY", "LONG", "buy", "long"] as string[]).includes(String(data.side)) ? "ok" : "danger"}
                label={String(data.side)}
              />
              <Badge tone={ORDER_STATUS_TONE[data.status]} label={data.status} />
            </CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div>
                <dt className="text-[11px] uppercase tracking-wider text-text-secondary">Qty</dt>
                <dd className="font-mono text-sm tabular-nums text-text-primary">
                                  {data.quantity != null ? data.quantity.toFixed(2) : "—"}
                                </dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-wider text-text-secondary">Entry</dt>
                <dd className="font-mono text-sm tabular-nums text-text-primary">
                  <NumericText value={data.entry_price} decimals={2} tone="neutral" />
                </dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-wider text-text-secondary">
                  Current
                </dt>
                <dd className="font-mono text-sm tabular-nums text-text-primary">
                  <NumericText value={data.current_price} decimals={2} tone="neutral" />
                </dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-wider text-text-secondary">P&L</dt>
                <dd className="font-mono text-sm tabular-nums">
                  <NumericText
                    value={data.pnl}
                    decimals={2}
                    showSign
                    tone={data.pnl >= 0 ? "up" : "down"}
                  />
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Lifecycle</CardTitle>
          </CardHeader>
          <CardContent>
            <OrderLifecycleTimeline status={data.status} lifecycle={data.lifecycle} />
          </CardContent>
        </Card>
      </div>

      {(() => {
        let reason: Record<string, unknown> | null = null;
        try {
          if (data.ai_reason) reason = JSON.parse(data.ai_reason);
        } catch {
          reason = null;
        }
        if (!reason) return null;
        return (
          <Card>
            <CardHeader>
              <CardTitle>AI Decision Reason</CardTitle>
              <CardDescription>Mengapa Lumine mengambil keputusan ini (19 Aug 2026)</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  tone={String(reason.side).toUpperCase() === "SELL" ? "danger" : "ok"}
                  label={`${String(reason.action).toUpperCase()} · ${String(reason.side).toUpperCase()}`}
                />
                <span className="font-mono text-xs tabular-nums text-text-secondary">
                  confidence {Number(reason.confidence ?? 0).toFixed(2)} · size {String(reason.size)}
                </span>
              </div>
              <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <div>
                  <dt className="text-[11px] uppercase tracking-wider text-text-secondary">Entry area</dt>
                  <dd className="font-mono text-xs text-text-primary">{String(reason.entry)}</dd>
                  <dd className="text-[11px] text-text-tertiary">{String(reason.entry_note ?? "—")}</dd>
                </div>
                <div>
                  <dt className="text-[11px] uppercase tracking-wider text-text-secondary">Stop loss</dt>
                  <dd className="font-mono text-xs text-text-primary">{String(reason.stop_loss ?? "—")}</dd>
                </div>
                <div>
                  <dt className="text-[11px] uppercase tracking-wider text-text-secondary">Take profit</dt>
                  <dd className="font-mono text-xs text-text-primary">{String(reason.take_profit ?? "—")}</dd>
                  <dd className="text-[11px] text-text-tertiary">{String(reason.tp_reason ?? "")}</dd>
                </div>
              </dl>
              {Boolean(reason.analyst_alignment) && (
                <p className="text-[11px] text-text-tertiary">
                  Analyst alignment: {JSON.stringify(reason.analyst_alignment)}
                </p>
              )}
              {Boolean(reason.raw_reason) && (
                <p className="rounded bg-bg-raised p-2 text-[11px] leading-relaxed text-text-secondary">
                  {String(reason.raw_reason)}
                </p>
              )}
              <p className="text-[11px] text-text-tertiary">
                Profil {String(reason.profile_id ?? "—")} · TF {String(reason.timeframe ?? "—")} · model {String(reason.model_version ?? "—")}
              </p>
            </CardContent>
          </Card>
        );
      })()}

      <Card>
        <CardHeader>
          <CardTitle>Stream events</CardTitle>
          <CardDescription>Filtered symbol: {data.symbol}</CardDescription>
        </CardHeader>
        <CardContent>
          <ActivityLog limit={12} />
        </CardContent>
      </Card>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancel order {orderId}?</DialogTitle>
            <DialogDescription>
              This will submit a cancel request to the backend order lifecycle
              (POST /orders/&#123;id&#125;/cancel).
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="secondary" size="sm" onClick={() => setConfirmOpen(false)}>
              Keep order
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={handleCancel}
              disabled={cancel.isPending}
              data-testid="confirm-cancel-order"
            >
              Confirm cancel
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {data && (
        <ModifyOrderDialog order={data} open={modifyOpen} onOpenChange={setModifyOpen} />
      )}
    </div>
  );
}
