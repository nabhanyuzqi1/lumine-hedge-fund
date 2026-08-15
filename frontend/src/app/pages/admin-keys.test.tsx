import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminKeysPage } from "@/app/pages/admin-keys";
import { ToastProvider } from "@/components/ui/toast";

vi.mock("echarts/core");
vi.mock("echarts/charts");
vi.mock("echarts/components");
vi.mock("echarts/renderers");

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/admin/keys"]}>
      <QueryClientProvider client={client}>
        <ToastProvider>
          <Routes>
            <Route path="/admin/keys" element={<AdminKeysPage />} />
          </Routes>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("AdminKeysPage", () => {
  beforeEach(() => {
    // Query hooks fall back to fixtures when GETs reject; create/revoke
    // mutations hit the live admin router and resolve with envelopes.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === "POST") {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                data: {
                  key_id: "key-abc123",
                  secret: "sk-live-secret-abc",
                  scopes: ["market.read", "portfolio.read"],
                  created_at: new Date().toISOString(),
                },
              }),
              { status: 201, headers: { "Content-Type": "application/json" } }
            )
          );
        }
        if (init?.method === "DELETE") {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                data: { key_id: "key-001", scopes: [], revoked: true, created_at: new Date().toISOString() },
              }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }
        return Promise.reject(new Error("backend offline"));
      })
    );
    vi.stubGlobal("navigator", {
      ...navigator,
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the API key table", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByTestId("api-key-table")).toBeDefined());
    await waitFor(() => expect(screen.getAllByTestId(/^api-key-row-/).length).toBeGreaterThan(0));
  });

  it("creates a key and shows one-time secret", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByTestId("api-key-table")).toBeDefined());

    fireEvent.click(screen.getByTestId("create-key-button"));
    await waitFor(() => expect(screen.getByTestId("create-key-submit")).toBeDefined());

    fireEvent.click(screen.getByTestId("create-key-submit"));

    await waitFor(() => expect(screen.getByTestId("secret-dialog")).toBeDefined());
    expect(screen.getByTestId("secret-value")).toBeDefined();

    fireEvent.click(screen.getByTestId("copy-secret"));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalled());
  });

  it("revokes an active key after confirmation", async () => {
    renderPage();

    await waitFor(() => expect(screen.getAllByTestId(/^api-key-row-/).length).toBeGreaterThan(0));

    const revokeButton = screen.getAllByTestId(/^revoke-key-/)[0];
    if (!revokeButton) throw new Error("expected an active key to revoke");
    fireEvent.click(revokeButton);

    await waitFor(() => expect(screen.getByTestId("revoke-confirm-dialog")).toBeDefined());
    fireEvent.click(screen.getByTestId("confirm-revoke"));

    await waitFor(() => expect(screen.queryByTestId("revoke-confirm-dialog")).toBeNull());
  });
});
