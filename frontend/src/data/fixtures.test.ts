import { describe, expect, it } from "vitest";

import {
  generateBars,
  generateCorrelationMatrix,
  generateEquity,
  generateExposure,
  generatePnl,
  generateSignals,
} from "@/data/fixtures";

describe("fixture determinism", () => {
  it("same seed ⇒ identical bars", () => {
    expect(generateBars({ seed: 42, count: 50 })).toEqual(generateBars({ seed: 42, count: 50 }));
  });

  it("different seed ⇒ different bars", () => {
    expect(generateBars({ seed: 1, count: 50 })).not.toEqual(generateBars({ seed: 2, count: 50 }));
  });

  it("equity, exposure, signals and correlation are deterministic", () => {
    expect(generateEquity({ seed: 7 })).toEqual(generateEquity({ seed: 7 }));
    expect(generateExposure({ seed: 11 })).toEqual(generateExposure({ seed: 11 }));
    expect(generateSignals({ seed: 3 })).toEqual(generateSignals({ seed: 3 }));
    expect(generateCorrelationMatrix(["A", "B"], 23)).toEqual(
      generateCorrelationMatrix(["A", "B"], 23)
    );
  });
});

describe("generateBars", () => {
  const bars = generateBars({ count: 100 });

  it("honors OHLC invariants and positive volume", () => {
    for (const bar of bars) {
      expect(bar.high).toBeGreaterThanOrEqual(Math.max(bar.open, bar.close));
      expect(bar.low).toBeLessThanOrEqual(Math.min(bar.open, bar.close));
      expect(bar.volume).toBeGreaterThan(0);
    }
  });

  it("spaces bars by the interval", () => {
    expect(bars[1]!.time - bars[0]!.time).toBe(300);
    expect(bars.length).toBe(100);
  });
});

describe("generateEquity", () => {
  it("stays positive and grows over the sample", () => {
    const points = generateEquity({ count: 100, startValue: 1_000_000, drift: 0.001 });
    expect(points.every((p) => p.value > 0)).toBe(true);
    expect(points[99]!.value).toBeGreaterThan(points[0]!.value);
  });
});

describe("generateExposure", () => {
  it("weights are positive and normalize near 100%", () => {
    const items = generateExposure();
    const total = items.reduce((sum, item) => sum + item.weight, 0);
    expect(items.every((item) => item.weight > 0)).toBe(true);
    expect(total).toBeGreaterThan(0.9);
    expect(total).toBeLessThan(1.1);
  });
});

describe("generateCorrelationMatrix", () => {
  const symbols = ["A", "B", "C"];
  const matrix = generateCorrelationMatrix(symbols);

  it("has unit diagonal and is symmetric", () => {
    for (let i = 0; i < symbols.length; i++) {
      expect(matrix[i]![i]).toBe(1);
      for (let j = 0; j < symbols.length; j++) {
        expect(matrix[i]![j]).toBe(matrix[j]![i]);
      }
    }
  });

  it("stays within [-0.7, 0.95] off the diagonal", () => {
    for (let i = 0; i < symbols.length; i++) {
      for (let j = 0; j < symbols.length; j++) {
        if (i === j) continue;
        expect(matrix[i]![j]).toBeGreaterThanOrEqual(-0.7);
        expect(matrix[i]![j]).toBeLessThanOrEqual(0.95);
      }
    }
  });
});

describe("generateSignals", () => {
  it("keeps confidence within the band and covers all analysts", () => {
    const points = generateSignals({ count: 20 });
    const analysts = new Set(points.map((p) => p.analyst));

    expect(analysts).toEqual(new Set(["technical", "macro", "news", "smc"]));
    for (const point of points) {
      expect(point.confidence).toBeGreaterThanOrEqual(0.05);
      expect(point.confidence).toBeLessThanOrEqual(0.95);
    }
  });
});

describe("generatePnl", () => {
  it("produces the requested number of points", () => {
    expect(generatePnl({ count: 60 })).toHaveLength(60);
  });
});
