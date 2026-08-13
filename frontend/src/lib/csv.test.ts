import { describe, expect, it } from "vitest";

import { toCsv } from "@/lib/csv";

describe("toCsv", () => {
  it("exports headers and rows", () => {
    const csv = toCsv([
      { symbol: "XAUUSD", nav: 100000.5, note: null },
      { symbol: "EURUSD", nav: 50000, note: "has, comma" },
    ]);
    const lines = csv.split("\n");
    expect(lines[0]).toBe("symbol,nav,note");
    expect(lines[1]).toBe("XAUUSD,100000.5,");
    expect(lines[2]).toBe('EURUSD,50000,"has, comma"');
  });

  it("quotes embedded newlines and quotes", () => {
    const csv = toCsv([{ a: 'say "hi"\nnext' }]);
    expect(csv).toContain('"say ""hi""\nnext"');
  });

  it("returns empty string for no rows", () => {
    expect(toCsv([])).toBe("");
  });
});
