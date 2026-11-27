// Dashboard — TERMINAL Lumine Fund (workstation trading).
//
// Ergonomi mengikuti terminal institusional (satu toolbar tipis di atas chart,
// HUD OHLC melayang di dalam kanvas, chart tinggi, dock posisi/eksekusi lebar),
// tetapi identitas visual tetap Lumine (obsidian, border zinc, aksen emerald /
// crimson, angka tabular).
//
// Struktur:
//   1. Toolbar chart SATU baris: switcher simbol, harga live, satu pill status
//      feed (FEED LIVE / STALE / MARKET TUTUP), pemilih timeframe, tombol Live.
//      BID/ASK/SPREAD sengaja hanya ada di ticket Order Baru (tidak dobel),
//      badge DEMO cukup di navbar global.
//   2. Alert: satu baris ringkas yang bisa dibuka (AlertsStrip).
//   3. Grid: kiri chart (dengan HUD OHLC melayang + overlay order) dan dock
//      posisi/pending/eksekusi; kanan ringkasan akun (ringkas) + order baru.
//      Kolom kanan bisa HIDE lewat tombol di toolbar (chart jadi selebar layar).
//   4. Kill-switch: chip kecil di toolbar kanan (status + aksi darurat), bukan
//      bar besar di kolom order.
//   5. Status sistem: satu bar tipis fixed di bawah viewport (SystemMetrics),
//      termasuk penanda sesi Asia/London/New York yang aktif.
//
// Tidak ada logika order, validasi, 2FA, atau perhitungan risiko yang diubah
// di halaman ini: semua tetap milik OrderForm/ConfirmDialog/lib/api.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import CandleChart from '../components/CandleChart'
import OrderForm from '../components/OrderForm'
import SystemMetrics from '../components/SystemMetrics'
import AccountRiskSummary from '../components/RegimeCard'
import AlertsStrip from '../components/AlertsStrip'
import KillSwitchControl from '../components/terminal/KillSwitchControl'
import TradingDock from '../components/terminal/TradingDock'
import { useDesk, useTick } from '../lib/useDesk'
import { auth, desk } from '../lib/api'
import { DebugOnly } from '../lib/debug'
import {
  SYMBOLS,
  useMarketStatus,
  isMarketClosed,
  marketReasonLabel,
  fmtWib,
} from '../lib/market'
import { TIMEFRAMES, bucketStart, fetchCandles, tickMs } from '../lib/candles'
import '../styles/terminal.css'

// Label ringkas untuk selector timeframe; nilai yang dikirim ke CandleChart
// tetap kode timeframe helper candles.js (M1..D1).
const TF_LABEL = { M1: '1m', M5: '5m', M15: '15m', H1: '1h', H4: '4h', D1: '1D' }
const TF_OPTIONS = TIMEFRAMES.map((tf) => ({ tf, label: TF_LABEL[tf] || tf }))
const DEFAULT_TF = 'M5'

// Label pendek di toolbar: XAU/BTC lebih terbaca daripada kode penuh 6 huruf.
const SYM_LABEL = { XAUUSD: 'XAU', BTCUSD: 'BTC' }

// Tinggi chart: workstation = 62vh dengan lantai 540px (candle + volume butuh
// ruang vertikal), mobile 340px supaya chart + ticket masuk satu layar.
const CHART_MIN_DESKTOP = 540
const CHART_H_MOBILE_MIN = 380
const CHART_H_MOBILE_MAX = 620
const MOBILE_MQ = '(max-width: 768px)'

// Indikator stale mengikuti ambang preflight gate (`max_tick_age_s`), bukan
// angka tetap: label "live" tidak boleh lebih longgar dari aturan yang
// menolak order. Fallback 60 s hanya bila /metrics belum termuat.
const QUOTE_STALE_FALLBACK_S = 60

// Ambang tick basi dari /metrics.triggers (server = sumber yang sama dengan
// gate). Poll 30 s; null selama belum ada jawaban.
function useMaxTickAge() {
  const [maxAge, setMaxAge] = useState(null)
  useEffect(() => {
    let alive = true
    const load = () => {
      fetch('/metrics', { credentials: 'include' })
        .then((r) => (r.ok ? r.json() : null))
        .then((m) => {
          const v = m?.triggers?.max_tick_age_s
          if (alive && v != null && Number.isFinite(Number(v))) setMaxAge(Number(v))
        })
        .catch(() => {})
    }
    load()
    const timer = setInterval(load, 30000)
    return () => { alive = false; clearInterval(timer) }
  }, [])
  return maxAge
}

