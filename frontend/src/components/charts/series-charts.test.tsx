import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('lightweight-charts');

import * as lwc from 'lightweight-charts';

import { DrawdownChart } from '@/components/charts/drawdown-chart';
import { EquityChart } from '@/components/charts/equity-chart';
import { PnlSparkline } from '@/components/charts/pnl-sparkline';
import type { EquityPoint } from '@/data/fixtures';
import { equityToArea, equityToDrawdown, pnlToLine } from '@/lib/chart-transform';

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
  createChart: ReturnType<typeof vi.fn>;
  __getCharts(): MockChart[];
  __resetCharts(): void;
};

const EQUITY: EquityPoint[] = [
  { time: 1000, value: 100 },
  { time: 2000, value: 110 },
  { time: 3000, value: 99 },
];

describe('EquityChart', () => {
  beforeEach(() => {
    mockLwc.__resetCharts();
  });

  it('renders its card and loads an area series with transformed points', () => {
    render(<EquityChart points={EQUITY} />);

    expect(screen.getByText('Portfolio Equity')).toBeDefined();
    expect(screen.getByText('Daily equity curve · USD')).toBeDefined();

    const chart = mockLwc.__getCharts()[0]!;
    expect(chart.addSeries).toHaveBeenCalledWith('AreaSeries', expect.anything());
    const area = chart.addSeries.mock.results[0]!.value as MockSeries;
    expect(area.setData).toHaveBeenCalledWith(equityToArea(EQUITY));
  });

  it('skips setData on empty input without crashing', () => {
    render(<EquityChart points={[]} />);
    const chart = mockLwc.__getCharts()[0]!;
    const area = chart.addSeries.mock.results[0]!.value as MockSeries;
    expect(area.setData).not.toHaveBeenCalled();
  });
});

describe('DrawdownChart', () => {
  beforeEach(() => {
    mockLwc.__resetCharts();
  });

  it('derives the underwater series from the same equity points', () => {
    render(<DrawdownChart equity={EQUITY} />);

    expect(screen.getByText('Drawdown')).toBeDefined();

    const chart = mockLwc.__getCharts()[0]!;
    const area = chart.addSeries.mock.results[0]!.value as MockSeries;
    const payload = area.setData.mock.calls[0]![0] as Array<{ time: number; value: number }>;
    expect(payload).toEqual(equityToArea(equityToDrawdown(EQUITY)));
    expect(payload.every((p) => p.value <= 0)).toBe(true);
  });
});

describe('PnlSparkline', () => {
  beforeEach(() => {
    mockLwc.__resetCharts();
  });

  it('hides the axes and loads a line series with pnl points', () => {
    render(<PnlSparkline points={EQUITY} />);

    const options = mockLwc.createChart.mock.calls[0]![1] as {
      timeScale: { visible: boolean };
      rightPriceScale: { visible: boolean };
    };
    expect(options.timeScale.visible).toBe(false);
    expect(options.rightPriceScale.visible).toBe(false);

    const chart = mockLwc.__getCharts()[0]!;
    expect(chart.addSeries).toHaveBeenCalledWith('LineSeries', expect.anything());
    const line = chart.addSeries.mock.results[0]!.value as MockSeries;
    expect(line.setData).toHaveBeenCalledWith(pnlToLine(EQUITY));
  });

  it('removes the chart instance on unmount', () => {
    const { unmount } = render(<PnlSparkline points={EQUITY} />);
    const chart = mockLwc.__getCharts()[0]!;

    unmount();
    expect(chart.remove).toHaveBeenCalledTimes(1);
  });
});
