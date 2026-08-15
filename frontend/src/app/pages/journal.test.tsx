import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { JournalPage } from "@/app/pages/journal";

vi.mock("echarts/core");
vi.mock("echarts/charts");
vi.mock("echarts/components");
vi.mock("echarts/renderers");

// ZERO-DEMO: mock API client module langsung (deterministik — tanpa race
// fetch-level). Mock filter symbol seperti backend behavior.
const { apiGet } = vi.hoisted(() => {
  const all = Array.from({ length: 50 }, (_, i) => {
    const n = i + 1;
    const symbol = i % 5 === 0 ? "EURUSD" : "XAUUSD";
    return {
      entry_id: `entry-${String(n).padStart(4, "0")}`,
      created_at: new Date(Date.now() - n * 60_000).toISOString(),
      agent_name: i % 3 === 0 ? "risk_officer" : "technical_analyst",
      reflection: `reflection-${n}`,
      lesson: null,
      symbol,
    };
  });
  return {
    apiGet: vi.fn(async (path: string, params?: Record<string, string | string[]>) => {
      if (String(path).includes("/journal")) {
        const symbol = params?.symbol;
        const filtered =
          typeof symbol === "string" && symbol.length > 0
            ? all.filter((e) => e.symbol === symbol)
            : all;
        return { items: filtered, total: filtered.length, limit: 50, offset: 0 };
      }
      return { items: [], total: 0 };
    }),
  };
});

vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return {
    ...actual,
    get: apiGet,
  };
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/journal"]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/journal" element={<JournalPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("JournalPage", () => {
  afterEach(() => {
    // NOTE: jangan vi.clearAllMocks() — hoisted apiGet implementation
    // (vi.fn(async ...)) bisa hilang setelah clear antar test.
    vi.unstubAllGlobals();
  });

  it("renders the journal table", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByTestId("journal-row-entry-0001")).toBeDefined(), {
      timeout: 3000,
    });
    await waitFor(() => expect(screen.getAllByTestId(/^journal-row-/)).toHaveLength(50));
  });

  it("filters by symbol", async () => {
    renderPage();

    await waitFor(() => expect(screen.getAllByTestId(/^journal-row-/)).toHaveLength(50));

    fireEvent.change(screen.getByTestId("journal-symbol-filter"), { target: { value: "EURUSD" } });

    await waitFor(() => {
      const rows = screen.getAllByTestId(/^journal-row-/);
      expect(rows.length).toBeGreaterThan(0);
      expect(rows.length).toBeLessThan(50);
    });
  });

  it("loads more entries and hides button at end", async () => {
    renderPage();

    await waitFor(() => expect(screen.getAllByTestId(/^journal-row-/)).toHaveLength(50));
    // total == items.length → has_more false → tombol Load more tidak muncul
    expect(screen.queryByTestId("journal-load-more")).toBeNull();
  });

  it("expands a row on click", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByTestId("journal-row-entry-0001")).toBeDefined());
    // Detail row (expanded) — label "Portfolio" muncul sebagai <dt>; label
    // filter toolbar pakai <label> — bedakan via selector.
    expect(screen.queryByText("Portfolio", { selector: "dt" })).toBeNull();
    fireEvent.click(screen.getByTestId("journal-row-entry-0001"));
    await waitFor(() =>
      expect(screen.getByText("Portfolio", { selector: "dt" })).toBeDefined()
    );
  });
});
