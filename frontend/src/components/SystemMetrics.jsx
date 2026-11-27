// Status sistem Terminal: SATU bar tipis full-width FIXED di bawah viewport.
// Isi bar dibatasi 4 butir + satu tombol Detail supaya tidak jadi dinding teks:
//   DB · EA · Tick · Gap
// Klik bar/Detail -> panel: popover di desktop (menempel di atas bar),
// bottom sheet di mobile. Panel memuat metrik lengkap (tidak ada data dibuang).
// Bar tidak menutupi konten: halaman menyisakan padding-bottom setinggi bar
// (lihat terminal.css), dan di mobile bar duduk di atas bottom nav + safe-area.
// Komponen read-only: tidak ada aksi; kontrol kill-switch ada di header.
// Bar juga memuat penanda sesi likuiditas (Asia/London/New York) versi kecil:
// sesi adalah konteks harga, bukan data sistem, jadi cukup di footer.
import { useEffect, useRef, useState } from 'react'
import { useDesk } from '../lib/useDesk'
import { sessionsFor } from '../lib/market'

const SESSION_ORDER = ['asia', 'london', 'ny']
const SESSION_LABEL = { asia: 'Asia', london: 'London', ny: 'New York' }

const POLL_MS = 30000

function fmtAge(s) {
  if (s == null) return '·'
  if (s < 90) return `${Math.round(s)}s`
  if (s < 5400) return `${Math.round(s / 60)}m`
  return `${Math.round(s / 3600)}j`
}

function fmtBytes(b) {
  if (b == null) return '·'
  if (b > 1e9) return `${(b / 1e9).toFixed(1)} GB`
  return `${(b / 1e6).toFixed(0)} MB`
}

function fmtMs(v) {
  return v == null ? '·' : `${Math.round(v)}ms`
}

// Ambang warna untuk persentase: aman / waspada / kritis.
function pctTone(v, warn, down) {
  if (v == null) return undefined
  if (v >= down) return 'down'
  if (v >= warn) return 'warn'
  return 'ok'
}

function Chip({ ok, warn, children, title }) {
  const cls = ok ? 'is-ok' : warn ? 'is-warn' : 'is-down'
  return <span className={`sm-chip ${cls}`} title={title}>{children}</span>
}

// Baris metrik di panel detail: label kiri, nilai kanan, angka tabular.
// tone: undefined | 'ok' | 'warn' | 'down' — hanya untuk angka yang punya
// ambang jelas (latency, failure rate, DSB); sisanya netral.
function Row({ label, value, title, tone, children }) {
  return (
    <div className="sm-row" title={title}>
      <span className="sm-label">{label}</span>
      <span className={`sm-value num ${tone ? `is-${tone}` : ''}`.trim()}>
        {children ?? value}
      </span>
    </div>
  )
}

// Satu bagian panel: judul kecil + chip status opsional, isi baris metrik.
function Sect({ title, chip, children }) {
  return (
    <section className="sm-section">
      <header className="sm-section-head">
        <h3>{title}</h3>
        {chip}
      </header>
      <div className="sm-rows">{children}</div>
    </section>
  )
}

// Satu butir status bar: dot warna + teks pendek.
function Item({ tone, children, title }) {
  return (
    <span className={`term-sysitem is-${tone}`} title={title || undefined}>
      <i className="term-sysdot" aria-hidden="true" />
      {children}
    </span>
  )
}

