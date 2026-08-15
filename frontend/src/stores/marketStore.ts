import { create } from "zustand";

export interface MarketTick {
  symbol: string;
  bid: number;
  ask: number;
  last: number;
  timestamp: string;
}

export interface CandlestickBar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

interface MarketState {
  ticks: Record<string, MarketTick>;
  history: Record<string, MarketTick[]>;
  bars: Record<string, CandlestickBar[]>;
}

interface MarketActions {
  upsertTick: (tick: MarketTick) => void;
  getTick: (symbol: string) => MarketTick | undefined;
  getHistory: (symbol: string) => MarketTick[];
  upsertBar: (symbol: string, bar: CandlestickBar) => void;
  getBars: (symbol: string) => CandlestickBar[];
}

const MAX_HISTORY_PER_SYMBOL = 1_000;
const EMPTY_HISTORY: MarketTick[] = [];
const EMPTY_BARS: CandlestickBar[] = [];

export const useMarketStore = create<MarketState & MarketActions>((set, get) => ({
  ticks: {},
  history: {},
  bars: {},

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

  upsertBar: (symbol, bar) => {
    set((state) => {
      const symbolBars = state.bars[symbol] ?? [];
      const nextBars = [...symbolBars, bar].slice(-500);
      return { bars: { ...state.bars, [symbol]: nextBars } };
    });
  },

  getTick: (symbol) => get().ticks[symbol],

  getHistory: (symbol) => get().history[symbol] ?? EMPTY_HISTORY,

  getBars: (symbol) => get().bars[symbol] ?? EMPTY_BARS,
}));
