import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarketConditionBadges } from "./market-condition-badges";

// Mock useMarketIndicators — komponen murni presentational.
vi.mock("@/api/hooks", () => ({
  useMarketIndicators: vi.fn(),
}));

import { useMarketIndicators } from "@/api/hooks";
const mockIndicators = vi.mocked(useMarketIndicators);

describe("MarketConditionBadges", () => {
  it("merender VOL/SPR/session dengan tone sesuai threshold", () => {
    mockIndicators.mockReturnValue({
      data: { volatility: 34.2, spread: 62, session: "london", features: {} },
    } as never);

    render(<MarketConditionBadges symbol="XAUUSD" />);

    // Badge berisi dot span + teks multi-node — cocokkan via textContent,
    // ambil elemen badge (punya kelas rounded-full dari cva Badge).
    const badgeByText = (t: string) => {
      const hits = screen.getAllByText((_, el) => el?.textContent?.trim() === t);
      expect(hits.length).toBeGreaterThan(0);
      return hits.find((h) => h.className.includes("rounded-full")) ?? hits[0];
    };

    expect(badgeByText("VOL 34.2")).toBeInTheDocument();
    expect(badgeByText("SPR 62")).toBeInTheDocument();
    expect(badgeByText("LONDON")).toBeInTheDocument();

    // danger tone utk vol>=30 dan spread>50
    expect(badgeByText("VOL 34.2").className).toContain("danger");
    expect(badgeByText("SPR 62").className).toContain("danger");
  });

  it("session overlap dipetakan ke label LDN×NY", () => {
    mockIndicators.mockReturnValue({
      data: { volatility: 10, spread: 15, session: "overlap_ldn_ny", features: {} },
    } as never);
    render(<MarketConditionBadges symbol="XAUUSD" />);
    const hits = screen.getAllByText((_, el) => el?.textContent?.trim() === "LDN×NY");
    expect(hits.length).toBeGreaterThan(0);
  });

  it("return null saat semua data nol/unknown", () => {
    mockIndicators.mockReturnValue({
      data: { volatility: 0, spread: 0, session: "unknown", features: {} },
    } as never);
    const { container } = render(<MarketConditionBadges symbol="XAUUSD" />);
    expect(container.firstChild).toBeNull();
  });
});