/**
 * Manual mock for `lightweight-charts` (jsdom has no canvas). Auto-applied
 * to every test file — component tests assert against instances captured
 * here via `__getCharts()`.
 */
import { vi } from "vitest";

export const ColorType = { Solid: "solid" };
export const CrosshairMode = { Normal: 0 };
export const CandlestickSeries = "CandlestickSeries";
export const HistogramSeries = "HistogramSeries";
export const AreaSeries = "AreaSeries";
export const LineSeries = "LineSeries";

const charts: Array<ReturnType<typeof makeChart>> = [];

function makeSeries() {
  return {
    setData: vi.fn(),
    update: vi.fn(),
    applyOptions: vi.fn(),
    remove: vi.fn(),
  };
}

function makeChart() {
  const chart = {
    addSeries: vi.fn(() => makeSeries()),
    priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
    remove: vi.fn(),
    resize: vi.fn(),
    applyOptions: vi.fn(),
  };
  charts.push(chart);
  return chart;
}

export const createChart = vi.fn(() => makeChart());

export function __getCharts() {
  return charts;
}

export function __resetCharts() {
  charts.length = 0;
  createChart.mockClear();
}
