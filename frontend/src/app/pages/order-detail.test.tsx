import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OrderDetailPage } from "@/app/pages/order-detail";
import { ToastProvider } from "@/components/ui/toast";
import { useUiStore } from "@/stores/uiStore";

vi.mock("echarts/core");
vi.mock("echarts/charts");
vi.mock("echarts/components");
vi.mock("echarts/renderers");

function renderPage(orderId = "ord-001") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[`/orders/${orderId}`]}>
      <QueryClientProvider client={client}>
        <ToastProvider>
          <Routes>
            <Route path="/orders/:orderId" element={<OrderDetailPage />} />
          </Routes>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("OrderDetailPage", () => {
  beforeEach(() => {
    // ZERO-DEMO: GET /orders/{id} → order real shape (envelope); cancel
    // mutation hits live DELETE /api/v1/orders/{id}.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
        const envelope = (data: unknown, status = 200) =>
          Promise.resolve(
            new Response(
              JSON.stringify({
                meta: { api_version: "v1", timestamp: new Date().toISOString(), request_id: "test", status: "ok" },
                data,
                error: null,
              }),
              { status, headers: { "Content-Type": "application/json" } }
            )
          );
        if (!init?.method || init.method === "GET") {
          return envelope({
            order_id: "ord-001",
            portfolio_id: "default",
            symbol: "XAUUSD",
            side: "buy",
            order_type: "market",
            volume: "0.01",
            price: "4374.21",
            status: "pending",
            filled_volume: "0.00",
            created_at: "2026-08-15T00:00:00Z",
            updated_at: "2026-08-15T00:00:00Z",
          });
        }
        if (init?.method === "DELETE") {
          return envelope({ order_id: "ord-001", status: "cancelled" });
        }
        return Promise.reject(new Error("backend offline"));
      })
    );
    useUiStore.setState({ killSwitchActive: false });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders order summary and lifecycle timeline", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText(/Order ord-001/i)).toBeDefined());
    expect(screen.getByTestId("order-lifecycle-timeline")).toBeDefined();
    expect(screen.getByTestId("cancel-order-button")).toBeDefined();
  });

  it("opens confirm dialog and cancels the order", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByTestId("cancel-order-button")).toBeEnabled());

    fireEvent.click(screen.getByTestId("cancel-order-button"));
    await waitFor(() => expect(screen.getByTestId("confirm-cancel-order")).toBeDefined());

    await act(async () => {
      fireEvent.click(screen.getByTestId("confirm-cancel-order"));
    });

    await waitFor(() => expect(screen.queryByTestId("confirm-cancel-order")).toBeNull());
  });

  it("disables cancel button when kill switch is active", async () => {
    useUiStore.setState({ killSwitchActive: true });
    renderPage();

    await waitFor(() => expect(screen.getByTestId("cancel-order-button")).toBeDisabled());
    expect(screen.getByTestId("kill-switch-disabled-hint")).toBeDefined();
  });
});
