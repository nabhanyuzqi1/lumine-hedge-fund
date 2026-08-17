import { describe, expect, it } from "vitest";

import type { ChartBar, EquityPoint, ExposureItem, SignalPoint } from "@/data/fixtures";
import { CHART_COLORS } from "@/lib/chart-theme";
import {
  barsToCandles,
  candleFromBar,
  confidenceToEcharts,
  correlationToHeatmap,
  equityToArea,
  equityToDrawdown,
  exposureToTreemap,
  heikinAshiToCandles,
  pnlToLine,
  toUTCTime,
  updateBarWithTick,
  volumeFromBar,
} from "@/lib/chart-transform";

const BARS: ChartBar[] = [
  { time: 1000, open: 100, high: 110, low: 95, close: 105, volume: 500 },
  { time: 2000, open: 105, high: 108, low: 100, close: 98, volume: 700 },
];

describe("barsToCandles", () => {
  it("splits bars into candle and volume series with UTC second times", () => {
    const { candles, volumes } = barsToCandles(BARS);

    expect(candles).toHaveLength(2);
    expect(candles[0]).toEqual({ time: 1000, open: 100, high: 110, low: 95, close: 105 });
    expect(volumes).toHaveLength(2);
    expect(volumes[0]).toEqual({ time: 1000, value: 500, color: CHART_COLORS.up });
  });

  it("colors volume bars by direction (down on a red candle)", () => {
    const { volumes } = barsToCandles(BARS);
    expect(volumes[1]).toEqual({ time: 2000, value: 700, color: CHART_COLORS.down });
  });
});

describe("candleFromBar / volumeFromBar", () => {
  it("produces single-point payloads for incremental updates", () => {
    expect(candleFromBar(BARS[0]!)).toEqual({
      time: 1000,
      open: 100,
      high: 110,
      low: 95,
      close: 105,
    });
    expect(volumeFromBar(BARS[0]!).color).toBe(CHART_COLORS.up);
  });
});

describe("updateBarWithTick", () => {
  it("raises high and moves close", () => {
    const updated = updateBarWithTick(BARS[0]!, 112);
    expect(updated.high).toBe(112);
    expect(updated.low).toBe(95);
    expect(updated.close).toBe(112);
  });

  it("lowers low without touching high", () => {
    const updated = updateBarWithTick(BARS[0]!, 92);
    expect(updated.high).toBe(110);
    expect(updated.low).toBe(92);
    expect(updated.close).toBe(92);
  });

  it("keeps time when no time is given, else takes the later time", () => {
    expect(updateBarWithTick(BARS[0]!, 105).time).toBe(1000);
    expect(updateBarWithTick(BARS[0]!, 105, 1500).time).toBe(1500);
  });
});

describe("equityToArea / pnlToLine", () => {
  it("maps points to series data preserving time", () => {
    const points: EquityPoint[] = [
      { time: 1000, value: 100 },
      { time: 2000, value: 105 },
    ];
    expect(equityToArea(points)).toEqual([
      { time: 1000, value: 100 },
      { time: 2000, value: 105 },
    ]);
    expect(pnlToLine(points)).toEqual([
      { time: 1000, value: 100 },
      { time: 2000, value: 105 },
    ]);
  });
});

describe("equityToDrawdown", () => {
  it("is always ≤ 0 and recovers to 0 at new peaks", () => {
    const points: EquityPoint[] = [
      { time: 1000, value: 100 },
      { time: 2000, value: 120 },
      { time: 3000, value: 108 },
      { time: 4000, value: 96 },
      { time: 5000, value: 132 },
    ];
    const dd = equityToDrawdown(points);

    const expected = [0, 0, -0.1, -0.2, 0];
    dd.forEach((p, index) => expect(p.value).toBeCloseTo(expected[index]!, 10));
    expect(dd.every((p) => p.value <= 0)).toBe(true);
  });
});

