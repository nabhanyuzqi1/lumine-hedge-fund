import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { AutheliaGuard } from "./authelia-guard";

beforeEach(() => {
  vi.clearAllMocks();
  // Reset window.location.href to empty string for assertions
  Object.defineProperty(window, "location", {
    writable: true,
    value: { pathname: "/superadmin", search: "", href: "" },
  });
});

describe("AutheliaGuard", () => {
  it("shows loading spinner while checking", () => {
    vi.stubGlobal("fetch", () => new Promise(() => {})); // never resolves
    render(<AutheliaGuard><div data-testid="content">protected</div></AutheliaGuard>);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByTestId("content")).not.toBeInTheDocument();
  });

  it("renders children when authenticated", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve({ status: 200 } as Response)
    );
    render(<AutheliaGuard><div data-testid="content">protected</div></AutheliaGuard>);
    expect(await screen.findByTestId("content")).toBeInTheDocument();
  });

  it("redirects to /auth/ when unauthenticated", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve({ status: 401 } as Response)
    );
    render(<AutheliaGuard><div data-testid="content">protected</div></AutheliaGuard>);
    await new Promise((r) => setTimeout(r, 50));
    expect((window.location as { href: string }).href).toContain("/auth/?rd=");
  });
});