// Langganan tick SSE (auth.onTick) dengan filter simbol, satu tempat.
function authTick(symbol, cb) {
  return auth.onTick((t) => {
    if (!symbol || t.symbol === symbol) cb(t)
  })
}

// Usia tick terakhir simbol aktif (detik), diperbarui tiap detik.
// Sumber: auth.onTick (SSE) — bukan mock; 0 tick = null.
function useTickAge(symbol) {
  const [age, setAge] = useState(null)
  useEffect(() => {
    let last = null
    const off = authTick(symbol, () => { last = Date.now() })
    const timer = setInterval(() => {
      setAge(last == null ? null : (Date.now() - last) / 1000)
    }, 1000)
    return () => { off(); clearInterval(timer) }
  }, [symbol])
  return age
}

// Tinggi chart mengikuti viewport aktif (bukan state layout): satu breakpoint,
// sama dengan breakpoint mobile di terminal.css.
function useChartHeight() {
  const [h, setH] = useState(() => calcChartHeight())
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_MQ)
    const apply = () => setH(calcChartHeight())
    apply()
    mq.addEventListener('change', apply)
    window.addEventListener('resize', apply)
    return () => {
      mq.removeEventListener('change', apply)
      window.removeEventListener('resize', apply)
    }
  }, [])
  return h
}

function calcChartHeight() {
  if (typeof window === 'undefined') return CHART_MIN_DESKTOP
  // Mobile/tablet: chart mengisi layar seperti MT4/TradingView, menyisakan
  // ruang toolbar + bar status + bottom nav. Di layar pendek tetap >= 380px.
  if (window.matchMedia(MOBILE_MQ).matches) {
    return Math.min(CHART_H_MOBILE_MAX, Math.max(CHART_H_MOBILE_MIN, Math.round(window.innerHeight - 262)))
  }
  return Math.max(CHART_MIN_DESKTOP, Math.round(window.innerHeight * 0.62))
}

// Preferensi kolom kanan (ticket) dibuka/ditutup. Disimpan lokal supaya
// trader yang memilih chart penuh tidak harus menutupnya tiap muat halaman.
const SIDE_KEY = 'lumine.term.side.open'

function readSidePref() {
  try {
    const v = localStorage.getItem(SIDE_KEY)
    return v == null ? true : v === '1'
  } catch {
    return true
  }
}

function writeSidePref(open) {
  try { localStorage.setItem(SIDE_KEY, open ? '1' : '0') } catch {
    // localStorage diblokir: preferensi berlaku untuk sesi ini saja
  }
}

