import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WorkflowRunListPage } from "./workflow-run-list";

function envelope(data: unknown): Response {
  return new Response(JSON.stringify({ data, meta: { status: "ok" } }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("WorkflowRunListPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  function renderPage() {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <WorkflowRunListPage />
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  it("renders runs from the REST response (envelope)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        envelope({
          items: [
            {
              run_id: "11111111-2222-3333-4444-555555555555",
              workflow_name: "decision_cycle",
              status: "completed",
              input_payload: { symbol: "XAUUSD" },
              output_payload: { decision: "hold" },
              started_at: "2026-08-14T00:00:00Z",
              finished_at: "2026-08-14T00:05:00Z",
            },
          ],
          total: 1,
          limit: 20,
          offset: 0,
        })
      )
    );

    renderPage();
    await waitFor(() => expect(screen.getByTestId("runs-table")).toBeDefined());
    expect(screen.getByText("decision_cycle")).toBeDefined();
    expect(screen.getByText("completed")).toBeDefined();
    expect(screen.getByTestId("run-total").textContent).toContain("1");
  });

  it("falls back to fixtures when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("ECONNREFUSED")));

    renderPage();
    await waitFor(() => expect(screen.getByTestId("runs-table")).toBeDefined());
    expect(screen.getByTestId("run-total").textContent).toContain("100");
  });
});
