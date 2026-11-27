// Model overlay chart: garis harga (entry/SL/TP), marker eksekusi, dan angka
// untuk HUD. Semua nilai berasal dari state desk (/positions, /orders) —
// tidak ada harga yang dikarang di client.
//
// Aturan bentuk (dipakai CandleChart):
//   overlay = { id, price, color, dashed, title }
//   marker  = SeriesMarker (lihat lightweight-charts) dengan time = detik
//             bucket chart, jadi marker selalu menempel di candle yang ada.
//
// Simbol lain diabaikan: chart menampilkan satu simbol, jadi order/posisi
// XAUUSD tidak boleh muncul sebagai garis di chart BTCUSD.

const LINE_SOLID = 'solid'
const BUY = '#10b981'
const SELL = '#ef4444'
const AMBER = '#f59e0b'
const MUTED = '#8b909e'

const num = (v) => (v == null || Number.isNaN(Number(v)) ? null : Number(v))
const isBuy = (side) => String(side || '').toLowerCase() === 'buy'

// Waktu (ms) -> detik bucket chart yang paling dekat ke BELAKANG.
// Dipakai untuk marker: lightweight-charts menolak time yang tidak ada di
// data (marker hilang tanpa error), jadi kita tempelkan ke candle nyata.
export function snapToBar(bars, ms) {
  if (!bars || !bars.length || !Number.isFinite(ms)) return null
  const t = Math.floor(ms / 1000)
  if (t < bars[0].time) return bars[0].time
  let lo = 0
  let hi = bars.length - 1
  let best = bars[0].time
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (bars[mid].time <= t) {
      best = bars[mid].time
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  return best
}

export function fmtPrice(v, digits = 2) {
  const n = num(v)
  return n == null ? '·' : n.toFixed(digits)
}

export function fmtUsd(v) {
  const n = num(v)
  if (n == null) return '·'
  return `${n >= 0 ? '+' : '-'}$${Math.abs(n).toFixed(2)}`
}

// Status order yang masih "hidup" (belum tereksekusi / belum gagal).
const PENDING_STATUS = new Set(['PENDING', 'SENT', 'DELIVERED', 'NEW', 'STUCK'])
// Status order yang sudah jadi posisi/eksekusi pasar.
const FILLED_STATUS = new Set(['FILLED'])

export function isPendingOrder(o) {
  return PENDING_STATUS.has(String(o?.status || '').toUpperCase())
}

export function isFilledOrder(o) {
  return FILLED_STATUS.has(String(o?.status || '').toUpperCase())
}

// Awal hari WIB (UTC+7) untuk filter "Eksekusi hari ini".
export function startOfTodayWib(now = Date.now()) {
  const WIB_MS = 7 * 3600 * 1000
  const local = now + WIB_MS
  return Math.floor(local / 86400000) * 86400000 - WIB_MS
}

// Posisi OPEN simbol aktif -> garis entry/SL/TP + label PnL berjalan.
export function positionOverlays({ positions, orders, symbol, digits = 2 }) {
  const byId = new Map((orders || []).map((o) => [String(o.id), o]))
  const out = []
  for (const p of positions || []) {
    if (p.symbol !== symbol) continue
    if (String(p.status ?? 'OPEN').toUpperCase() !== 'OPEN') continue
    const buy = isBuy(p.side)
    const entry = num(p.entry)
    const order = p.orderId != null ? byId.get(String(p.orderId)) : null
    const sl = num(p.sl) ?? num(order?.sl)
    const tp = num(p.tp) ?? num(order?.tp)
    const id = String(p.id ?? p.orderId ?? `${symbol}-${entry}`)
    const sideLabel = buy ? 'BUY' : 'SELL'
    const vol = num(p.volume)
    if (entry != null) {
      out.push({
        id: `pos-entry-${id}`,
        price: entry,
        color: buy ? BUY : SELL,
        dashed: false,
        title: `${sideLabel} ${vol != null ? vol.toFixed(2) : '·'} @ ${fmtPrice(entry, digits)}${p.pnl != null ? ` · ${fmtUsd(p.pnl)}` : ''}`,
        tag: 'entry',
      })
    }
    if (sl != null) {
      out.push({
        id: `pos-sl-${id}`,
        price: sl,
        color: SELL,
        dashed: true,
        title: `SL ${fmtPrice(sl, digits)}`,
        tag: 'sl',
      })
    }
    if (tp != null) {
      out.push({
        id: `pos-tp-${id}`,
        price: tp,
        color: BUY,
        dashed: true,
        title: `TP ${fmtPrice(tp, digits)}`,
        tag: 'tp',
      })
    }
  }
  return out
}

// Order pending simbol aktif -> garis putus-putus amber di harga permintaan.
export function pendingOverlays({ orders, symbol, digits = 2 }) {
  return (orders || [])
    .filter((o) => o.symbol === symbol && isPendingOrder(o))
    .map((o) => {
      const price = num(o.price_requested) ?? num(o.fill)
      if (price == null) return null
      const buy = isBuy(o.side)
      const vol = num(o.volume)
      return {
        id: `ord-${o.id}`,
        price,
        color: buy ? BUY : SELL,
        dashed: true,
        title: `PENDING ${buy ? 'BUY' : 'SELL'} ${vol != null ? vol.toFixed(2) : '·'} @ ${fmtPrice(price, digits)}`,
        tag: 'pending',
      }
    })
    .filter(Boolean)
}

// Marker eksekusi (order FILLED) + exit posisi CLOSED, ditempel ke candle
// yang benar-benar ada di chart (snapToBar).
export function tradeMarkers({ orders, positions, bars, symbol, digits = 2 }) {
  if (!bars || !bars.length) return []
  const out = []
  const byId = new Map((orders || []).map((o) => [String(o.id), o]))

  for (const o of orders || []) {
    if (o.symbol !== symbol || !isFilledOrder(o)) continue
    const price = num(o.fill) ?? num(o.price_filled) ?? num(o.price_requested)
    const ms = o.createdMs ?? (o.created_at ? new Date(o.created_at).getTime() : null)
    const time = snapToBar(bars, ms)
    if (time == null) continue
    const buy = isBuy(o.side)
    const vol = num(o.volume)
    out.push({
      time,
      position: buy ? 'belowBar' : 'aboveBar',
      shape: buy ? 'arrowUp' : 'arrowDown',
      color: buy ? BUY : SELL,
      text: `${buy ? 'BUY' : 'SELL'} ${vol != null ? vol.toFixed(2) : '·'}${price != null ? ` @ ${fmtPrice(price, digits)}` : ''}`,
      size: 1,
    })
  }

  for (const p of positions || []) {
    if (p.symbol !== symbol) continue
    if (String(p.status ?? '').toUpperCase() !== 'CLOSED') continue
    const close = num(p.close_price) ?? num(p.exit_price)
    const ms = p.closed_at ? new Date(p.closed_at).getTime() : null
    const time = snapToBar(bars, ms)
    if (time == null) continue
    const pnl = num(p.pnl)
    const order = p.orderId != null ? byId.get(String(p.orderId)) : null
    const exitTag = p.exit_reason ? String(p.exit_reason).toUpperCase() : 'EXIT'
    out.push({
      time,
      position: 'aboveBar',
      shape: 'circle',
      color: pnl != null && pnl < 0 ? SELL : AMBER,
      text: `${exitTag}${pnl != null ? ` ${fmtUsd(pnl)}` : close != null ? ` @ ${fmtPrice(close, digits)}` : ''}`,
      size: 0.8,
    })
  }

  // Marker harus urut waktu naik (kontrak lightweight-charts).
  return out.sort((a, b) => a.time - b.time)
}

// Semua overlay simbol aktif: posisi dulu (paling penting), lalu pending.
export function buildOverlays({ positions, orders, symbol, digits }) {
  return [
    ...positionOverlays({ positions, orders, symbol, digits }),
    ...pendingOverlays({ orders, symbol, digits }),
  ]
}

// Rekap untuk dock bawah + HUD: hanya hitungan nyata dari state.
export function dockModel({ positions, orders, symbol }) {
  const open = (positions || []).filter(
    (p) => String(p.status ?? 'OPEN').toUpperCase() === 'OPEN',
  )
  const pending = (orders || []).filter(isPendingOrder)
  const since = startOfTodayWib()
  const today = (orders || []).filter((o) => {
    if (!isFilledOrder(o)) return false
    const ms = o.createdMs ?? (o.created_at ? new Date(o.created_at).getTime() : null)
    return ms != null && ms >= since
  })
  const floating = open.reduce((a, p) => a + (num(p.pnl) ?? 0), 0)
  return {
    open,
    pending,
    today,
    floating,
    openForSymbol: open.filter((p) => p.symbol === symbol),
  }
}

export { BUY, SELL, AMBER, MUTED, LINE_SOLID }
