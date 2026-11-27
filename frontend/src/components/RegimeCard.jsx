// Kartu "Ringkasan" Terminal (kolom kanan) — versi tenang: equity besar,
// delta harian, dan TEPAT empat angka inti (winrate, profit factor, drawdown,
// posisi terbuka) dalam satu deret yang mudah dipindai. Tanpa kotak KPI kecil
// berantakan; angka memakai tabular-nums; satu aksen warna (emerald) hanya
// untuk status pasar dan delta positif.
//
// Sumber angka (tidak ada yang dikarang):
//   - equity:            GET /risk/portfolio (fallback /metrics.risk)
//   - delta harian:      GET /metrics.risk.daily_pnl + daily_start_balance
//                        (fallback state.killSwitch.metrics dari /kill-switch)
//   - drawdown:          GET /metrics.risk.daily_drawdown_pct + triggers
//   - posisi terbuka:    GET /risk/portfolio.open_positions (fallback /metrics)
//   - winrate/PF:        dihitung dari posisi CLOSED yang sudah dimuat desk
//                        (state.positions). Tidak ada trade tertutup -> '—'.
//   - regime + keyakinan: GET /regime/current
import { useEffect, useState } from 'react'
import { fetchRegimeCurrent, fetchRiskPortfolio } from '../lib/api'
import { useDesk } from '../lib/useDesk'
import { DebugOnly } from '../lib/debug'
import {
  isMarketClosed,
  marketReasonLabel,
  fmtWib,
  useMarketStatus,
} from '../lib/market'

const POLL_MS = 30000
const REGIME_STALE_S = 600 // 10 menit

function fmtSigned(v, digits = 2) {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  const n = Number(v)
  return `${n >= 0 ? '+' : '-'}$${Math.abs(n).toLocaleString('id-ID', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`
}

function fmtPct(v, digits = 1) {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  return `${Number(v).toFixed(digits)}%`
}

// Winrate & profit factor dari daftar posisi tertutup (profit nyata server).
// Tanpa trade tertutup: null (UI menampilkan '—', bukan nol karangan).
function closedStats(positions) {
  const closed = (positions || []).filter(
    (p) => (p.status ?? '').toUpperCase() === 'CLOSED' && p.pnl != null,
  )
  if (!closed.length) return null
  let wins = 0
  let grossWin = 0
  let grossLoss = 0
  for (const p of closed) {
    const n = Number(p.pnl)
    if (Number.isNaN(n)) continue
    if (n > 0) { wins += 1; grossWin += n }
    else if (n < 0) { grossLoss += Math.abs(n) }
  }
  const lossBase = grossLoss > 0 ? grossLoss : 0
  return {
    n: closed.length,
    winrate: closed.length ? (wins / closed.length) * 100 : null,
    profitFactor: lossBase > 0 ? grossWin / lossBase : null,
  }
}

