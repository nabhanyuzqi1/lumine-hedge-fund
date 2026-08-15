import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { LandingPage } from "./landing";

// framer-motion whileInView butuh IntersectionObserver — stub untuk jsdom.
beforeAll(() => {
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    }
  );
});

describe("LandingPage", () => {
  it("renders the public landing page", () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>
    );

    // LandingPage is now the public landing — check brand name is visible
    expect(screen.getAllByText("LUMINE").length).toBeGreaterThan(0);
  });
});
