import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AnalystCard } from "./analyst-card";
import { DecisionCard } from "./decision-card";
import { ExposureSummaryCard } from "./exposure-summary-card";
import { MarketIndicatorsPanel } from "./market-indicators-panel";

function envelope(data: unknown): Response {
  return new Response(JSON.stringify({ data, meta: { status: "ok" } }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function renderWithClient(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

describe("dashboard components (F-04..F-07)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("AnalystCard renders analyst, direction and confidence", () => {
    renderWithClient(
      <AnalystCard
        signal={{
          time: 1720000000,
          analyst: "technical_analyst",
          confidence: 0.78,
          direction: "bullish",
          rationale: "breakout above resistance",
        }}
      />
    );
    expect(screen.getByText("Technical")).toBeDefined();
    expect(screen.getByText("bullish")).toBeDefined();
    expect(screen.getByText("78%")).toBeDefined();
  });

  it("DecisionCard renders action and confidence", () => {
    renderWithClient(
      <DecisionCard
        decision={{ action: "sell", confidence: 0.62, timestamp: "2026-08-14T00:00:00Z" }}
      />
    );
    expect(screen.getByText("sell")).toBeDefined();
    expect(screen.getByText("62% confidence")).toBeDefined();
  });

  it("MarketIndicatorsPanel falls back gracefully when backend offline", async () => {
    renderWithClient(<MarketIndicatorsPanel symbol="XAUUSD" />);
    await waitFor(() => {
      expect(screen.getByTestId("market-indicators-panel")).toBeDefined();
    });
  });

  it("MarketIndicatorsPanel renders live values from the envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("volatility")) return Promise.resolve(envelope({ volatility: "0.1299" }));
        if (url.includes("spread")) return Promise.resolve(envelope({ spread: "0.4475" }));
        if (url.includes("session")) return Promise.resolve(envelope({ session: "american" }));
        return Promise.resolve(envelope({ rsi_14: 55.2, atr_14: 9.6, vwap: 2449.1 }));
      })
    );
    renderWithClient(<MarketIndicatorsPanel symbol="XAUUSD" />);
    await waitFor(() => {
      expect(screen.getByText("12.99%")).toBeDefined();
    });
    expect(screen.getByText("american")).toBeDefined();
  });

  it("ExposureSummaryCard renders per-symbol weights", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        envelope({
          items: [
            { symbol: "XAUUSD", correlated_bucket: "metals", pct_of_nav: "0.38" },
            { symbol: "BTCUSD", correlated_bucket: "crypto", pct_of_nav: "0.12" },
          ],
          total: 2,
          limit: 20,
          offset: 0,
        })
      )
    );
    renderWithClient(<ExposureSummaryCard />);
    await waitFor(() => {
      expect(screen.getByText("XAUUSD")).toBeDefined();
    });
    expect(screen.getByText("38.0%")).toBeDefined();
  });
});
