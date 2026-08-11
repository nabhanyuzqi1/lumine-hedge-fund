import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LineageDetailPage } from '@/app/pages/lineage-detail';

vi.mock('echarts/core');
vi.mock('echarts/charts');
vi.mock('echarts/components');
vi.mock('echarts/renderers');

function renderPage(lineageId = 'lin-001') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[`/lineage/${lineageId}`]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/lineage/:lineageId" element={<LineageDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('LineageDetailPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('backend offline')));
    vi.stubGlobal('navigator', {
      ...navigator,
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders lineage summary and decision tree', async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText(/Lineage lin-001/i)).toBeDefined());
    expect(screen.getByTestId('lineage-viewer')).toBeDefined();
    expect(screen.getByText(/IC proposal — lin-001/i)).toBeDefined();
    expect(screen.getByText(/override present/i)).toBeDefined();
  });

  it('filters tree by search term', async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText(/IC proposal — lin-001/i)).toBeDefined());
    expect(screen.getByText(/macro \/ rates/i)).toBeDefined();

    fireEvent.change(screen.getByTestId('lineage-search'), { target: { value: 'sizer' } });

    await waitFor(() => {
      expect(screen.queryByText(/macro \/ rates/i)).toBeNull();
      expect(screen.getByText(/portfolio_sizer \/ size/i)).toBeDefined();
    });
  });

  it('copies path to clipboard', async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText(/IC proposal — lin-001/i)).toBeDefined());
    fireEvent.click(screen.getByTestId('copy-path-technical'));

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('decision.technical'),
    );
  });
});
