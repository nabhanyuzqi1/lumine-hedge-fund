import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WhatIfPanel } from "./what-if-panel";

vi.mock("@/lib/api/clients/portfolioClient", () => ({
  simulateTrade: vi.fn().mockResolvedValue({
    projected_nav: "100001.06",
    margin_required: "9.68",
    pnl_change: "1.06",
  }),
}));

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <WhatIfPanel />
    </QueryClientProvider>
  );
}

describe("WhatIfPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the form controls", () => {
    renderPanel();
    expect(screen.getByTestId("what-if-panel")).toBeDefined();
    expect(screen.getByLabelText("Symbol")).toBeDefined();
    expect(screen.getByLabelText("Side")).toBeDefined();
    expect(screen.getByLabelText("Volume")).toBeDefined();
    expect(screen.getByLabelText("Price")).toBeDefined();
  });

  it("submits a simulation and renders the projection", async () => {
    renderPanel();
    await userEvent.click(screen.getByRole("button", { name: "Simulate" }));

    await waitFor(() => {
      expect(screen.getByTestId("what-if-result")).toBeDefined();
    });
    const values = screen.getByTestId("what-if-result").textContent ?? "";
    expect(values.replace(/[^\d.]/g, "")).toContain("100001.06");
  });
});
