import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { OrderDetailPage } from '@/app/pages/order-detail';
import { ToastProvider } from '@/components/ui/toast';
import { useUiStore } from '@/stores/uiStore';

vi.mock('echarts/core');
vi.mock('echarts/charts');
vi.mock('echarts/components');
vi.mock('echarts/renderers');

function renderPage(orderId = 'ord-001') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[`/orders/${orderId}`]}>
      <QueryClientProvider client={client}>
        <ToastProvider>
          <Routes>
            <Route path="/orders/:orderId" element={<OrderDetailPage />} />
          </Routes>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('OrderDetailPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('backend offline')));
    useUiStore.setState({ killSwitchActive: false });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders order summary and lifecycle timeline', async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText(/Order ord-001/i)).toBeDefined());
    expect(screen.getByTestId('order-lifecycle-timeline')).toBeDefined();
    expect(screen.getByTestId('cancel-order-button')).toBeDefined();
  });

  it('opens confirm dialog and cancels the order', async () => {
    renderPage();

    await waitFor(() => expect(screen.getByTestId('cancel-order-button')).toBeEnabled());

    fireEvent.click(screen.getByTestId('cancel-order-button'));
    await waitFor(() => expect(screen.getByTestId('confirm-cancel-order')).toBeDefined());

    await act(async () => {
      fireEvent.click(screen.getByTestId('confirm-cancel-order'));
    });

    await waitFor(() => expect(screen.queryByTestId('confirm-cancel-order')).toBeNull());
  });

  it('disables cancel button when kill switch is active', async () => {
    useUiStore.setState({ killSwitchActive: true });
    renderPage();

    await waitFor(() => expect(screen.getByTestId('cancel-order-button')).toBeDisabled());
    expect(screen.getByTestId('kill-switch-disabled-hint')).toBeDefined();
  });
});