// Waktu bar candle (epoch detik, UTC) -> "MM-DD HH:MM UTC".
function fmtBarTime(sec) {
  if (!sec) return '·'
  const d = new Date(sec * 1000)
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC`
}

// Satu-satunya pill status feed. Menggabungkan status pasar dan kesegaran
// tick supaya tidak ada dua badge yang saling bertentangan di layar:
//   pasar buka + tick segar  -> emerald • FEED LIVE
//   pasar buka + tick basi   -> amber  • STALE Ns
//   pasar tutup              -> amber  • MARKET TUTUP (+ alasan di title)
//   belum ada status         -> muted  · ·
function FeedPill({ market, stale, ageS }) {
  if (market?.status === 'CLOSED') {
    const reason = marketReasonLabel(market.reason)
    const open = fmtWib(market.nextOpen)
    const title = `Pasar tutup${reason ? ` (${reason})` : ''}${open ? ` · buka ${open}` : ''} · order baru nonaktif`
    return (
      <span className="feed-pill is-closed" title={title}>
        <i aria-hidden="true" />
        MARKET TUTUP
      </span>
    )
  }
  if (market?.status === 'OPEN' && stale) {
    return (
      <span className="feed-pill is-stale" title={`Tick terakhir ${Math.round(ageS)} detik lalu — di atas ambang gate`}>
        <i aria-hidden="true" />
        STALE {Math.round(ageS)}s
      </span>
    )
  }
  if (market?.status === 'OPEN') {
    return (
      <span className="feed-pill is-live" title="Harga tick segar · order diizinkan selama gate lolos">
        <i aria-hidden="true" />
        FEED LIVE
      </span>
    )
  }
  return (
    <span className="feed-pill is-unknown" title="Status pasar belum tersedia dari server">
      <i aria-hidden="true" />
      · ·
    </span>
  )
}

export default function Dashboard() {
  const state = useDesk()
  const symbol = state?.symbol
  const quote = symbol ? state?.quotes?.[symbol] : null
  const market = useMarketStatus(symbol)
  const marketClosed = isMarketClosed(market)
  const tickAge = useTickAge(symbol)
  const maxTickAge = useMaxTickAge()
  const staleAfter = maxTickAge ?? QUOTE_STALE_FALLBACK_S
  const quoteStale = tickAge != null && tickAge > staleAfter && !marketClosed
  const chartH = useChartHeight()

  // Timeframe chart (state lokal, default M5). Nilai = kode candles.js.
  const [tf, setTf] = useState(DEFAULT_TF)
  // Bar dari crosshair CandleChart; null = mouse di luar candle.
  const [cursor, setCursor] = useState(null)
  // Candle terakhir dari endpoint yang sama dengan chart: fallback HUD saat
  // crosshair null (bukan angka karangan).
  const [lastBar, setLastBar] = useState(null)
  // TF efektif dari server (bisa fallback M15): dipakai untuk membucket tick
  // supaya HUD tidak memakai satuan periode yang salah.
  const [barTf, setBarTf] = useState(tf)
  // Naikkan epoch = remount chart = zoom + auto-scroll kembali ke kanan.
  const [chartEpoch, setChartEpoch] = useState(0)
  // Kolom kanan (ringkasan + ticket) bisa disembunyikan: chart memakai lebar
  // penuh seperti panel kanan TradingView yang di-collapse.
  const [sideOpen, setSideOpen] = useState(readSidePref)

  function toggleSide() {
    setSideOpen((v) => {
      writeSidePref(!v)
      return !v
    })
  }

  const digits = (symbol && SYMBOLS[symbol]?.digits) || 2
  const fmtPrice = (v) => (v == null || Number.isNaN(Number(v)) ? '·' : Number(v).toFixed(digits))

  useEffect(() => {
    if (!symbol) return undefined
    let alive = true
    const ctrl = new AbortController()
    fetchCandles({ symbol, timeframe: tf, limit: 2, signal: ctrl.signal })
      .then((res) => {
        if (!alive) return
        setBarTf(res.tf)
        setLastBar(res.candles.length ? res.candles[res.candles.length - 1] : null)
      })
      .catch(() => { if (alive) setLastBar(null) })
    return () => { alive = false; ctrl.abort() }
  }, [symbol, tf, chartEpoch])

  // Candle terakhir untuk HUD: bar server + tick terakhir, dengan aturan
  // bucket yang sama dengan chart. Tick TIDAK pernah membuat bar baru di sini.
  const tick = useTick()
  const liveBar = useMemo(() => {
    if (!lastBar) return null
    if (!tick || tick.symbol !== symbol || marketClosed) return lastBar
    const price = Number(tick.price)
    const ms = tickMs(tick.ts)
    if (!Number.isFinite(price) || ms == null) return lastBar
    const time = Math.floor(bucketStart(ms, barTf) / 1000)
    if (time !== lastBar.time) return lastBar
    return { ...lastBar, high: Math.max(lastBar.high, price), low: Math.min(lastBar.low, price), close: price }
  }, [lastBar, tick, symbol, barTf, marketClosed])

  const handleCrosshair = useCallback((bar) => setCursor(bar), [])

  function changeTf(next) {
    setCursor(null)
    setTf(next)
  }

  function resetChart() {
    setCursor(null)
    setChartEpoch((n) => n + 1)
  }

  // Tinggi maksimum kolom kanan dihitung dari offset grid sebenarnya, bukan
  // 100vh - gap: grid baru mulai 96-230px dari atas (toolbar + alert),
  // sehingga batas lama membuat kartu Ringkasan tertutup bar status fixed di
  // layar pendek (mis. 1366x768 saat form order dibuka). Dihitung tiap render
  // supaya strip alert yang muncul/hilang ikut terhitung.
  const rootRef = useRef(null)
  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    const grid = root.querySelector('.term-grid')
    if (!grid) return
    const bar = document.querySelector('.term-sysbar')
    const barH = bar ? bar.offsetHeight : 40
    const gridTop = grid.getBoundingClientRect().top + window.scrollY
    const avail = Math.max(240, Math.round(window.innerHeight - gridTop - barH - 16))
    root.style.setProperty('--term-side-max', `${avail}px`)
  })

  const hud = cursor ?? liveBar

  return (
    <div className="dashboard term-root" ref={rootRef}>
      {/* ── Toolbar chart: satu baris, tanpa duplikasi badge/quote ── */}
      <section className="card term-toolbar" aria-label="Toolbar chart">
        <div className="ttb-left">
          <div className="term-sym" role="group" aria-label="Pilih simbol">
            {Object.keys(SYMBOLS).map((s) => (
              <button
                key={s}
                type="button"
                className={`term-sym-btn ${s === symbol ? 'is-active' : ''}`.trim()}
                aria-pressed={s === symbol}
                title={s}
                onClick={() => desk.setSymbol(s)}
              >
                {SYM_LABEL[s] || s}
              </button>
            ))}
          </div>
          <div className="ttb-quote">
            <span className={`ttb-price tnum ${quoteStale ? 'is-stale' : ''}`.trim()}>
              {quote?.price?.toFixed(2) ?? '·····'}
            </span>
            <span className="ttb-ba tnum" title="Bid · Ask · Spread (poin)">
              <span>B {quote?.bid?.toFixed(2) ?? '·'}</span>
              <span>A {quote?.ask?.toFixed(2) ?? '·'}</span>
              <span className="ttb-spread">S {quote?.spread != null ? quote.spread.toFixed(2) : '·'}</span>
            </span>
          </div>
          <FeedPill market={market} stale={quoteStale} ageS={tickAge} />
        </div>

        <div className="ttb-right">
          <KillSwitchControl compact />
          <div className="term-tf" role="group" aria-label="Timeframe chart">
            {TF_OPTIONS.map((opt) => (
              <button
                key={opt.tf}
                type="button"
                className={`term-tf-btn ${tf === opt.tf ? 'is-active' : ''}`.trim()}
                aria-pressed={tf === opt.tf}
                title={`Timeframe ${opt.tf}`}
                onClick={() => changeTf(opt.tf)}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="term-reset"
            onClick={resetChart}
            title="Kembalikan zoom dan auto-scroll ke candle terbaru"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 12a9 9 0 1 0 3.2-6.9" />
              <path d="M3 4v5h5" />
            </svg>
            Live
          </button>
          <button
            type="button"
            className={`term-side-toggle ${sideOpen ? 'is-on' : ''}`.trim()}
            aria-pressed={sideOpen}
            aria-controls="term-side"
            onClick={toggleSide}
            title={sideOpen ? 'Sembunyikan panel kanan (chart lebih lebar)' : 'Tampilkan panel kanan'}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <path d="M15 4v16" />
            </svg>
          </button>
        </div>
      </section>

      {/* Alert: satu baris ringkas, buka saat perlu, hilang saat kosong */}
      <AlertsStrip />

      <div className={`term-grid ${sideOpen ? '' : 'is-side-hidden'}`.trim()}>
        {/* ── Kolom kiri: chart (HUD melayang) + dock posisi & eksekusi ── */}
        <div className="term-col-main">
          <section className="term-chart-card" aria-label={`Grafik harga ${symbol ?? ''}`}>
            {/* HUD melayang: pointer-events-none, tidak memakan tinggi chart.
                Isi: simbol · TF, O/H/L/C (crosshair atau bar terakhir), waktu. */}
            <div className="chart-hud" aria-hidden="true">
              <span className="chart-hud-sym">
                {symbol ?? '·'}
                <span className="chart-hud-tf"> · {TF_LABEL[barTf] || barTf}</span>
              </span>
              <span className="chart-hud-ohlc">
                {[['O', hud?.open], ['H', hud?.high], ['L', hud?.low], ['C', hud?.close]].map(([k, v]) => (
                  <span className="chart-hud-cell" key={k}>
                    <span className="chart-hud-key">{k}</span>
                    <span className="tnum">{fmtPrice(v)}</span>
                  </span>
                ))}
              </span>
              <span className="chart-hud-time tnum">
                {cursor ? 'CURSOR' : 'LAST'} {fmtBarTime(hud?.time)}
              </span>
            </div>
            <CandleChart
              key={chartEpoch}
              symbol={symbol}
              timeframe={tf}
              height={chartH}
              className="term-candle"
              marketStatus={market}
              onCrosshair={handleCrosshair}
              positions={state?.positions || []}
              orders={state?.orders || []}
            />
          </section>

          <TradingDock symbol={symbol} />
        </div>

        {/* ── Kolom kanan: ringkasan akun (ringkas) + order baru ── */}
        {sideOpen && (
          <aside className="term-col-side" id="term-side" aria-label="Ringkasan akun dan tiket order">
            <AccountRiskSummary symbol={symbol} compact />
            <OrderForm />
          </aside>
        )}
      </div>

      {/* Status sistem: satu bar tipis fixed di bawah viewport, klik = detail */}
      <SystemMetrics />

      <DebugOnly label="debug">
        <p className="term-foot-note">
          Candle {TF_LABEL[tf] || tf} · waktu bar UTC · harga live dari feed SSE · chart membaca /candles
          tiap 1 detik saat tab terlihat (tick hanya memperbarui bar terakhir yang bucket-nya sama).
          Garis entry/SL/TP dan marker eksekusi berasal dari /positions dan /orders.
        </p>
      </DebugOnly>
    </div>
  )
}
