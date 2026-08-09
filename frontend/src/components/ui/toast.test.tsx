import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

import { ToastProvider, useToast, ToastViewport } from './toast';

function TestHarness() {
  const { toast } = useToast();
  return (
    <div>
      <button
        type="button"
        onClick={() =>
          toast({
            variant: 'success',
            title: 'Order filled',
            description: 'XAUUSD buy @ 2450.30',
            duration: 1000,
          })
        }
      >
        Notify
      </button>
      <button
        type="button"
        onClick={() =>
          toast({
            variant: 'danger',
            title: 'Stream dropped',
          })
        }
      >
        Alert
      </button>
      <ToastViewport />
    </div>
  );
}

describe('Toast', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  it('renders a toast and dismisses manually', () => {
    render(
      <ToastProvider>
        <TestHarness />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Notify' }));
    expect(screen.getByText('Order filled')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss notification' }));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('auto-dismisses after duration', async () => {
    render(
      <ToastProvider>
        <TestHarness />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Notify' }));
    expect(screen.getByText('Order filled')).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(1100));
    await waitFor(() => {
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });
  });

  it('uses assertive aria-live for danger', () => {
    render(
      <ToastProvider>
        <TestHarness />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Alert' }));
    const toast = screen.getByRole('status');
    expect(toast).toHaveAttribute('aria-live', 'assertive');
  });
});
