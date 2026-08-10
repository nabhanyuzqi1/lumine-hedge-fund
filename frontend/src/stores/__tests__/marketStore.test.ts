import { describe, it, expect } from 'vitest';
import { useMarketStore, type MarketTick } from '../marketStore';

function makeTick(symbol: string, price: number): MarketTick {
  return {
    symbol,
    bid: price,
    ask: price + 0.5,
    last: price,
    timestamp: new Date().toISOString(),
  };
}

describe('marketStore', () => {
  it('upserts and retrieves ticks', () => {
    useMarketStore.getState().upsertTick(makeTick('XAUUSD', 2400));

    const tick = useMarketStore.getState().getTick('XAUUSD');
    expect(tick).toBeDefined();
    expect(tick?.last).toBe(2400);
  });

  it('caps history per symbol to 1000 entries', () => {
    for (let i = 0; i < 1_050; i++) {
      useMarketStore.getState().upsertTick(makeTick('XAUUSD', 2400 + i));
    }

    const history = useMarketStore.getState().getHistory('XAUUSD');
    expect(history).toHaveLength(1_000);
    expect(history[0]!.last).toBe(2400 + 50);
    expect(history[history.length - 1]!.last).toBe(2400 + 1_049);
  });
});