describe("exposureToTreemap", () => {
  const items: ExposureItem[] = [
    { symbol: "XAUUSD", assetClass: "Metals", weight: 0.38 },
    { symbol: "XAGUSD", assetClass: "Metals", weight: 0.08 },
    { symbol: "EURUSD", assetClass: "FX", weight: 0.16 },
  ];

  it("groups by asset class, sorted descending, children per symbol", () => {
    const tree = exposureToTreemap(items);

    expect(tree.map((n) => n.name)).toEqual(["Metals", "FX"]);
    expect(tree[0]?.value).toBeCloseTo(0.46);
    expect(tree[0]?.children).toEqual([
      { name: "XAUUSD", value: 0.38 },
      { name: "XAGUSD", value: 0.08 },
    ]);
  });

  it("returns empty tree for empty input", () => {
    expect(exposureToTreemap([])).toEqual([]);
  });
});

describe("correlationToHeatmap", () => {
  it("emits n² triplets with clamped values and labels", () => {
    const { data, labels } = correlationToHeatmap(
      ["A", "B"],
      [
        [1, 2],
        [3, 1],
      ]
    );

    expect(labels).toEqual(["A", "B"]);
    expect(data).toHaveLength(4);
    expect(data[0]).toEqual([0, 0, 1]);
    expect(data[1]).toEqual([0, 1, 1]); // 2 clamped to 1
    expect(data[2]).toEqual([1, 0, 1]); // 3 clamped to 1
    expect(data[3]).toEqual([1, 1, 1]);
  });
});

describe("confidenceToEcharts", () => {
  const points: SignalPoint[] = [
    { time: 3000, analyst: "technical", confidence: 0.7 },
    { time: 1000, analyst: "technical", confidence: 0.5 },
    { time: 2000, analyst: "macro", confidence: 0.9 },
  ];

  it("groups per analyst, sorts by time, uses epoch ms", () => {
    const { series } = confidenceToEcharts(points);

    expect(series.map((s) => s.name).sort()).toEqual(["macro", "technical"]);
    const technical = series.find((s) => s.name === "technical");
    expect(technical?.data).toEqual([
      [1_000_000, 0.5],
      [3_000_000, 0.7],
    ]);
  });

  it("clamps confidence to [0, 1]", () => {
    const { series } = confidenceToEcharts([
      { time: 1000, analyst: "macro", confidence: 1.4 },
      { time: 1000, analyst: "news", confidence: -0.2 },
    ]);
    expect(series.find((s) => s.name === "macro")?.data[0]?.[1]).toBe(1);
    expect(series.find((s) => s.name === "news")?.data[0]?.[1]).toBe(0);
  });
});

describe("toUTCTime", () => {
  it("floors fractional seconds", () => {
    expect(toUTCTime(1000.9)).toBe(1000);
  });
});

describe("heikinAshiToCandles", () => {
  it("computes HA close as (O+H+L+C)/4 and smooths open", () => {
    const bars = [
      { time: 100, open: 10, high: 12, low: 9, close: 11, volume: 5 },
      { time: 200, open: 11, high: 14, low: 10, close: 13, volume: 7 },
    ];
    const out = heikinAshiToCandles(bars);
    expect(out).toHaveLength(2);
    // Candle 1: haClose = (10+12+9+11)/4 = 10.5, haOpen = (10+11)/2 = 10.5
    expect(out[0]!.close).toBeCloseTo(10.5);
    expect(out[0]!.open).toBeCloseTo(10.5);
    // Candle 2: haClose = (11+14+10+13)/4 = 12, haOpen = (10.5+10.5)/2 = 10.5
    expect(out[1]!.close).toBeCloseTo(12);
    expect(out[1]!.open).toBeCloseTo(10.5);
    // haHigh = max(14, 10.5, 12) = 14
    expect(out[1]!.high).toBe(14);
  });

  it("skips non-finite bars (defensive NaN guard)", () => {
    const bars = [
      { time: 100, open: 10, high: 12, low: 9, close: 11, volume: 5 },
      { time: 200, open: Number.NaN, high: 14, low: 10, close: 13, volume: 7 },
      { time: 300, open: 12, high: 15, low: 11, close: 14, volume: 9 },
    ];
    const out = heikinAshiToCandles(bars);
    expect(out).toHaveLength(2);
  });
});
