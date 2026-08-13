import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ModifyOrderDialog } from "@/components/orders/modify-order-dialog";
import { ToastProvider } from "@/components/ui/toast";
import { generateOrder } from "@/data/fixtures";

function renderDialog(orderId = "ord-mod-1") {
  const order = generateOrder(orderId, 7);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onOpenChange = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <ModifyOrderDialog order={order} open onOpenChange={onOpenChange} />
      </ToastProvider>
    </QueryClientProvider>
  );
  return { order, onOpenChange };
}

describe("ModifyOrderDialog", () => {
  beforeEach(() => {
    // The submit mutation now calls PATCH /api/v1/orders/{id}; resolve with
    // a valid Order envelope so useModifyOrder can map it to the UI shape.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
        const body = init?.body ? JSON.parse(String(init.body)) : {};
        return Promise.resolve(
          new Response(
            JSON.stringify({
              data: {
                order_id: "ord-mod-1",
                portfolio_id: "default",
                symbol: "XAUUSD",
                side: "buy",
                order_type: "limit",
                volume: body.volume ?? 1,
                price: body.price ?? 2400,
                status: "pending",
                filled_volume: 0,
                rejected_reason: null,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("prefills current terms and submits an adjusted volume", async () => {
    const user = userEvent.setup();
    const { order, onOpenChange } = renderDialog();

    const volumeInput = screen.getByTestId("modify-order-volume");
    expect(volumeInput).toHaveValue(order.quantity);

    await user.clear(volumeInput);
    await user.type(volumeInput, "1.25");
    await user.click(screen.getByTestId("modify-order-submit"));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("disables submit while terms are unchanged", async () => {
    const user = userEvent.setup();
    renderDialog();

    const submit = screen.getByTestId("modify-order-submit") as HTMLButtonElement;
    expect(submit.disabled).toBe(true);

    await user.clear(screen.getByTestId("modify-order-price"));
    await user.type(screen.getByTestId("modify-order-price"), "2399");
    expect((screen.getByTestId("modify-order-submit") as HTMLButtonElement).disabled).toBe(false);
  });

  it("shows a validation message for non-positive values", async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.clear(screen.getByTestId("modify-order-volume"));
    await user.type(screen.getByTestId("modify-order-volume"), "0");

    expect(screen.getByTestId("modify-order-invalid")).toBeDefined();
    expect((screen.getByTestId("modify-order-submit") as HTMLButtonElement).disabled).toBe(true);
  });
});
