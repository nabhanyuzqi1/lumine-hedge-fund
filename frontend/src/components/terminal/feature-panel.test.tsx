import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FeaturePanel } from "./feature-panel";

// Mock useMarketIndicators — panel murni presentational terhadap data hook.
vi.mock("@/api/hooks", () => ({
  useMarketIndicators: vi.fn(),
}));

import { useMarketIndicators } from "@/api/hooks";
const mockIndicators = vi.mocked(useMarketIndicators);

describe("FeaturePanel", () => {
  it("merender baris volatility/spread/session/features", () => {
    mockIndicators.mockReturnValue({
      data: {
        volatility: 12.34,
        spread: 2.5,
        session: "london",
        features: { atr_14: 5.67, rsi_14: 61.2 },
      },
      isPending: false,
    } as never);

    render(<FeaturePanel symbol="XAUUSD" />);

    expect(screen.getByText("Volatility")).toBeInTheDocument();
    expect(screen.getByText("12.34")).toBeInTheDocument();
    expect(screen.getByText("Spread")).toBeInTheDocument();
    expect(screen.getByText("london")).toBeInTheDocument();
    expect(screen.getByText("ATR 14")).toBeInTheDocument();
    expect(screen.getByText("5.67")).toBeInTheDocument();
  });

  it("menampilkan skeleton saat pending", () => {
    mockIndicators.mockReturnValue({ isPending: true } as never);
    const { container } = render(<FeaturePanel symbol="XAUUSD" />);
    expect(container.querySelector(".animate-pulse")).not.toBeNull();
  });

  it("return null saat tidak ada data sama sekali", () => {
    mockIndicators.mockReturnValue({
      data: { volatility: 0, spread: 0, session: "", features: {} },
      isPending: false,
    } as never);
    const { container } = render(<FeaturePanel symbol="XAUUSD" />);
    expect(container.firstChild).toBeNull();
  });
});