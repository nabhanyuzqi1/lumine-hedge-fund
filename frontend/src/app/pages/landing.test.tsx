import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { LandingPage } from "./landing";

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