export default function SystemMetrics() {
  const state = useDesk()
  const symbol = state?.symbol
  const [m, setM] = useState(null)
  const [err, setErr] = useState(null)
  const [lastOk, setLastOk] = useState(null)
  const [now, setNow] = useState(() => Date.now())
  const [open, setOpen] = useState(false)
  const panelRef = useRef(null)

  useEffect(() => {
    let alive = true
    async function poll() {
      try {
        const res = await fetch('/metrics', { credentials: 'include' })
        if (res.status === 401) return // belum login: bar diam
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const body = await res.json()
        if (alive) { setM(body); setErr(null); setLastOk(Date.now()) }
      } catch (ex) {
        if (alive) setErr(ex.message)
      }
    }
    poll()
    const t = setInterval(poll, POLL_MS)
    const tk = setInterval(() => setNow(Date.now()), 1000)
    return () => { alive = false; clearInterval(t); clearInterval(tk) }
  }, [])

  // Panel: Escape menutup, klik di luar panel menutup (mobile punya backdrop
  // sendiri; listener ini menjaga desktop tetap terasa seperti popover).
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    const onDown = (e) => {
      const el = panelRef.current
      if (!el || el.contains(e.target)) return
      if (e.target.closest && e.target.closest('.term-sysbar-bar')) return
      setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onDown)
    }
  }, [open])

  // 2x poll tanpa data baru = stale: umur berjalan tiap detik, bukan angka beku.
  const metricsAge = lastOk ? (now - lastOk) / 1000 : null
  const metricsStale = metricsAge != null && metricsAge > (2 * POLL_MS) / 1000

  const db = m?.db
  const ea = m?.ea
  const host = m?.host
  const feed = m?.feed
  const spread = m?.spread
  const orders = m?.orders
  const lat = m?.latency
  const risk = m?.risk
  const backup = m?.backup
  const xau = spread?.XAUUSD

  // ── ringkasan empat butir ───────────────────────────────────────────────
  const dbOk = db?.available === true
  const eaAge = ea?.last_seen_age_s
  const eaOk = eaAge != null && eaAge <= (ea?.offline_threshold_s || 60)
  const tickAge = feed?.liquidity_age_s
  const tickTone = tickAge == null ? 'down' : tickAge <= 30 ? 'ok' : tickAge <= 120 ? 'warn' : 'down'
  const gaps = feed?.gaps_1h || {}
  const gapCount = Object.values(gaps).reduce((n, g) => n + (g?.count || 0), 0)
  // Sesi: dari tick server (quotes[symbol].sessions); bila belum ada tick,
  // hitung lokal dari jam UTC dengan aturan yang sama (lib/market).
  const liveSessions = (symbol && state?.quotes?.[symbol]?.sessions)
    || sessionsFor(symbol || 'XAUUSD')
  const failRate = orders?.failure_rate_24h
  const failPct = failRate != null ? Math.round(failRate * 100) : null
  const runners = Object.entries(m?.strategies?.runners || {})
  const activeStrategies = runners.filter(([k, v]) => !k.startsWith('shadow_') && v?.paper_state_age_s != null && v.paper_state_age_s <= 300).length

  return (
    <div className={`term-sysbar ${open ? 'is-open' : ''} ${metricsStale ? 'is-stale' : ''}`.trim()}>
      {open && <div className="term-sys-backdrop" onClick={() => setOpen(false)} aria-hidden="true" />}

      {open && (
        <div
          ref={panelRef}
          className="term-sysbar-panel"
          id="term-sys-detail"
          role="dialog"
          aria-label="Detail status sistem"
        >
          <div className="term-sysbar-panel-head">
            <h2 className="card-title">Detail sistem</h2>
            <span className={`chip ${err ? 'chip-down' : metricsStale ? 'chip-gold' : 'chip-up'}`} title={err || `terakhir: ${m?.collected_at || '·'}`}>
              {err
                ? (lastOk != null && metricsAge != null
                    ? `OFFLINE · STALE (${Math.round(metricsAge)}s)`
                    : 'OFFLINE')
                : metricsStale
                  ? `STALE (${Math.round(metricsAge)}s)`
                  : 'LIVE'}
            </span>
            <button
              type="button"
              className="term-sys-close"
              onClick={() => setOpen(false)}
              aria-label="Tutup detail sistem"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
                <path d="m6 6 12 12M18 6 6 18" />
              </svg>
            </button>
          </div>
          {!m ? (
            <p className="sm-empty">{err ? `Gagal memuat status sistem: ${err}` : 'Memuat status sistem…'}</p>
          ) : (
            <div className="sm-grid">
              <Sect
                title="API & DB"
                chip={<Chip ok={dbOk} warn={!dbOk && db != null}>{dbOk ? 'OK' : db ? 'GANGGUAN' : 'BELUM DATA'}</Chip>}
              >
                <Row label="Roundtrip DB" value={fmtMs(db?.latency_ms)} tone={db?.latency_ms != null ? (db.latency_ms <= 40 ? 'ok' : db.latency_ms <= 120 ? 'warn' : 'down') : undefined} title="Roundtrip query Postgres" />
                <Row label="Koneksi" value={`${db?.connections ?? '·'} / ${db?.max_connections ?? '·'}`} title="Koneksi aktif / maksimum pool" />
                <Row label="Ukuran DB" value={fmtBytes(db?.size_bytes)} />
                <Row label="CPU" value={host?.cpu_percent != null ? `${host.cpu_percent}%` : '·'} tone={pctTone(host?.cpu_percent, 75, 90)} />
                <Row label="RAM" value={host?.mem_used_pct != null ? `${host.mem_used_pct}%` : '·'} tone={pctTone(host?.mem_used_pct, 80, 92)} />
                <Row label="Swap" value={host?.swap_used_pct != null ? `${host.swap_used_pct}%` : '·'} tone={pctTone(host?.swap_used_pct, 25, 60)} />
                <Row label="Disk /" value={host?.disk_root_pct != null ? `${host.disk_root_pct}%` : '·'} tone={pctTone(host?.disk_root_pct, 80, 90)} />
              </Sect>

              <Sect
                title="EA & Feed"
                chip={<Chip ok={eaOk} warn={eaAge != null && !eaOk} title="Usia heartbeat EA">{eaAge != null ? fmtAge(eaAge) : 'belum terlihat'}</Chip>}
              >
                <Row label="Heartbeat EA" value={eaAge != null ? `${fmtAge(eaAge)} lalu` : 'belum terlihat'} tone={eaOk ? 'ok' : eaAge != null ? 'warn' : undefined} title="Usia heartbeat terakhir dari EA" />
                <Row label="Candle M5 XAU" value={fmtAge(feed?.candles?.['XAUUSD:M5']?.age_s)} title="Usia bar M5 terakhir" />
                <Row label="Tick terakhir" value={tickAge != null ? `${fmtAge(tickAge)} lalu` : '·'} tone={tickTone} title="Usia sampel tick terakhir" />
                <Row
                  label="Gap 1 jam"
                  value={Object.entries(gaps).map(([s, g]) => `${s} ${g.count}`).join(' · ') || '0'}
                  tone={gapCount === 0 ? 'ok' : 'warn'}
                  title="Jumlah gap data per simbol dalam 1 jam terakhir"
                />
                <Row label="Spread XAU" value={xau ? `${xau.p50_1h?.toFixed(2)} / ${xau.p95_1h?.toFixed(2)}` : '·'} title="p50 / p95 spread 1 jam (USD)" />
              </Sect>

              <Sect
                title="Order 24 jam"
                chip={<Chip ok={failPct != null && failPct < 5} warn={failPct != null && failPct < 20 && failPct >= 5}>{failPct != null ? `${failPct}% gagal` : 'belum data'}</Chip>}
              >
                <Row label="Terminal" value={orders?.terminal_24h ?? '·'} />
                <Row label="Gagal" value={orders?.failed_24h ?? '·'} tone={orders?.failed_24h > 0 ? 'warn' : undefined} />
                <Row label="Stuck > 60s" value={orders?.stuck_sent_60s ?? '·'} tone={orders?.stuck_sent_60s > 0 ? 'warn' : undefined} />
                <Row label="Latensi p50/p95/p99" value={
                  lat?.t0_t2_ms?.p95 != null
                    ? `${fmtMs(lat.t0_t2_ms.p50)} / ${fmtMs(lat.t0_t2_ms.p95)} / ${fmtMs(lat.t0_t2_ms.p99)}`
                    : lat?.orders_fallback?.t0_t1_s?.p50 != null
                      ? `${fmtMs(lat.orders_fallback.t0_t1_s.p50 * 1000)} / ${fmtMs(lat.orders_fallback.t0_t1_s.p95 * 1000)} / ${fmtMs(lat.orders_fallback.t0_t1_s.p99 * 1000)}`
                      : '·'
                } title="Latensi internal t0..t2 (target p95 300ms)" />
                <Row label="Sampai broker" value={
                  lat?.t0_t4_ms?.p95 != null
                    ? `${fmtMs(lat.t0_t4_ms.p50)} / ${fmtMs(lat.t0_t4_ms.p95)} / ${fmtMs(lat.t0_t4_ms.p99)}`
                    : lat?.orders_fallback?.t0_t4_s?.p50 != null
                      ? `${fmtMs(lat.orders_fallback.t0_t4_s.p50 * 1000)} / ${fmtMs(lat.orders_fallback.t0_t4_s.p95 * 1000)} / ${fmtMs(lat.orders_fallback.t0_t4_s.p99 * 1000)}`
                      : '·'
                } title="Waktu dari perintah sampai hasil broker (p50/p95/p99)" />
              </Sect>

              <Sect
                title="Risiko & Ops"
                chip={<Chip ok={!risk?.kill_switch?.active} warn={risk?.kill_switch?.active}>{risk?.kill_switch?.active ? `HALT · ${risk.kill_switch.mode}` : 'AMAN'}</Chip>}
              >
                <Row label="Drawdown harian" value={risk?.daily_drawdown_pct != null ? `${risk.daily_drawdown_pct}%` : '·'} tone={pctTone(risk?.daily_drawdown_pct, 2, 4)} />
                <Row label="Drawdown total" value={risk?.total_drawdown_pct != null ? `${risk.total_drawdown_pct}%` : '·'} tone={pctTone(risk?.total_drawdown_pct, 5, 10)} />
                <Row label="Eksposur" value={risk?.exposure_usd != null ? `$${Math.round(risk.exposure_usd).toLocaleString('id-ID')}` : '·'} title="Notional posisi terbuka" />
                <Row label="Posisi terbuka" value={risk?.open_positions ?? '·'} />
                <Row label="Strategi aktif" value={activeStrategies} title="Strategi dengan state paper segar (≤5 menit)" />
                <Row label="Backup harian" value={backup?.age_s != null ? `${fmtAge(backup.age_s)} lalu` : 'belum ada'} title={backup?.last ? `${backup.last.ts} · offsite=${backup.last.offsite}` : 'Tidak ada backup harian sukses'} />
              </Sect>
            </div>
          )}
        </div>
      )}

      <button
        type="button"
        className="term-sysbar-bar"
        aria-expanded={open}
        aria-controls="term-sys-detail"
        onClick={() => setOpen((v) => !v)}
        title="Status sistem: klik untuk detail"
      >
        <span className="term-sysbar-items">
          {!m ? (
            <Item tone={err ? 'down' : 'warn'}>{err ? 'Status sistem tidak tersedia' : 'Memuat status…'}</Item>
          ) : (
            <>
              <Item tone={dbOk ? 'ok' : 'down'} title={dbOk ? `Query DB ${fmtMs(db?.latency_ms)}` : 'DB tidak tersedia'}>
                DB {dbOk ? 'OK' : 'Gangguan'}
              </Item>
              <Item tone={eaOk ? 'ok' : 'warn'} title={eaAge != null ? `Heartbeat EA ${fmtAge(eaAge)} lalu` : 'EA belum terlihat'}>
                EA {eaOk ? 'Online' : 'Offline'}
              </Item>
              <Item tone={tickTone} title="Usia tick terakhir">
                Tick {fmtAge(tickAge)}
              </Item>
              <Item tone={gapCount === 0 ? 'ok' : 'warn'} title="Gap data 1 jam terakhir">
                {gapCount} gap
              </Item>
            </>
          )}
          {/* Sesi selalu tampil (tidak bergantung /metrics): konteks jam pasar. */}
          <span className="term-sysseps" title="Sesi likuiditas yang sedang berjalan (UTC)">
            {SESSION_ORDER.map((k) => {
              const on = liveSessions.includes(k)
              return (
                <span key={k} className={`term-syssep ${on ? 'is-on' : ''}`.trim()}>
                  <i aria-hidden="true" />
                  {SESSION_LABEL[k]}
                </span>
              )
            })}
          </span>
        </span>
        <span className="term-sysbar-more">
          {metricsStale && <i className="term-sysbar-stale" aria-hidden="true" />}
          {open ? 'Tutup' : 'Detail'}
          <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d={open ? 'M6 15l6-6 6 6' : 'M6 9l6 6 6-6'} />
          </svg>
        </span>
      </button>
    </div>
  )
}
