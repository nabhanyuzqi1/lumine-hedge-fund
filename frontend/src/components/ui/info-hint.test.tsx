import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HintHeader, InfoHint } from "./info-hint";

describe("InfoHint", () => {
  it("menampilkan ikon ? dan tooltip saat diklik", () => {
    render(<InfoHint text="Penjelasan singkat" />);
    const btn = screen.getByRole("button", { name: /Penjelasan singkat/ });
    expect(btn.textContent).toBe("?");
    fireEvent.click(btn);
    expect(screen.getByRole("tooltip").textContent).toContain("Penjelasan singkat");
  });

  it("menutup tooltip saat klik di luar", () => {
    render(
      <div>
        <InfoHint text="Tutup saat klik luar" />
        <span>luar</span>
      </div>
    );
    const btn = screen.getByRole("button", { name: /Tutup saat klik luar/ });
    fireEvent.click(btn);
    expect(screen.getByRole("tooltip")).toBeTruthy();
    fireEvent.mouseDown(screen.getByText("luar"));
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
});

describe("HintHeader", () => {
  it("merender label + ikon ?", () => {
    render(<HintHeader label="P&L" hint="Penjelasan P&L" />);
    expect(screen.getByText("P&L")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Penjelasan P&L/ })).toBeTruthy();
  });
});