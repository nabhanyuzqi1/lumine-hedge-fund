import { describe, expect, it } from "vitest";
import { usePortfolioStore } from "../portfolioStore";

function makePosition(
  id: string,
  symbol: string
): ReturnType<ReturnType<typeof usePortfolioStore.getState>["getPositions"]>[number] {
  return {
    id,
    portfolio_id: "p1",
    symbol,
    quantity: 1,
    side: "LONG",
    avg_entry_price: 2400,
    unrealized_pnl: 10,
    updated_at: new Date().toISOString(),
  };
}

function makeOrder(id: string, status: "PENDING" | "ACTIVE" | "FILLED" | "CANCELLED") {
  return {
    id,
    portfolio_id: "p1",
    symbol: "XAUUSD",
    side: "BUY" as const,
    quantity: 1,
    status,
    type: "LIMIT",
    created_at: new Date().toISOString(),
  };
}

describe("portfolioStore", () => {
  it("upserts and removes positions", () => {
    usePortfolioStore.getState().upsertPosition(makePosition("pos1", "XAUUSD"));
    expect(usePortfolioStore.getState().getPositions()).toHaveLength(1);

    usePortfolioStore.getState().removePosition("pos1");
    expect(usePortfolioStore.getState().getPositions()).toHaveLength(0);
  });

  it("filters orders by status", () => {
    usePortfolioStore.getState().upsertOrder(makeOrder("o1", "PENDING"));
    usePortfolioStore.getState().upsertOrder(makeOrder("o2", "FILLED"));
    usePortfolioStore.getState().upsertOrder(makeOrder("o3", "ACTIVE"));

    const active = usePortfolioStore.getState().getOrdersByStatus(["ACTIVE", "PENDING"]);
    expect(active).toHaveLength(2);
  });
});
