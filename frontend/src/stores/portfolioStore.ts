import { create } from 'zustand';

export interface Position {
  id: string;
  portfolio_id: string;
  symbol: string;
  quantity: number;
  side: 'LONG' | 'SHORT';
  avg_entry_price: number;
  unrealized_pnl: number;
  updated_at: string;
}

export interface Order {
  id: string;
  portfolio_id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  status: 'PENDING' | 'ACTIVE' | 'FILLED' | 'CANCELLED';
  type: string;
  created_at: string;
}

interface PortfolioState {
  positions: Record<string, Position>;
  orders: Record<string, Order>;
}

interface PortfolioActions {
  upsertPosition: (position: Position) => void;
  removePosition: (id: string) => void;
  upsertOrder: (order: Order) => void;
  removeOrder: (id: string) => void;
  getPositions: () => Position[];
  getOrders: () => Order[];
  getOrdersByStatus: (statuses: Order['status'][]) => Order[];
}

export const usePortfolioStore = create<PortfolioState & PortfolioActions>((set, get) => ({
  positions: {},
  orders: {},

  upsertPosition: (position) => {
    set((state) => ({
      positions: { ...state.positions, [position.id]: position },
    }));
  },

  removePosition: (id) => {
    set((state) => {
      const next = { ...state.positions };
      delete next[id];
      return { positions: next };
    });
  },

  upsertOrder: (order) => {
    set((state) => ({
      orders: { ...state.orders, [order.id]: order },
    }));
  },

  removeOrder: (id) => {
    set((state) => {
      const next = { ...state.orders };
      delete next[id];
      return { orders: next };
    });
  },

  getPositions: () => Object.values(get().positions),

  getOrders: () => Object.values(get().orders),

  getOrdersByStatus: (statuses) =>
    Object.values(get().orders).filter((order) => statuses.includes(order.status)),
}));
