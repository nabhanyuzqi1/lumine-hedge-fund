import * as React from "react";

import { useModifyOrder } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import type { OrderFixture } from "@/data/fixtures";

interface ModifyOrderDialogProps {
  order: OrderFixture;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * D-4 order modification. Adjusts limit price and/or volume before fill via
 * PATCH `/api/v1/orders/:id` (ordersClient.modifyOrder → routers/orders.py).
 * The server-confirmed order is written into the detail + list caches so the
 * terminal reflects the new terms.
 */
export function ModifyOrderDialog({ order, open, onOpenChange }: ModifyOrderDialogProps) {
  const modify = useModifyOrder();
  const { toast } = useToast();

  const [price, setPrice] = React.useState(String(order.entry_price));
  const [volume, setVolume] = React.useState(String(order.quantity));

  React.useEffect(() => {
    if (open) {
      setPrice(String(order.entry_price));
      setVolume(String(order.quantity));
    }
  }, [open, order.entry_price, order.quantity]);

  const priceNum = Number.parseFloat(price);
  const volumeNum = Number.parseFloat(volume);
  const hasChange = priceNum !== order.entry_price || volumeNum !== order.quantity;
  const invalid =
    !Number.isFinite(priceNum) || priceNum <= 0 || !Number.isFinite(volumeNum) || volumeNum <= 0;
  const canSubmit = hasChange && !invalid && !modify.isPending;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      await modify.mutateAsync({ orderId: order.id, price: priceNum, volume: volumeNum });
      onOpenChange(false);
      toast({
        variant: "success",
        title: "Order modified",
        description: `${order.id} → ${volumeNum.toFixed(2)} @ ${priceNum.toFixed(2)} (server-confirmed).`,
      });
    } catch {
      toast({
        variant: "danger",
        title: "Modify failed",
        description: "Backend rejected the modification — check API connectivity.",
      });
    }
  };

  const inputClass =
    "w-full rounded-chip border border-border-subtle bg-bg-base p-2 font-mono text-xs text-text-primary placeholder:text-text-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="modify-order-dialog">
        {/* noValidate: the dialog runs its own validation (invalid message +
            disabled submit); native step/constraint checks would otherwise
            silently block the submit event in jsdom/browsers. */}
        <form onSubmit={handleSubmit} noValidate>
          <DialogHeader>
            <DialogTitle>Modify order {order.id}</DialogTitle>
            <DialogDescription>
              Adjust the working limit terms before fill. Current: {order.quantity.toFixed(2)} @{" "}
              {order.entry_price.toFixed(2)}.
            </DialogDescription>
          </DialogHeader>

          <div className="my-4 grid grid-cols-2 gap-3">
            <label className="block space-y-1">
              <span className="text-[11px] font-medium uppercase tracking-wider text-text-secondary">
                Volume
              </span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={volume}
                onChange={(e) => setVolume(e.target.value)}
                aria-label="Volume"
                className={inputClass}
                data-testid="modify-order-volume"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-[11px] font-medium uppercase tracking-wider text-text-secondary">
                Price
              </span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                aria-label="Price"
                className={inputClass}
                data-testid="modify-order-price"
              />
            </label>
          </div>

          <p className="mb-2 text-[11px] leading-relaxed text-text-secondary">
            Adjustment amends the existing working order. For a full re-pricing with a clean
            lifecycle, cancel this order and place a new one instead.
          </p>

          {invalid && (
            <p className="mb-2 text-[11px] text-danger" data-testid="modify-order-invalid">
              Volume and price must be positive numbers.
            </p>
          )}

          <DialogFooter>
            <Button variant="secondary" size="sm" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              type="submit"
              disabled={!canSubmit}
              data-testid="modify-order-submit"
            >
              Apply changes
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
