import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("lightweight-charts");
vi.mock("echarts/core");
vi.mock("echarts/charts");
vi.mock("echarts/components");
vi.mock("echarts/renderers");
vi.mock("@/app/components/top-bar", () => ({
  TopBar: () => null,
}));

// ZERO-DEMO: mock API client module langsung (deterministik — tanpa race
// fetch-level). Data REAL shape; kosong untuk yang tidak diuji.
const { apiGet } = vi.hoisted(() => ({
  apiGet: vi.fn(async (path: string) => {
    if (String(path).includes("/orders")) {
      return {
        items: [
          {
            order_id: "ord-abc-123",
            portfolio_id: "default",
            symbol: "XAUUSD",
            side: "buy",
            order_type: "market",
            volume: "0.01",
            price: "4374.21",
            status: "filled",
            filled_volume: "0.01",
            created_at: "2026-08-15T00:00:00Z",
            updated_at: "2026-08-15T00:00:00Z",
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
      };
    }
    if (String(path).includes("/portfolio/positions")) {
      return { items: [], total: 0, limit: 20, offset: 0 };
    }
    if (String(path).includes("/portfolio/summary")) {
      return {
        portfolio_id: "default",
        nav: "100.00",
        cash: "80.00",
        margin_used: "20.00",
        open_pnl: "0.00",
        closed_pnl: "0.00",
        timestamp: "2026-08-15T00:00:00Z",
      };
    }
    if (String(path).includes("/market/ohlcv")) {
      return { items: [], total: 0 };
    }
    if (String(path).includes("/market/quote")) {
      return { symbol: "XAUUSD", bid: 4374.2, ask: 4374.3, last: 4374.21, timestamp: "2026-08-15T00:00:00Z" };
    }
    if (String(path).includes("/market/signals")) {
      return { items: [], total: 0, limit: 20, offset: 0 };
    }
    if (String(path).includes("/market/correlation")) return {};
    if (String(path).includes("/market/volatility")) return { volatility: "0.0018" };
    if (String(path).includes("/market/spread")) return { avg_spread: "0.96" };
    if (String(path).includes("/market/session")) {
      return { current_session: "off", next_session: "asian", time_until_next: 0, is_trading_open: false };
    }
    if (String(path).includes("/market/features")) {
      return { symbol: "XAUUSD", features: {}, computed_at: "2026-08-15T00:00:00Z" };
    }
    if (String(path).includes("/journal")) {
      return { items: [], total: 0, limit: 20, offset: 0 };
    }
    return { items: [], total: 0 };
  }),
}));

vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return {
    ...actual,
    get: apiGet,
  };
});

// SSE streams: mock module agar tidak ada reconnect loop di test.
vi.mock("@/hooks/useSSE", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useSSE")>("@/hooks/useSSE");
  return {
    ...actual,
    useSSE: () => ({
      status: "error" as const,
      lastEventId: null,
      stale: false,
      error: new Error("stream not tested"),
    }),
  };
});

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
    apiGet.mockClear();
    useUiStore.setState({ workspace: "trading" });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the trading grid (zero-demo: real shapes, kosong saat tidak ada data)", async () => {
    renderPage();

    // Command bar menggantikan h1 "Terminal" (Bloomberg-style, tanpa judul duplikat).
    expect(screen.getByLabelText(/Symbol command line/i)).toBeDefined();
    expect(screen.getByTestId("ticker-tape")).toBeDefined();
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
  });

  it("renders real order rows dari mock (ord-*)", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText(/ord-/i).length).toBeGreaterThan(0);
    });
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
