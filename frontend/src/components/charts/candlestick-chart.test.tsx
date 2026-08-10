import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as lwc from 'lightweight-charts';

vi.mock('lightweight-charts');

import { CandlestickChart, TICK_DEBOUNCE_MS } from '@/components/charts/candlestick-chart';
import type { ChartBar } from '@/data/fixtures';
import { CHART_COLORS } from '@/lib/chart-theme';
import type { MarketTick } from '@/stores';

/**
 * Manual `__mocks__/lightweight-charts` auto-applies in jsdom; instances are
 * captured per test and asserted via `__getCharts()`.
 */
type MockSeries = {
  setData: ReturnType<typeof vi.fn>;
  update: ReturnType<typeof vi.fn>;
  remove: ReturnType<typeof vi.fn>;
  applyOptions: ReturnType<typeof vi.fn>;
};
type MockChart = {
  addSeries: ReturnType<typeof vi.fn>;
  priceScale: ReturnType<typeof vi.fn>;
  remove: ReturnType<typeof vi.fn>;
  resize: ReturnType<typeof vi.fn>;
};
const mockLwc = lwc as unknown as {
  __getCharts(): MockChart[];
  __resetCharts(): void;
};

const BARS: ChartBar[] = [
  { time: 1000, open: 100, high: 110, low: 95, close: 105, volume: 500 },
  { time: 2000, open: 105, high: 108, low: 100, close: 98, volume: 700 },
];

const TICK: MarketTick = {
  symbol: 'XAUUSD',
  bid: 111.8,
  ask: 112.2,
  last: 112,
  timestamp: '2026-08-10T00:00:00Z',
};

describe('CandlestickChart', () => {
  beforeEach(() => {
    mockLwc.__resetCharts();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('creates candle + volume series and loads bars once', () => {
    render(<CandlestickChart bars={BARS} timeframe="5m" />);

    expect(lwc.createChart).toHaveBeenCalledTimes(1);
    const chart = mockLwc.__getCharts()[0];
    expect(chart).toBeDefined();

    const addCalls = chart!.addSeries.mock.calls;
    expect(addCalls.map((call) => call[0])).toEqual(['CandlestickSeries', 'HistogramSeries']);

    const candles = chart!.addSeries.mock.results[0]!.value as MockSeries;
    const volumes = chart!.addSeries.mock.results[1]!.value as MockSeries;
    expect(candles.setData).toHaveBeenCalledWith([
      { time: 1000, open: 100, high: 110, low: 95, close: 105 },
      { time: 2000, open: 105, high: 108, low: 100, close: 98 },
    ]);
    expect(volumes.setData).toHaveBeenCalledWith([
      { time: 1000, value: 500, color: CHART_COLORS.up },
      { time: 2000, value: 700, color: CHART_COLORS.down },
    ]);
  });

  it('debounces live ticks and mutates only the last bar', () => {
    vi.useFakeTimers();
    render(<CandlestickChart bars={BARS} lastTick={TICK} timeframe="5m" />);

    const chart = mockLwc.__getCharts()[0]!;
    const candles = chart.addSeries.mock.results[0]!.value as MockSeries;
    const volumes = chart.addSeries.mock.results[1]!.value as MockSeries;

    // Inside the debounce window: no update yet.
    act(() => {
      vi.advanceTimersByTime(TICK_DEBOUNCE_MS - 1);
    });
    expect(candles.update).not.toHaveBeenCalled();

    // Past the window: close moves to tick, high raised, low untouched.
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(candles.update).toHaveBeenCalledTimes(1);
    expect(candles.update).toHaveBeenCalledWith({
      time: 2000,
      open: 105,
      high: 112,
      low: 100,
      close: 112,
    });
    expect(volumes.update).toHaveBeenCalledWith({
      time: 2000,
      value: 700,
      color: CHART_COLORS.up,
    });
  });

  it('renders timeframe buttons and reports changes', () => {
    const onTimeframeChange = vi.fn();
    render(<CandlestickChart bars={BARS} timeframe="5m" onTimeframeChange={onTimeframeChange} />);

    const active = screen.getByRole('button', { name: '5m' });
    expect(active).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('button', { name: '1H' }));
    expect(onTimeframeChange).toHaveBeenCalledWith('1H');
  });

  it('removes the chart instance on unmount', () => {
    const { unmount } = render(<CandlestickChart bars={BARS} timeframe="5m" />);
    const chart = mockLwc.__getCharts()[0]!;

    unmount();
    expect(chart.remove).toHaveBeenCalledTimes(1);
  });
});
