import { QueryClient } from "@tanstack/react-query";

/**
 * Shared TanStack Query client for the Lumine portal.
 *
 * Defaults are tuned for institutional dashboards:
 * - Short staleTime for market data freshness.
 * - Exponential retries for transient REST failures.
 * - Window-focus refetch so reopened tabs catch up quickly.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 3,
      retryDelay: (attemptIndex) => Math.min(1_000 * 2 ** attemptIndex, 30_000),
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
    },
  },
});
