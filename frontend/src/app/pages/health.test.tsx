import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { HealthPage } from './health';

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('HealthPage', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        status: 200,
        text: async () =>
          JSON.stringify({
            meta: {
              api_version: 'v1',
              timestamp: '2026-08-01T00:00:00Z',
              request_id: 'r1',
              status: 'ok',
            },
            data: {
              symbol: 'XAUUSD',
              bid: 2400.5,
              ask: 2400.8,
              spread: 0.3,
              timestamp: '2026-08-01T00:00:00Z',
            },
            error: null,
          }),
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders quote from API', async () => {
    renderWithQuery(<HealthPage />);

    expect(screen.getByText('Loading quote...')).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText('XAUUSD')).toBeInTheDocument());
    expect(screen.getByText('2400.50')).toBeInTheDocument();
  });
});
