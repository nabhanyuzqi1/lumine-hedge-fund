import { create } from 'zustand';
import type { SSEStatus } from '@/hooks/useSSE';

export interface StreamState {
  key: string;
  status: SSEStatus;
  lastEventId: string | null;
  stale: boolean;
  error: string | null;
  connectedAt: string | null;
}

interface StreamStateMap {
  streams: Record<string, StreamState>;
}

interface StreamActions {
  setStreamState: (key: string, partial: Partial<StreamState>) => void;
  getStreamState: (key: string) => StreamState;
  getAllStreams: () => StreamState[];
}

function makeInitialStreamState(key: string): StreamState {
  return {
    key,
    status: 'idle',
    lastEventId: null,
    stale: false,
    error: null,
    connectedAt: null,
  };
}

export const useStreamStore = create<StreamStateMap & StreamActions>((set, get) => ({
  streams: {},

  setStreamState: (key, partial) => {
    set((state) => {
      const current = state.streams[key] ?? makeInitialStreamState(key);
      return {
        streams: {
          ...state.streams,
          [key]: { ...current, ...partial },
        },
      };
    });
  },

  getStreamState: (key) => get().streams[key] ?? makeInitialStreamState(key),

  getAllStreams: () => Object.values(get().streams),
}));
