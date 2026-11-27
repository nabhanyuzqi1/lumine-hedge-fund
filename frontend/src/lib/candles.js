// Sumber data candle chart (READ-ONLY): GET /candles?symbol=&tf=&limit=.
// Kontrak backend hari ini melayani M1/M5/M15; H1/H4/D1 sedang ditambahkan
// tim backend. Permintaan timeframe yang belum aktif TIDAK boleh memecahkan
// UI: helper ini jatuh ke timeframe terdekat yang tersedia dan menandai
// `fallback: true` supaya chart menampilkan pemberitahuan, bukan error merah.
//
// Endpoint hanya mendukung `limit` (tanpa offset/from-to), jadi scrollback
// historis dilakukan dengan meminta limit lebih besar lalu menggabungkan
// candle lama di depan data yang sudah ada (lihat CandleChart).

export const TIMEFRAMES = ['M1', 'M5', 'M15', 'H1', 'H4', 'D1']

// Detik per timeframe; dipakai untuk membulatkan waktu tick ke awal periode.
export const TF_SECONDS = {
  M1: 60,
  M5: 300,
  M15: 900,
  H1: 3600,
  H4: 14400,
  D1: 86400,
}

// Timeframe fallback bila backend menolak tf tinggi (belum aktif).
export const TF_FALLBACK = {
  H1: 'M15',
  H4: 'M15',
  D1: 'M15',
}

export const DEFAULT_LIMIT = 500
// Sama dengan CANDLES_MAX_LIMIT di app/routes.py; limit di luar rentang 400.
export const MAX_LIMIT = 2000

export function isTimeframe(tf) {
  return typeof tf === 'string' && Object.prototype.hasOwnProperty.call(TF_SECONDS, tf)
}

export function timeframeSeconds(tf) {
  return TF_SECONDS[tf] || TF_SECONDS.M5
}

// Awal periode candle (epoch ms) untuk sebuah waktu; D1 = hari UTC.
export function bucketStart(ms, tf) {
  const step = timeframeSeconds(tf) * 1000
  return Math.floor(ms / step) * step
}

// Normalisasi timestamp tick: epoch ms, epoch detik, atau ISO string.
// Mengembalikan milidetik, atau null bila tidak bisa dibaca.
export function tickMs(ts) {
  if (ts == null) return null
  if (typeof ts === 'number' && Number.isFinite(ts)) {
    return ts < 1e12 ? ts * 1000 : ts
  }
  if (typeof ts === 'string') {
    const num = Number(ts)
    if (Number.isFinite(num) && ts.trim() !== '') return num < 1e12 ? num * 1000 : num
    const parsed = Date.parse(ts)
    return Number.isNaN(parsed) ? null : parsed
  }
  return null
}

function candleError(message, code, status) {
  return Object.assign(new Error(message), { code, status })
}

async function readError(res, label) {
  let detail = ''
  try {
    const body = await res.json()
    const d = body && body.detail
    if (typeof d === 'string') detail = d
    else if (d && typeof d === 'object') detail = d.message || d.hint || ''
  } catch {
    // body bukan JSON (mis. halaman HTML 502): pakai pesan status saja.
  }
  const code =
    res.status === 401
      ? 'AUTH'
      : res.status === 400 || res.status === 422
        ? 'TF_UNSUPPORTED'
        : 'HTTP'
  return candleError(detail || `${label} (HTTP ${res.status})`, code, res.status)
}

// Baris API -> daftar bar chart. `time` dipaksa ke detik UNIX AWAL bucket
// timeframe (server bisa menyimpan ts legacy di tengah periode), urut naik,
// tanpa duplikat; baris rusak dilewati agar satu data cacat tidak
// mengosongkan seluruh chart. Baris ganda dalam satu bucket: yang terakhir
// (paling baru di respons, server mengirim naik) yang dipakai.
function toBar(row) {
  if (!row || row.ts == null) return null
  const ms = tickMs(row.ts)
  if (ms == null) return null
  const open = Number(row.open)
  const high = Number(row.high)
  const low = Number(row.low)
  const close = Number(row.close)
  if (![open, high, low, close].every(Number.isFinite)) return null
  const volume = Number(row.volume)
  return {
    time: Math.floor(ms / 1000),
    open,
    high,
    low,
    close,
    // Volume = nilai server apa adanya (tidak diakumulasi di client).
    volume: Number.isFinite(volume) ? volume : 0,
  }
}

