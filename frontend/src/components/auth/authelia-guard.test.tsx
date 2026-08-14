import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { AutheliaGuard } from "./authelia-guard";

// Mock fetch
global.fetch = vi.fn();

describe("AutheliaGuard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete (window as any).location;
    (window as any).location = { href: "" };
  });

  it("renders children when authenticated (200)", async () => {
    (global.fetch as any).mockResolvedValueOnce({ ok: true, status: 200 });

    render(
      <BrowserRouter>
        <AutheliaGuard>
          <div>Protected content</div>
        </AutheliaGuard>
      </BrowserRouter>
    );

    expect(screen.getByText("Verifying session...")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Protected content")).toBeInTheDocument());
  });

  it("redirects to Authelia login when unauthenticated (401)", async () => {
    (global.fetch as any).mockResolvedValueOnce({ ok: false, status: 401 });

    render(
      <BrowserRouter>
        <AutheliaGuard>
          <div>Protected content</div>
        </AutheliaGuard>
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(window.location.href).toContain("/auth/?rd=");
    });
  });

  it("redirects to Authelia login on fetch error", async () => {
    (global.fetch as any).mockRejectedValueOnce(new Error("Network error"));

    render(
      <BrowserRouter>
        <AutheliaGuard>
          <div>Protected content</div>
        </AutheliaGuard>
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(window.location.href).toContain("/auth/?rd=");
    });
  });
});
