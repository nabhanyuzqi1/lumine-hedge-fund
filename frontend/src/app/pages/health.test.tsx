import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HealthPage } from "./health";

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const QUOTE_PAYLOAD = {
  meta: {
    api_version: "v1",
    timestamp: "2026-08-01T00:00:00Z",
    request_id: "r1",
    status: "ok",
  },
  data: {
    XAUUSD: {
      symbol: "XAUUSD",
      bid: 2400.5,
      ask: 2400.8,
      spread: 0.3,
      timestamp: "2026-08-01T00:00:00Z",
    },
  },
  error: null,
};

const SYSTEM_PAYLOAD = {
  meta: {
    api_version: "v1",
    timestamp: "2026-08-01T00:00:00Z",
    request_id: "r2",
    status: "ok",
  },
  data: {
    environment: "production",
    version: "test",
    demo_data: false,
    llm_gateway_configured: true,
    llm_gateway_url: "https://gw.example",
    services: [{ name: "api", health: "healthy", status: "running" }],
  },
  error: null,
};

describe("HealthPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input);
        const body =
          url.includes("/admin/system-info")
            ? JSON.stringify(SYSTEM_PAYLOAD)
            : url.includes("/health")
              ? JSON.stringify({ meta: { status: "ok" }, data: { status: "ok" }, error: null })
              : JSON.stringify(QUOTE_PAYLOAD);
        return {
          status: 200,
          text: async () => body,
        };
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders quote from API", async () => {
    renderWithQuery(<HealthPage />);

    await waitFor(() => expect(screen.getByText("XAUUSD")).toBeInTheDocument());
    expect(screen.getByText("2400.50")).toBeInTheDocument();
  });
});
