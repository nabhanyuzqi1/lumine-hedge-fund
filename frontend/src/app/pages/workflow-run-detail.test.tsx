import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WorkflowRunDetailPage } from "@/app/pages/workflow-run-detail";
import { useCommitteeStore } from "@/stores/committeeStore";

vi.mock("echarts/core");
vi.mock("echarts/charts");
vi.mock("echarts/components");
vi.mock("echarts/renderers");

function renderPage(workflowId = "wf-xauusd-daily", runId = "run-001") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[`/workflows/${workflowId}/runs/${runId}`]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/workflows/:workflowId/runs/:runId" element={<WorkflowRunDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("WorkflowRunDetailPage", () => {
  beforeEach(() => {
    // ZERO-DEMO: GET /workflows/{runId} → run real shape (envelope).
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL) =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              meta: { api_version: "v1", timestamp: new Date().toISOString(), request_id: "test", status: "ok" },
              data: {
                run_id: "run-001",
                workflow_id: "wf-xauusd-daily",
                workflow_name: "XAUUSD Daily Direction",
                status: "running",
                started_at: "2026-08-15T00:00:00Z",
                finished_at: null,
              },
              error: null,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        )
      )
    );
    useCommitteeStore.setState({
      activities: [
        {
          id: "act-1",
          workflow_run_id: "run-001",
          type: "analyst_output",
          agent: "technical",
          decision: "Trend continuation confirmed",
          timestamp: new Date().toISOString(),
        },
      ],
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders run summary and stepper", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText(/Run run-001/i)).toBeDefined());
    expect(screen.getByTestId("run-stepper")).toBeDefined();
    expect(
      screen.getByText(/XAUUSD Daily Direction|News Event Sweep|Portfolio Rebalance/i)
    ).toBeDefined();
  });

  it("filters committee feed by run id", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByTestId("committee-feed")).toBeDefined());
    expect(screen.getByText("technical")).toBeDefined();
    expect(screen.getByText("Trend continuation confirmed")).toBeDefined();
  });
});
