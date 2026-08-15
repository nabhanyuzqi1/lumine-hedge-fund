import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("lightweight-charts");
vi.mock("echarts/core");
vi.mock("echarts/charts");
vi.mock("echarts/components");
vi.mock("echarts/renderers");

import * as echarts from "echarts/core";

import { DashboardPage } from "@/app/pages/dashboard";

const mockEcharts = echarts as unknown as {
  __getInstances(): Array<{ setOption: ReturnType<typeof vi.fn> }>;
  __resetInstances(): void;
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DashboardPage />
    </QueryClientProvider>
  );
}

describe("DashboardPage", () => {
  beforeEach(() => {
    // Backend offline → every API hook falls back to deterministic fixtures.
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("backend offline")));
    mockEcharts.__resetInstances();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the full chart grid from fixture-fallback data", async () => {
    renderPage();

    // Statically imported lightweight-charts panes.
    expect(screen.getByText("XAUUSD — Price Action")).toBeDefined();
    expect(screen.getByText("5m candlesticks · volume overlay")).toBeDefined();
    expect(screen.getByText("Portfolio Equity")).toBeDefined();
    expect(screen.getByText("Drawdown")).toBeDefined();
    expect(screen.getByText("Live P&L")).toBeDefined();

    // Lazily imported ECharts panes resolve after suspense. The lazy chunk
    // fetch + Suspense resolution can exceed findBy*'s 1000ms default on a
    // loaded machine, so give this async assertion a 5s budget.
    expect(
      await screen.findByText("Exposure by asset class · %", {}, { timeout: 5000 })
    ).toBeDefined();
    expect(screen.getByText("Cross-Asset Correlation")).toBeDefined();
    expect(screen.getByText("AI Committee Confidence")).toBeDefined();

    await waitFor(() => expect(mockEcharts.__getInstances()).toHaveLength(3));
  });
});
