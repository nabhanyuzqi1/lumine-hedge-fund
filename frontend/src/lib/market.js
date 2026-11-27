// Kontrak multipair UI: daftar simbol yang dikenal + metadata per simbol.
// contract = nilai dolar per 1.00 pergerakan harga per lot
// (XAUUSD: 100 oz/lot · BTCUSD: 1 coin/lot) — dipakai kalkulasi risiko
// OrderForm; slDist/tpDist = jarak hint SL/TP wajar per simbol.
import { useCallback, useSyncExternalStore } from 'react'

export const SYMBOLS = {
  XAUUSD: { digits: 2, slDist: 5, tpDist: 8, contract: 100 },
  BTCUSD: { digits: 2, slDist: 150, tpDist: 250, contract: 1 },
}

export const DEFAULT_SYMBOL = 'XAUUSD'

export function isSymbol(s) {
  return Object.prototype.hasOwnProperty.call(SYMBOLS, s)
}

// Sesi likuiditas dari jam UTC. Tick SSE tidak membawa sessions, jadi UI
// menghitung sendiri (logika sama dengan simulator demo). BTCUSD crypto:
// likuid 24/7 — semua sesi utama aktif.
export function sessionsFor(symbol, d = new Date()) {
  if (symbol === 'BTCUSD') return ['asia', 'london', 'ny']
  const h = d.getUTCHours() + d.getUTCMinutes() / 60
  const s = []
  if (h >= 0 && h < 9) s.push('asia')
  if (h >= 7 && h < 16) s.push('london')
  if (h >= 12.5 && h < 21) s.push('ny')
  return s.length ? s : ['sydney']
}

// ── status pasar (GET /market/status?symbol=) ─────────────────────────────
// Kontrak backend: { market_status: OPEN|CLOSED|UNKNOWN, market_close_reason,
// trade_mode, last_tick_ts, last_tick_age_s, next_open_ts, ea_seen_s, source }.
// Satu poller per simbol dipakai bersama semua widget (Dashboard, chart,
// Regime, order form) supaya endpoint ini tidak dipanggil berulang-ulang.
export const MARKET_POLL_MS = 20000

// Pesan tunggal untuk tombol Kirim & error HTTP 409 (string sama dengan
// detail dari API supaya user melihat satu kalimat, bukan dua versi).
export const MARKET_CLOSED_MSG =
  'Market sedang tutup — order baru dinonaktifkan hingga sesi buka'

// Alasan tutup dari server -> kalimat pendek untuk badge.
const REASON_LABEL = {
  weekend: 'akhir pekan',
  session: 'jeda sesi',
  holiday: 'libur bursa',
  broker: 'tutup broker',
  no_data: 'belum ada data tick',
}

const TRADE_MODE_LABEL = {
  FULL: 'order penuh',
  CLOSEONLY: 'hanya tutup posisi',
  DISABLED: 'order dimatikan',
}

const STATUS_VALUES = new Set(['OPEN', 'CLOSED', 'UNKNOWN'])

// WIB = UTC+7 tetap (tanpa DST). Format manual supaya badge tidak bergantung
// pada locale/ICU browser dan selalu menyebut zona waktunya.
const WIB_OFFSET_MS = 7 * 3600 * 1000
const DAY_ID = ['Min', 'Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab']

export function fmtWib(iso, { withDay = true } = {}) {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const w = new Date(d.getTime() + WIB_OFFSET_MS)
  const hh = String(w.getUTCHours()).padStart(2, '0')
  const mm = String(w.getUTCMinutes()).padStart(2, '0')
  return withDay ? `${DAY_ID[w.getUTCDay()]} ${hh}:${mm} WIB` : `${hh}:${mm} WIB`
}

// Usia detik -> teks pendek (dipakai badge & kartu regime).
export function fmtAgeShort(s) {
  if (s == null || !Number.isFinite(Number(s))) return '·'
  const n = Number(s)
  if (n < 90) return `${Math.round(n)}s`
  if (n < 5400) return `${Math.round(n / 60)}m`
  return `${Math.round(n / 3600)}j`
}

export function marketReasonLabel(reason) {
  if (!reason) return null
  return REASON_LABEL[reason] || reason
}

export function tradeModeLabel(mode) {
  if (!mode) return null
  return TRADE_MODE_LABEL[mode] || mode
}

function statusError(message, code) {
  return Object.assign(new Error(message), { code })
}

