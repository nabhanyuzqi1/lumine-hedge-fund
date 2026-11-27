// Simulator mode demo · dipakai saat backend belum hidup (VITE_DEMO=1 / ?demo=1).
// Seluruh data sintetis dan selalu ditandai "DEMO" di UI. Multipair: dua
// random-walk independen (XAU ~2.6k, BTC ~97k) mengikuti kontrak quotes
// yang sama dengan mode real.

import { SYMBOLS, DEFAULT_SYMBOL, isSymbol, sessionsFor } from './market'

function mulberry32(a) {
  return function () {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const now = () => Date.now()
const fmtId = (n) => 'F2-' + String(n).padStart(4, '0')

// Skala harga demo per simbol: start = harga awal, jitter = rentang gerak
// per tick, slip = slippage fill, maxSpread = ambang RISK_FAIL demo
// (simulasi risk gate spread; backend memakai settings max_spread).
const DEMO_CFG = {
  XAUUSD: { start: 2648.4, jitter: 0.72, slip: 0.05, maxSpread: 0.5 },
  BTCUSD: { start: 97150, jitter: 42, slip: 8, maxSpread: 20 },
}

function spreadFor(d, symbol) {
  const h = d.getUTCHours()
  const rollover = h >= 21 && h < 23
  if (symbol === 'BTCUSD') return (rollover ? 14 : 6) + Math.random() * 6
  return rollover ? 0.42 + Math.random() * 0.25 : 0.14 + Math.random() * 0.14
}

function makeStrategies() {
  const defs = [
    { id: 'ma-cross-h1', name: 'MA Cross H1', track: 'A', symbol: 'XAUUSD', desc: 'EMA 21/55 cross di H1, filter sesi London.', win: 0.54, pf: 1.62, dd: 0.084, sharpe: 1.31, trades: 412 },
    { id: 'ldn-breakout', name: 'London Breakout', track: 'A', symbol: 'XAUUSD', desc: 'Breakout range Asia, target 1.5R, stop di sisi lain range.', win: 0.47, pf: 1.88, dd: 0.112, sharpe: 1.44, trades: 298 },
    { id: 'vol-mean-m15', name: 'Vol Mean M15', track: 'B', symbol: 'BTCUSD', desc: 'Mean reversion ATR-filtered, model lightgbm, fitur likuiditas.', win: 0.58, pf: 1.41, dd: 0.066, sharpe: 1.12, trades: 1264 },
  ]
  return defs.map((d, i) => {
    const rnd = mulberry32(1000 + i * 77)
    let eq = 100
    const curve = []
    for (let k = 0; k < 90; k++) {
      eq += (rnd() - 0.44) * 2.2
      curve.push(Math.max(40, eq))
    }
    return { ...d, mode: 'paper', curve }
  })
}

const emptyState = () => ({
  symbol: DEFAULT_SYMBOL,
  quotes: {},
  positions: [],
  orders: [],
  equity: 10000,
  halted: false,
  strategies: [],
  connection: 'demo',
})

// Satu tick random-walk untuk satu simbol, shape sama dengan quotes real.
function nextQuote(prev, symbol, d) {
  const cfg = DEMO_CFG[symbol]
  const drift = Math.sin(now() / 47000) * cfg.jitter * 0.25
  let price = prev?.price ?? cfg.start
  price = Math.max(cfg.start * 0.4, price + (Math.random() - 0.5) * cfg.jitter + drift)
  const spread = spreadFor(d, symbol)
  return {
    price,
    bid: price - spread / 2,
    ask: price + spread / 2,
    spread,
    sessions: sessionsFor(symbol, d),
    ticks: [...(prev?.ticks || []).slice(-320), price],
  }
}

// Riwayat awal 120 tick saat start agar chart tidak kosong.
function seedQuote(symbol) {
  const cfg = DEMO_CFG[symbol]
  let price = cfg.start
  const ticks = []
  for (let i = 0; i < 120; i++) {
    price += (Math.random() - 0.5) * cfg.jitter
    ticks.push(price)
  }
  const d = new Date()
  const spread = spreadFor(d, symbol)
  return {
    price,
    bid: price - spread / 2,
    ask: price + spread / 2,
    spread,
    sessions: sessionsFor(symbol, d),
    ticks,
  }
}

export function createDemo() {
  let state = emptyState()
  state.strategies = makeStrategies()
  state.connection = 'demo'
  const subs = new Set()
  const tickSubs = new Set()
  let seq = 1
  let timer = null

  const emit = () => subs.forEach((fn) => fn(state))
  const emitTick = () => {
    const q = state.quotes[state.symbol]
    if (!q) return
    tickSubs.forEach((fn) => fn({ symbol: state.symbol, price: q.price, bid: q.bid, ask: q.ask, ts: now() }))
  }

  function tick() {
    const d = new Date()
    const quotes = { ...state.quotes }
    for (const s of Object.keys(SYMBOLS)) quotes[s] = nextQuote(quotes[s], s, d)
    state = {
      ...state,
      quotes,
      positions: state.positions.map((p) => {
        const q = quotes[p.symbol]
        const contract = SYMBOLS[p.symbol]?.contract ?? 1
        return { ...p, pnl: (q.price - p.entry) * (p.side === 'buy' ? 1 : -1) * p.volume * contract }
      }),
    }
    emit()
    emitTick()
  }

  function pushEvent(order, evt) {
    order.events = [...order.events, { t: now(), ...evt }]
    order.status = evt.state
  }

  function transition(order, stateName, note, delay) {
    setTimeout(() => {
      pushEvent(order, { state: stateName, note })
      if (stateName === 'FILLED') {
        const q = state.quotes[order.symbol]
        const slip = (Math.random() - 0.5) * DEMO_CFG[order.symbol].slip
        order.fill = order.side === 'buy' ? q.ask + slip : q.bid + slip
        state = {
          ...state,
          positions: [
            ...state.positions,
            {
              id: order.id,
              orderId: order.id,
              symbol: order.symbol,
              side: order.side,
              volume: order.volume,
              entry: order.fill,
              sl: order.sl,
              tp: order.tp,
              pnl: 0,
              openedAt: now(),
            },
          ],
        }
      }
      emit()
    }, delay)
  }

  return {
    isAuthed: () => localStorage.getItem('fund2_demo_auth') === '1',
    async login(user, pass) {
      if (!user || pass.length < 4) throw new Error('Username dan password (min. 4 karakter) wajib diisi.')
      localStorage.setItem('fund2_demo_auth', '1')
    },
    logout() {
      localStorage.removeItem('fund2_demo_auth')
    },
    start() {
      if (timer) return
      const quotes = {}
      for (const s of Object.keys(SYMBOLS)) quotes[s] = seedQuote(s)
      state = { ...state, quotes }
      emit()
      timer = setInterval(tick, 900)
    },
    stop() {
      clearInterval(timer)
      timer = null
    },
    subscribe(fn) {
      subs.add(fn)
      fn(state)
      return () => subs.delete(fn)
    },
    onTick(fn) {
      tickSubs.add(fn)
      return () => tickSubs.delete(fn)
    },
    setSymbol(sym) {
      if (!isSymbol(sym) || sym === state.symbol) return
      state = { ...state, symbol: sym }
      emit()
      emitTick()
    },
    placeOrder({ symbol, side, volume, sl, tp }) {
      const sym = isSymbol(symbol) ? symbol : state.symbol
      const cfg = DEMO_CFG[sym]
      if (state.halted) {
        const o = { id: fmtId(seq++), symbol: sym, side, volume, sl, tp, status: 'RISK_FAIL', events: [{ t: now(), state: 'RECEIVED' }, { t: now(), state: 'RISK_FAIL', note: 'Kill-switch armed · order ditolak' }] }
        state = { ...state, orders: [o, ...state.orders] }
        emit()
        return o
      }
      const o = { id: fmtId(seq++), symbol: sym, side, volume, sl, tp, status: 'RECEIVED', events: [{ t: now(), state: 'RECEIVED', note: 'Order diterima API' }] }
      state = { ...state, orders: [o, ...state.orders] }
      emit()
      if ((state.quotes[sym]?.spread ?? 0) > cfg.maxSpread) {
        transition(o, 'RISK_FAIL', 'Spread melebihi filter risk gate', 140)
      } else {
        transition(o, 'RISK_PASS', 'Risk gate lolos: SL/TP ada, volume dalam batas', 120)
        transition(o, 'SENT', 'Dikirim ke MT5 bridge', 260)
        transition(o, 'FILLED', 'Terkonfirmasi broker', 620)
      }
      return o
    },
    closePosition(id) {
      const pos = state.positions.find((p) => p.id === id)
      if (!pos) return
      const order = state.orders.find((o) => o.id === pos.orderId)
      if (order) {
        pushEvent(order, { state: 'CLOSED', note: `Posisi ditutup manual · P/L $${pos.pnl.toFixed(2)}` })
      }
      state = { ...state, positions: state.positions.filter((p) => p.id !== id), equity: state.equity + pos.pnl }
      emit()
    },
    setStrategyMode(id, mode) {
      state = { ...state, strategies: state.strategies.map((s) => (s.id === id ? { ...s, mode } : s)) }
      emit()
    },
    setKillSwitch(armed) {
      state = { ...state, halted: armed }
      emit()
    },
    // Event log demo tersimpan di memori pada objek order.
    async loadOrderEvents(id) {
      const order = state.orders.find((o) => o.id === id)
      return order?.events ? [...order.events] : []
    },
    getState: () => state,
  }
}
