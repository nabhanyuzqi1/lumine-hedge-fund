import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { LandingPage } from "./landing";

describe("LandingPage", () => {
  it("redirects to the terminal workspace", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/terminal" element={<div data-testid="terminal-stub" />} />
        </Routes>
      </MemoryRouter>
    );

    // LandingPage is a redirect stub; the terminal route must take over.
    expect(await screen.findByTestId("terminal-stub")).toBeDefined();
  });
});