function toNumberOrNull(v) {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

// Respons API -> objek status ternormalisasi. Field yang hilang jadi null;
// nilai market_status di luar kontrak dianggap UNKNOWN (tidak menebak).
export function normalizeMarketStatus(body, symbol) {
  const raw = body && typeof body === 'object' ? body : {}
  const status = String(raw.market_status ?? 'UNKNOWN').toUpperCase()
  return {
    symbol: raw.symbol || symbol || null,
    market_status: STATUS_VALUES.has(status) ? status : 'UNKNOWN',
    market_close_reason: raw.market_close_reason ?? null,
    trade_mode: raw.trade_mode ?? null,
    last_tick_ts: raw.last_tick_ts ?? null,
    last_tick_age_s: toNumberOrNull(raw.last_tick_age_s),
    next_open_ts: raw.next_open_ts ?? null,
    ea_seen_s: toNumberOrNull(raw.ea_seen_s),
    source: raw.source ?? null,
  }
}

// GET /market/status satu kali. Throw dengan code UNAVAILABLE bila route belum
// ada (SPA fallback 200 text/html) atau body bukan JSON — UI lalu tampil
// UNKNOWN, bukan status karangan.
export async function fetchMarketStatus(symbol, { signal } = {}) {
  if (!symbol) throw statusError('symbol wajib diisi', 'INVALID')
  let res
  try {
    res = await fetch(`/market/status?symbol=${encodeURIComponent(symbol)}`, {
      credentials: 'include',
      signal,
    })
  } catch (ex) {
    if (ex && ex.name === 'AbortError') throw statusError('permintaan dibatalkan', 'ABORT')
    throw statusError('Tidak bisa menghubungi server status pasar', 'NETWORK')
  }
  if (res.status === 401) throw statusError('Sesi berakhir, login ulang', 'AUTH')
  if (res.status === 404) throw statusError('Endpoint status pasar belum tersedia', 'UNAVAILABLE')
  if (!res.ok) throw statusError(`Gagal memuat status pasar (HTTP ${res.status})`, 'HTTP')
  const type = res.headers.get('content-type') || ''
  if (!type.includes('application/json')) {
    throw statusError('Endpoint status pasar belum tersedia', 'UNAVAILABLE')
  }
  const body = await res.json().catch(() => null)
  if (!body || typeof body !== 'object') {
    throw statusError('Respons status pasar tidak valid', 'INVALID')
  }
  return normalizeMarketStatus(body, symbol)
}

// ── store status pasar (satu poller per simbol, 20 detik) ────────────────
const EMPTY_SNAPSHOT = Object.freeze({
  symbol: null,
  status: 'UNKNOWN',
  reason: null,
  tradeMode: null,
  lastTickTs: null,
  lastTickAgeS: null,
  nextOpen: null,
  source: null,
  error: null,
  code: null,
  lastOkAt: null,
})

const entries = new Map()

function buildSnapshot(entry) {
  const d = entry.data
  return {
    symbol: entry.symbol,
    status: d && STATUS_VALUES.has(d.market_status) ? d.market_status : 'UNKNOWN',
    reason: d ? d.market_close_reason : null,
    tradeMode: d ? d.trade_mode : null,
    lastTickTs: d ? d.last_tick_ts : null,
    lastTickAgeS: d ? d.last_tick_age_s : null,
    nextOpen: d ? d.next_open_ts : null,
    source: d ? d.source : null,
    error: entry.error,
    code: entry.code,
    lastOkAt: entry.lastOkAt,
  }
}

function notify(entry) {
  entry.snapshot = buildSnapshot(entry)
  for (const fn of entry.listeners) fn()
}

function getEntry(symbol) {
  let entry = entries.get(symbol)
  if (!entry) {
    entry = {
      symbol,
      data: null,
      error: null,
      code: null,
      lastOkAt: null,
      snapshot: { ...EMPTY_SNAPSHOT, symbol },
      listeners: new Set(),
      timer: null,
      ctrl: null,
      inflight: false,
    }
    entries.set(symbol, entry)
  }
  return entry
}

function snapshotFor(symbol) {
  const entry = symbol ? entries.get(symbol) : null
  return entry ? entry.snapshot : EMPTY_SNAPSHOT
}

async function poll(entry) {
  if (entry.inflight) return
  entry.inflight = true
  const ctrl = new AbortController()
  entry.ctrl = ctrl
  try {
    const data = await fetchMarketStatus(entry.symbol, { signal: ctrl.signal })
    entry.data = data
    entry.error = null
    entry.code = null
    entry.lastOkAt = Date.now()
  } catch (ex) {
    if (ex && ex.code === 'ABORT') return
    // Data terakhir dipertahankan (dengan penanda error), tidak dihapus:
    // badge tetap bisa menampilkan status terakhir yang diketahui.
    entry.error = ex.message || 'Gagal memuat status pasar'
    entry.code = ex.code || 'NETWORK'
  } finally {
    entry.inflight = false
    entry.ctrl = null
    if (entry.listeners.size) notify(entry)
  }
}

function subscribeSymbol(symbol, cb) {
  if (!symbol) return () => {}
  const entry = getEntry(symbol)
  entry.listeners.add(cb)
  if (!entry.timer) {
    poll(entry)
    entry.timer = setInterval(() => poll(entry), MARKET_POLL_MS)
  }
  return () => {
    entry.listeners.delete(cb)
    if (!entry.listeners.size) {
      clearInterval(entry.timer)
      entry.timer = null
      if (entry.ctrl) entry.ctrl.abort()
    }
  }
}

/**
 * Status pasar simbol aktif: poll 20 detik + saat simbol berganti.
 * Bentuk: { symbol, status: 'OPEN'|'CLOSED'|'UNKNOWN', reason, tradeMode,
 * lastTickTs, lastTickAgeS, nextOpen, source, error, code, lastOkAt }.
 * Endpoint belum ada / gagal -> status UNKNOWN dengan `error` terisi.
 */
export function useMarketStatus(symbol) {
  const subscribe = useCallback((cb) => subscribeSymbol(symbol, cb), [symbol])
  const getSnapshot = useCallback(() => snapshotFor(symbol), [symbol])
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
}

export function isMarketClosed(market) {
  return market?.status === 'CLOSED'
}

// Error submit order yang berarti pasar tutup (HTTP 409 code market_closed).
// api.js melempar Error berisi `detail`; code dipakai bila nanti dilampirkan.
export function isMarketClosedError(ex) {
  if (!ex) return false
  if (String(ex.code || '').toLowerCase() === 'market_closed') return true
  return /market[^.]{0,24}tutup/i.test(String(ex.message || ''))
}
