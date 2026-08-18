import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AIInsightPanel } from "./ai-insight-panel";

// Mock useSignals — panel hanya presentational.
vi.mock("@/api/hooks", () => ({
  useSignals: () => ({
    data: [
      {
        time: 1700000000,
        analyst: "technical_analyst",
        confidence: 0.82,
        direction: "bullish",
        rationale: "EMA20 > EMA50, momentum naik",
      },
      {
        time: 1699999900,
        analyst: "news_analyst",
        confidence: 0.45,
        direction: "neutral",
        rationale: "news mix, tidak ada surprise",
      },
    ],
    isLoading: false,
  }),
}));

describe("AIInsightPanel", () => {
  it("menampilkan verdict terakhir + confidence + bar minimum eksekusi", () => {
    render(<AIInsightPanel symbol="XAUUSD" />);
    expect(screen.getByText(/Verdict terakhir/)).toBeTruthy();
    expect(screen.getAllByText(/bullish/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/82%/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Confidence & bar minimum eksekusi/)).toBeTruthy();
    expect(screen.getByText(/≥ 70%/)).toBeTruthy();
  });

  it("menampilkan semua sinyal analyst via AnalystCard", () => {
    render(<AIInsightPanel symbol="XAUUSD" />);
    expect(screen.getByTestId("analyst-card-technical_analyst")).toBeTruthy();
    expect(screen.getByTestId("analyst-card-news_analyst")).toBeTruthy();
  });
});
