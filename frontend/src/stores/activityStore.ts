import { create } from "zustand";

export type LogLevel = "info" | "warn" | "danger";

export interface ActivityLogEntry {
  id: string;
  stream: string;
  message: string;
  level: LogLevel;
  /** ISO timestamp. */
  timestamp: string;
}

const MAX_ENTRIES = 100;

interface ActivityState {
  entries: ActivityLogEntry[];
}

interface ActivityActions {
  appendLog: (entry: Omit<ActivityLogEntry, "id" | "timestamp">) => void;
  getEntries: () => ActivityLogEntry[];
}

let logSeq = 0;

/**
 * Ring-buffer stream/event activity log (F-Sprint 5). SSE handlers append
 * lifecycle events here once the backend is live; demo streams append
 * synthetic equivalents — identical code path for both.
 */
export const useActivityStore = create<ActivityState & ActivityActions>((set, get) => ({
  entries: [],

  appendLog: (entry) => {
    logSeq += 1;
    set((state) => ({
      entries: [
        ...state.entries,
        { ...entry, id: `log-${logSeq}`, timestamp: new Date().toISOString() },
      ].slice(-MAX_ENTRIES),
    }));
  },

  getEntries: () => get().entries,
}));
