import { create } from "zustand";

export interface MarketTick {
  symbol: string;
  bid: number;
  ask: number;
  last: number;
  timestamp: string;
}

interface MarketState {
  ticks: Record<string, MarketTick>;
  history: Record<string, MarketTick[]>;
}

interface MarketActions {
  upsertTick: (tick: MarketTick) => void;
  getTick: (symbol: string) => MarketTick | undefined;
  getHistory: (symbol: string) => MarketTick[];
}

const MAX_HISTORY_PER_SYMBOL = 1_000;
const EMPTY_HISTORY: MarketTick[] = [];

export const useMarketStore = create<MarketState & MarketActions>((set, get) => ({
  ticks: {},
  history: {},

  upsertTick: (tick) => {
    set((state) => {
      const symbolHistory = state.history[tick.symbol] ?? [];
      const nextHistory = [...symbolHistory, tick].slice(-MAX_HISTORY_PER_SYMBOL);

      return {
        ticks: { ...state.ticks, [tick.symbol]: tick },
        history: { ...state.history, [tick.symbol]: nextHistory },
      };
    });
  },

  getTick: (symbol) => get().ticks[symbol],

  getHistory: (symbol) => get().history[symbol] ?? EMPTY_HISTORY,
}));
