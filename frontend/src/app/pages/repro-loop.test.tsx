import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, vi, beforeEach, afterEach } from 'vitest';
import { DashboardPage } from '@/app/pages/dashboard';

// NOTE: NO mock of useDemoStreams — use the REAL hook to reproduce.
vi.mock('lightweight-charts');

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DashboardPage />
    </QueryClientProvider>,
  );
}

describe('REPRO real useDemoStreams', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('backend offline')));
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('does not exceed update depth with real demo stream', async () => {
    renderPage();
    vi.advanceTimersByTime(3000);
    expect(screen.getByText('Live P&L')).toBeDefined();
  });
});
