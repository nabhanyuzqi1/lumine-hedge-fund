import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { JournalPage } from "@/app/pages/journal";

vi.mock("echarts/core");
vi.mock("echarts/charts");
vi.mock("echarts/components");
vi.mock("echarts/renderers");

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
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("backend offline")));
  });

  afterEach(() => {
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
    expect(screen.getByTestId("journal-load-more")).toBeDefined();

    fireEvent.click(screen.getByTestId("journal-load-more"));

    await waitFor(() => expect(screen.getAllByTestId(/^journal-row-/)).toHaveLength(100), {
      timeout: 5000,
    });

    fireEvent.click(screen.getByTestId("journal-load-more"));
    await waitFor(() => expect(screen.getAllByTestId(/^journal-row-/)).toHaveLength(137), {
      timeout: 5000,
    });

    await waitFor(() => expect(screen.queryByTestId("journal-load-more")).toBeNull());
  });

  it("expands a row on click", async () => {
    renderPage();

    await waitFor(() => expect(screen.getAllByTestId(/^journal-row-/)).toHaveLength(50));
    const firstRow = screen.getAllByTestId(/^journal-row-/)[0];
    if (!firstRow) throw new Error("expected at least one journal row");
    fireEvent.click(firstRow);

    await waitFor(() => expect(screen.getByText("Portfolio", { selector: "dt" })).toBeDefined());
  });
});
