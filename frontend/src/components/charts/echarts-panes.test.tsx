import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('echarts/core');
vi.mock('echarts/charts');
vi.mock('echarts/components');
vi.mock('echarts/renderers');

import * as echarts from 'echarts/core';

import { AllocationChart } from '@/components/charts/allocation-chart';
import { ConfidenceChart } from '@/components/charts/confidence-chart';
import { CorrelationChart } from '@/components/charts/correlation-chart';
import type { CorrelationMatrix, ExposureItem, SignalPoint } from '@/data/fixtures';

type MockInstance = {
  setOption: ReturnType<typeof vi.fn>;
  resize: ReturnType<typeof vi.fn>;
  dispose: ReturnType<typeof vi.fn>;
};
const mockEcharts = echarts as unknown as {
  init: ReturnType<typeof vi.fn>;
  __getInstances(): MockInstance[];
  __resetInstances(): void;
};

const ITEMS: ExposureItem[] = [
  { symbol: 'XAUUSD', assetClass: 'Metals', weight: 0.38 },
  { symbol: 'XAGUSD', assetClass: 'Metals', weight: 0.08 },
  { symbol: 'EURUSD', assetClass: 'FX', weight: 0.16 },
];

const SYMBOLS = ['A', 'B'];
const MATRIX: CorrelationMatrix = [
  [1, 0.4],
  [0.4, 1],
];

const POINTS: SignalPoint[] = [
  { time: 1000, analyst: 'technical', confidence: 0.7 },
  { time: 2000, analyst: 'macro', confidence: 0.4 },
  { time: 1500, analyst: 'technical', confidence: 0.65 },
];

type EchartsOption = {
  series: Array<{ type: string; name?: string; data: unknown }>;
};

async function latestOption(): Promise<EchartsOption> {
  const instance = mockEcharts.__getInstances()[0]!;
  await waitFor(() => expect(instance.setOption).toHaveBeenCalled());
  return instance.setOption.mock.calls.at(-1)![0] as EchartsOption;
}

describe('ECharts panes', () => {
  beforeEach(() => {
    mockEcharts.__resetInstances();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('AllocationChart emits a treemap grouped by asset class', async () => {
    render(<AllocationChart items={ITEMS} />);

    expect(screen.getByText('Capital Allocation')).toBeDefined();
    const option = await latestOption();

    expect(option.series[0]!.type).toBe('treemap');
    const data = option.series[0]!.data as Array<{ name: string; value: number }>;
    expect(data.map((n) => n.name)).toEqual(['Metals', 'FX']);
    expect(data[0]!.value).toBeCloseTo(0.46);
  });

  it('CorrelationChart emits an n×n heatmap with labeled axes', async () => {
    render(<CorrelationChart symbols={SYMBOLS} matrix={MATRIX} />);

    expect(screen.getByText('Cross-Asset Correlation')).toBeDefined();
    const option = await latestOption();

    expect(option.series[0]!.type).toBe('heatmap');
    expect(option.series[0]!.data).toHaveLength(4);
  });

  it('ConfidenceChart emits one line per analyst, time-sorted', async () => {
    render(<ConfidenceChart points={POINTS} />);

    expect(screen.getByText('AI Committee Confidence')).toBeDefined();
    const option = await latestOption();

    const series = option.series as Array<{
      type: string;
      name: string;
      data: Array<[number, number]>;
    }>;
    expect(series.map((s) => s.type)).toEqual(['line', 'line']);
    expect(series.map((s) => s.name).sort()).toEqual(['macro', 'technical']);
    const technical = series.find((s) => s.name === 'technical')!;
    expect(technical.data).toEqual([
      [1_000_000, 0.7],
      [1_500_000, 0.65],
    ]);
  });

  it('disposes the instance on unmount', () => {
    const { unmount } = render(<AllocationChart items={ITEMS} />);
    const instance = mockEcharts.__getInstances()[0]!;

    unmount();
    expect(instance.dispose).toHaveBeenCalledTimes(1);
  });
});
