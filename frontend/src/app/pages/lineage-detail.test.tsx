import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LineageDetailPage } from "@/app/pages/lineage-detail";

vi.mock("echarts/core");
vi.mock("echarts/charts");
vi.mock("echarts/components");
vi.mock("echarts/renderers");

// ZERO-DEMO: mock API client langsung — lineage real shape (tree minimal
// dari toLineageFixture: root decision). Bukan fixture generate*.
const { apiGet } = vi.hoisted(() => ({
  apiGet: vi.fn(async (path: string) => {
    if (String(path).includes("/lineage/lin-001")) {
      return {
        lineage_id: "lin-001",
        decision_id: "dec-001",
        decision_type: "IC proposal",
        agent_name: "Technical Analyst",
        inputs_hash: "abc123def456",
        outputs_hash: "def456abc123",
        policy_version: "v1",
        created_at: "2026-08-15T00:00:00Z",
      };
    }
    if (String(path).includes("/lineage/")) {
      throw new Error("lineage not found");
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

function renderPage(lineageId = "lin-001") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[`/lineage/${lineageId}`]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/lineage/:lineageId" element={<LineageDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("LineageDetailPage", () => {
  beforeEach(() => {
    apiGet.mockClear();
    vi.stubGlobal("navigator", {
      ...navigator,
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders lineage summary and decision tree", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText(/Lineage lin-001/i)).toBeDefined());
    expect(screen.getByTestId("lineage-viewer")).toBeDefined();
    // Root node label dari decision_type + agent_name (API real shape)
    expect(screen.getByText(/IC proposal — Technical Analyst/i)).toBeDefined();
  });

  it("filters tree by search term", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText(/IC proposal — Technical Analyst/i)).toBeDefined());

    fireEvent.change(screen.getByTestId("lineage-search"), { target: { value: "proposal" } });

    await waitFor(() => {
      expect(screen.getByText(/IC proposal — Technical Analyst/i)).toBeDefined();
    });
  });

  it("copies path to clipboard", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText(/IC proposal — Technical Analyst/i)).toBeDefined());
    fireEvent.click(screen.getByTestId("copy-path-decision"));

    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("decision"));
  });
});
