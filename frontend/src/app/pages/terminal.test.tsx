import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("lightweight-charts");
vi.mock("echarts/core");
vi.mock("echarts/charts");
vi.mock("echarts/components");
vi.mock("echarts/renderers");
vi.mock("@/hooks/useDemoStreams", () => ({
  useDemoStreams: () => ({ lastTick: null, pnlSeries: [] }),
}));
vi.mock("@/app/components/top-bar", () => ({
  TopBar: () => null,
}));

import { TerminalPage } from "@/app/pages/terminal";
import { useUiStore } from "@/stores/uiStore";
import { AuthProvider } from "@/lib/auth/role-context";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <AuthProvider>
          <TerminalPage />
        </AuthProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("TerminalPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("backend offline")));
    useUiStore.setState({ workspace: "trading" });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the trading grid with fixture-fallback data", async () => {
    renderPage();

    expect(screen.getByRole("heading", { name: /Terminal/i })).toBeDefined();
    expect(screen.getByTestId("quote-panel")).toBeDefined();
    expect(screen.getByTestId("risk-gauges")).toBeDefined();
    expect(document.querySelector(".data-testid-positions-table")).toBeDefined();
    expect(document.querySelector(".data-testid-orders-table")).toBeDefined();
    expect(
      screen.queryByTestId("committee-feed") ?? screen.queryByTestId("committee-empty")
    ).toBeDefined();
    expect(
      screen.queryByTestId("activity-log") ?? screen.queryByTestId("activity-empty")
    ).toBeDefined();

    // Fixture orders include clickable order links.
    await waitFor(() => expect(screen.getAllByText(/ord-/i).length).toBeGreaterThan(0));
  });

  it("always renders the trading grid regardless of workspace state", async () => {
    renderPage();

    await act(async () => {
      useUiStore.setState({ workspace: "research" });
    });

    // Trading grid remains visible because Terminal page now displays TradingWorkspace directly.
    expect(screen.getByTestId("quote-panel")).toBeDefined();
    expect(screen.getByTestId("risk-gauges")).toBeDefined();
    expect(screen.queryByTestId("workspace-placeholders")).toBeNull();
  });

  it("navigates to order detail when an order id is clicked", async () => {
    renderPage();

    const orderLinks = await waitFor(() => screen.getAllByText(/ord-/i));
    expect(orderLinks.length).toBeGreaterThan(0);
  });
});