export default function AccountRiskSummary({ symbol = 'XAUUSD', compact = false }) {
  const state = useDesk()
  const market = useMarketStatus(symbol)
  const [snap, setSnap] = useState(null) // GET /risk/portfolio
  const [metrics, setMetrics] = useState(null) // GET /metrics
  const [regime, setRegime] = useState(null) // GET /regime/current
  const [err, setErr] = useState(null)
  const [fetchedAt, setFetchedAt] = useState(null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    let alive = true
    async function poll() {
      const [portfolio, regimeRes, metricsRes] = await Promise.allSettled([
        fetchRiskPortfolio(),
        fetchRegimeCurrent(symbol),
        fetch('/metrics', { credentials: 'include' }).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))),
      ])
      if (!alive) return
      if (portfolio.status === 'fulfilled') setSnap(portfolio.value)
      if (regimeRes.status === 'fulfilled') setRegime(regimeRes.value)
      if (metricsRes.status === 'fulfilled') setMetrics(metricsRes.value)
      const firstError = [portfolio, regimeRes, metricsRes].find((r) => r.status === 'rejected')
      setErr(firstError ? firstError.reason?.message || 'gagal memuat' : null)
      if (portfolio.status === 'fulfilled' || regimeRes.status === 'fulfilled') setFetchedAt(Date.now())
    }
    poll()
    const t = setInterval(poll, POLL_MS)
    const tick = setInterval(() => setNow(Date.now()), 1000)
    return () => { alive = false; clearInterval(t); clearInterval(tick) }
  }, [symbol])

  // Status tutup boleh datang dari /market/status atau /regime/current
  // (field opsional); keduanya sah, yang penting satu kesimpulan.
  const closed =
    isMarketClosed(market) ||
    regime?.market_closed === true ||
    String(regime?.market_status || '').toUpperCase() === 'CLOSED'

  // Umur data berjalan client-side: age_s saat fetch + detik sejak fetch.
  const ageS = regime?.age_s != null && fetchedAt != null
    ? regime.age_s + (now - fetchedAt) / 1000
    : null
  const stale = !closed && (err != null || ageS == null || ageS > REGIME_STALE_S || !!regime?.stale)

  const risk = metrics?.risk
  const equity = snap?.equity ?? risk?.equity ?? state?.equity
  const ksm = state?.killSwitch?.metrics
  const dailyPnl = risk?.daily_pnl ?? ksm?.daily_pnl
  const dailyStart = risk?.daily_start_balance ?? ksm?.daily_start_balance
  const dailyPct = dailyPnl != null && dailyStart ? (dailyPnl / Math.abs(dailyStart)) * 100 : null
  const dd = risk?.daily_drawdown_pct
  const ddMax = metrics?.triggers?.daily_drawdown_pct
  const openPositions =
    snap?.open_positions ??
    risk?.open_positions ??
    (state?.positions || []).filter((p) => (p.status ?? 'OPEN') === 'OPEN').length
  const stats = closedStats(state?.positions)

  const conf = regime?.confidence
  const confPct = conf != null && !stale && !closed ? Math.round(conf * 100) : null
  const regimeLabel = closed ? 'Market tutup' : (regime?.label ?? null)
  const closeReason = marketReasonLabel(market?.reason)
  const lastTickText = closed
    ? (fmtWib(market?.lastTickTs) || fmtWib(regime?.candle_ts) || null)
    : null
  const dailyPctText = dailyPct != null
    ? `${dailyPct >= 0 ? '+' : ''}${dailyPct.toFixed(2)}%`
    : null

  return (
    <section className={`card term-sum ${compact ? 'is-compact' : ''} ${stale ? 'is-stale' : ''}`.trim()} aria-label="Ringkasan akun dan risiko">
      <div className="term-sum-head">
        <span className="term-sum-title">Ringkasan</span>
        {closed
          ? <span className="chip chip-gold" title={`Pasar tutup${closeReason ? ` (${closeReason})` : ''} · regime dihitung ulang setelah tick pertama sesi berikutnya`}>MARKET TUTUP</span>
          : stale
            ? <span className="chip chip-gold" title={regime?.degrade_reason || regime?.reason || err || 'Data terakhir sudah lama'}>DATA TERTUNDA</span>
            : <span className="chip chip-up" title="Semua sumber data ringkasan terbaru">LIVE</span>}
      </div>

      {/* Hero: equity besar + delta harian; satu-satunya angka yang besar. */}
      <div className="term-sum-hero">
        <div className="term-sum-equity tnum" title="Ekuitas akun saat ini">
          <span className="term-sum-cur">$</span>{equity != null ? Math.round(equity).toLocaleString('id-ID') : '—'}
        </div>
        <div className={`term-sum-delta ${(dailyPnl ?? 0) >= 0 ? 'is-up' : 'is-down'}`.trim()}>
          <span className="tnum">{dailyPnl != null ? fmtSigned(dailyPnl) : '—'}</span>
          <span className="term-sum-delta-sub">
            hari ini{dailyPctText ? ` · ${dailyPctText}` : ''}
          </span>
        </div>
      </div>

      {/* Empat angka inti, satu deret, tanpa kotak-kotak kecil. */}
      <dl className="term-sum-stats">
        <div className="term-sum-stat">
          <dt>Winrate</dt>
          <dd className="tnum" title={stats ? `Dari ${stats.n} posisi tertutup` : 'Belum ada posisi tertutup'}>
            {stats?.winrate != null ? `${stats.winrate.toFixed(0)}%` : '—'}
          </dd>
        </div>
        <div className="term-sum-stat">
          <dt title="Profit factor: laba kotor dibagi rugi kotor dari posisi tertutup">PF</dt>
          <dd className="tnum" title={stats ? `Dari ${stats.n} posisi tertutup` : 'Belum ada posisi tertutup'}>
            {stats?.profitFactor != null ? stats.profitFactor.toFixed(2) : '—'}
          </dd>
        </div>
        <div className="term-sum-stat">
          <dt>Drawdown</dt>
          <dd className="tnum" title="Drawdown hari ini terhadap batas yang menghentikan trading">
            {fmtPct(dd, 2)}
            {ddMax != null && <span className="term-sum-sub"> / {fmtPct(ddMax, 1)}</span>}
          </dd>
        </div>
        <div className="term-sum-stat">
          <dt>Posisi</dt>
          <dd className="tnum" title="Jumlah posisi terbuka sekarang">
            {openPositions ?? '—'}
          </dd>
        </div>
      </dl>

      {/* Satu baris konteks: regime, keyakinan, penanda pasar tutup. */}
      <p className="term-sum-foot">
        {regimeLabel ? `Regime ${regimeLabel}` : 'Regime —'}
        {confPct != null ? ` · keyakinan ${confPct}%` : ''}
        {closed && lastTickText ? ` · tick terakhir ${lastTickText}` : ''}
      </p>

      <DebugOnly label="debug">
        <p className="term-foot">
          Sumber: /risk/portfolio + /metrics + /regime/current + /positions · poll {POLL_MS / 1000}s
        </p>
      </DebugOnly>
    </section>
  )
}