function normalizeBars(rows, tf) {
  const step = timeframeSeconds(tf)
  const byTime = new Map()
  for (const row of Array.isArray(rows) ? rows : []) {
    const bar = toBar(row)
    if (!bar) continue
    const time = Math.floor(bar.time / step) * step
    byTime.set(time, { ...bar, time })
  }
  return Array.from(byTime.values()).sort((a, b) => a.time - b.time)
}

async function requestCandles(symbol, tf, limit, signal) {
  const url = `/candles?symbol=${encodeURIComponent(symbol)}&tf=${encodeURIComponent(tf)}&limit=${limit}`
  let res
  try {
    res = await fetch(url, { credentials: 'include', signal })
  } catch (ex) {
    if (ex && ex.name === 'AbortError') throw candleError('permintaan dibatalkan', 'ABORT', 0)
    throw candleError('Tidak bisa menghubungi server candle', 'NETWORK', 0)
  }
  if (res.status === 401) {
    throw candleError('Sesi berakhir, login ulang', 'AUTH', 401)
  }
  if (!res.ok) throw await readError(res, 'Gagal memuat candle')
  const body = await res.json()
  const tfUsed = body && body.tf ? body.tf : tf
  return {
    symbol: body && body.symbol ? body.symbol : symbol,
    tf: tfUsed,
    candles: normalizeBars(body && body.candles, tfUsed),
  }
}

/**
 * Ambil candle historis untuk chart.
 *
 * @param {object} opts
 * @param {string} opts.symbol        mis. 'XAUUSD'
 * @param {string} opts.timeframe     'M1' | 'M5' | 'M15' | 'H1' | 'H4' | 'D1'
 * @param {number} [opts.limit]       1..2000 (default 500)
 * @param {AbortSignal} [opts.signal]
 * @returns {Promise<{symbol:string, tf:string, requestedTf:string, fallback:boolean,
 *   limit:number, exhausted:boolean, candles:Array}>}
 *   `exhausted` = server tidak punya candle lebih lama lagi.
 */
export async function fetchCandles({ symbol, timeframe = 'M5', limit = DEFAULT_LIMIT, signal } = {}) {
  if (!symbol) throw candleError('symbol wajib diisi', 'INVALID', 0)
  const requestedTf = isTimeframe(timeframe) ? timeframe : 'M5'
  const safeLimit = Math.min(MAX_LIMIT, Math.max(1, Math.floor(Number(limit) || DEFAULT_LIMIT)))

  try {
    const res = await requestCandles(symbol, requestedTf, safeLimit, signal)
    return {
      ...res,
      requestedTf,
      fallback: false,
      limit: safeLimit,
      exhausted: res.candles.length < safeLimit,
    }
  } catch (ex) {
    // tf tinggi belum aktif di backend -> satu percobaan ulang dengan tf
    // fallback. Kegagalan lain (auth/jaringan) langsung dilempar.
    const fb = TF_FALLBACK[requestedTf]
    if (ex.code !== 'TF_UNSUPPORTED' || !fb) throw ex
    const res = await requestCandles(symbol, fb, safeLimit, signal)
    return {
      ...res,
      requestedTf,
      fallback: true,
      limit: safeLimit,
      exhausted: res.candles.length < safeLimit,
    }
  }
}

// Gabung candle lama (server) dengan candle yang sudah ada di chart. Data
// server menang untuk periode yang sama (revisi volume), kecuali candle
// terakhir yang mungkin sudah diperbarui tick live: `live` di-overlay ulang.
export function mergeBars(prevBars, nextBars, live) {
  const map = new Map()
  for (const bar of nextBars || []) map.set(bar.time, bar)
  for (const bar of prevBars || []) if (!map.has(bar.time)) map.set(bar.time, bar)
  const out = Array.from(map.values()).sort((a, b) => a.time - b.time)
  if (live) {
    const idx = out.findIndex((b) => b.time === live.time)
    if (idx >= 0) out[idx] = { ...out[idx], ...live }
    else if (!out.length || live.time > out[out.length - 1].time) out.push({ ...live })
  }
  return out
}
