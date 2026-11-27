import { useEffect, useMemo, useState } from 'react'
import { desk, toast } from '../lib/api'
import { DEMO, useDesk } from '../lib/useDesk'
import HistoryFilters from '../components/HistoryFilters'
import ModeBadge, { ModeLegend } from '../components/ModeBadge'
// Tata letak khusus halaman ledger/lab/guardrail (prefix `lld-`).
import '../styles/ledger-lab-guard.css'

// Mode data buku besar order: GET /orders = order yang dikirim ke broker
// (LIVE). Di mode demo isinya sintetis, jadi badge-nya DEMO.
const DATA_MODE = DEMO ? 'DEMO' : 'LIVE'

const STATUS_LABEL = {
  FILLED: 'Terisi',
  SENT: 'Terkirim',
  DELIVERED: 'Diterima EA',
  RECEIVED: 'Diterima',
  RISK_PASS: 'Risk lolos',
  RISK_FAIL: 'Ditolak risk',
  FAILED: 'Gagal',
  STUCK: 'Stuck',
  RECONCILED: 'Terekonsiliasi',
  FILLED_THEN_CLOSED: 'Terisi lalu ditutup',
  ORPHAN_ADOPTED: 'Orphan diadopsi',
  ORPHAN_CLOSED: 'Orphan ditutup',
  CLOSED: 'Ditutup',
}

function timeOf(t) {
  const d = new Date(t)
  return d.toLocaleTimeString('id-ID', { hour12: false }) + '.' + String(d.getMilliseconds()).padStart(3, '0')
}

const FILTERS = ['semua', 'FILLED', 'CLOSED', 'RISK_FAIL', 'FAILED']

// Filter bar UI-D2 (PRD v2.2 §21.3): strategi/symbol/reason/tanggal.
const DEFAULT_FILTERS = { strategi: '', symbol: '', reason: '', range: 'semua' }

// Ukuran point simbol yang diperdagangkan (digits 2): dipakai untuk
// menampilkan slippage dalam points. Simbol lain fallback ke 0.01.
const POINT_SIZE = { XAUUSD: 0.01, BTCUSD: 0.01 }

// ---- ekstraksi harga & risk dari satu baris order ----
// requested: price_requested dari /orders; fallback payload event pertama
// (PRD §21.3). filled: price_filled / fill, fallback payload event FILLED.
function orderPrices(o) {
  const evts = o.events || []
  const fillEvt = evts.find((e) => e.state === 'FILLED')
  const p0 = evts[0]?.payload
  const req = o.price_requested ?? o.requested_price
    ?? (p0 && typeof p0 === 'object' ? p0.price_requested ?? p0.requested ?? p0.price : null)
  const fil = o.fill != null && o.fill > 0 ? o.fill
    : fillEvt?.payload && typeof fillEvt.payload === 'object' ? fillEvt.payload.price ?? fillEvt.payload.fill : null
  return {
    requested: req != null && req > 0 ? Number(req) : null,
    filled: fil != null && fil > 0 ? Number(fil) : null,
  }
}

function pointSize(symbol) {
  return POINT_SIZE[symbol] ?? 0.01
}

function slippageOf(o) {
  const { requested, filled } = orderPrices(o)
  if (requested == null || filled == null || requested === 0) return null
  const delta = filled - requested
  return { delta, pct: (delta / requested) * 100 }
}

// Semua reason code order: payload.reasons event risk gate (array),
// payload.reason event FAILED/RISK_FAIL, note event RISK_FAIL (demo),
// dan kolom fail_reason. Unik, urut kemunculan.
function orderReasons(o) {
  const out = []
  for (const e of o.events || []) {
    const p = e.payload
    if (p && typeof p === 'object') {
      if (Array.isArray(p.reasons)) {
        for (const r of p.reasons) if (r != null && r !== '') out.push(String(r))
      }
      if (p.reason && (e.state === 'FAILED' || e.state === 'RISK_FAIL')) out.push(String(p.reason))
    }
    if (e.state === 'RISK_FAIL' && e.note) out.push(String(e.note))
  }
  if (o.fail_reason) out.push(String(o.fail_reason))
  return [...new Set(out)]
}

// Keputusan risk gate order: DITOLAK bila ada event RISK_FAIL /
// payload.risk=rejected / status RISK_FAIL; LULUS bila ada
// RISK_PASS / payload.risk=pass. lastGate = event gate terakhir.
function riskOf(o) {
  let decision = null
  let lastGate = null
  for (const e of o.events || []) {
    const p = e.payload
    const risk = p && typeof p === 'object' ? p.risk : null
    if (e.state === 'RISK_FAIL' || e.state === 'RISK_PASS' || risk === 'rejected' || risk === 'pass') lastGate = e
    if (e.state === 'RISK_FAIL' || risk === 'rejected') decision = 'DITOLAK'
    else if ((e.state === 'RISK_PASS' || risk === 'pass') && decision == null) decision = 'LULUS'
  }
  if (o.status === 'RISK_FAIL') decision = 'DITOLAK'
  return { decision, lastGate }
}

function matchesFilters(o, statusFilter, f) {
  if (statusFilter !== 'semua' && o.status !== statusFilter) return false
  if (f.strategi && (o.strategy || 'manual') !== f.strategi) return false
  if (f.symbol && o.symbol !== f.symbol) return false
  if (f.reason && !orderReasons(o).includes(f.reason)) return false
  if (f.range !== 'semua') {
    const t = o.createdMs ?? o.events?.[0]?.t
    if (t == null) return false
    if (f.range === 'hari') {
      const d = new Date()
      d.setHours(0, 0, 0, 0)
      if (t < d.getTime()) return false
    } else if (t < Date.now() - 7 * 86400000) {
      return false
    }
  }
  return true
}

function filtersDirty(statusFilter, f) {
  return statusFilter !== 'semua' || !!(f.strategi || f.symbol || f.reason) || f.range !== 'semua'
}

function filterDesc(statusFilter, f) {
  const parts = [`status=${statusFilter}`, `tanggal=${f.range}`]
  if (f.strategi) parts.push(`strategi=${f.strategi}`)
  if (f.symbol) parts.push(`symbol=${f.symbol}`)
  if (f.reason) parts.push(`reason=${f.reason}`)
  return parts.join(' · ')
}

// ---- ekspor CSV (PRD P1b + audit UI-D2 §21.3) ----
function toCsv(rows, exporter, desc) {
  const head = [
    'waktu', 'order_id', 'symbol', 'side', 'volume',
    'requested_price', 'filled_price', 'slippage', 'slippage_pct',
    'sl', 'tp', 'status', 'strategy', 'risk_decision', 'risk_reason', 'fail_reason',
  ]
  const esc = (v) => {
    if (v == null) return ''
    const s = String(v)
    return /[",\n;]/.test(s) ? '"' + s.replaceAll('"', '""') + '"' : s
  }
  const lines = rows.map((o) => {
    const { requested, filled } = orderPrices(o)
    const slip = slippageOf(o)
    const reasons = orderReasons(o)
    const created = o.createdMs ?? o.events?.[0]?.t
    return [
      created ? new Date(created).toISOString() : '',
      o.id,
      o.symbol,
      String(o.side || '').toUpperCase(),
      o.volume ?? '',
      requested ?? '',
      filled ?? '',
      slip ? slip.delta.toFixed(2) : '',
      slip ? slip.pct.toFixed(4) : '',
      o.sl ?? '',
      o.tp ?? '',
      o.status,
      o.strategy || '',
      riskOf(o).decision || '',
      reasons.join(' | '),
      o.fail_reason || '',
    ].map(esc).join(';')
  })
  // Baris pertama: komentar audit (username exporter + tanggal export +
  // filter aktif) sesuai PRD v2.2 §21.3.
  const audit = `# Audit export: exporter=${exporter || 'unknown'}; tanggal_export=${new Date().toISOString()}; jumlah_baris=${rows.length}; filter=${desc}`
  // BOM agar Excel membaca UTF-8 dengan benar; delimiter ; untuk locale ID
  return '\uFEFF' + audit + '\n' + head.join(';') + '\n' + lines.join('\n')
}

function downloadCsv(rows, exporter, desc) {
  const blob = new Blob([toCsv(rows, exporter, desc)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  const d = new Date()
  const stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}-${String(d.getHours()).padStart(2, '0')}${String(d.getMinutes()).padStart(2, '0')}`
  a.href = url
  a.download = `fund2-riwayat-${stamp}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
  toast('CSV diunduh', `${rows.length} order diekspor sesuai filter aktif`)
}

function fmtSlip(o, slip) {
  const pts = slip.delta / pointSize(o.symbol)
  const sign = (v) => `${v >= 0 ? '+' : ''}`
  const parts = [`${sign(slip.delta)}${pts.toFixed(0)} pts`]
  if (slip.pct != null) parts.push(`${sign(slip.pct)}${slip.pct.toFixed(3)}%`)
  return parts.join(' · ')
}

export default function History() {
  const state = useDesk()
  const [filter, setFilter] = useState('semua')
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [openId, setOpenId] = useState(null)
  // Cache event log per order: daftar /orders menyertakan events, tapi
  // snapshot lama / error SSE bisa kosong; saat baris dibuka event diambil
  // dari GET /orders/{id} dan di-cache agar tidak hilang saat refresh SSE.
  const [evState, setEvState] = useState({})
  const [loadingId, setLoadingId] = useState(null)
  // Riwayat lebih dalam dari jendela SSE (default 50): ambil sekali via
  // GET /orders?limit=200 dan gabungkan tanpa duplikat id (PRD §21.3).
  const [older, setOlder] = useState([])
  // Username exporter untuk baris audit CSV (dari /auth/me).
  const [exporter, setExporter] = useState('')

  useEffect(() => {
    let alive = true
    desk.fetchOrders(200)
      .then((rows) => { if (alive) setOlder(rows) })
      .catch(() => { /* offline/demo: cukup pakai daftar dari SSE */ })
    fetch('/auth/me', { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((b) => { if (alive && b?.username) setExporter(b.username) })
      .catch(() => { /* demo/offline: exporter=unknown di CSV */ })
    return () => { alive = false }
  }, [])

  const orders = useMemo(() => {
    const live = state?.orders || []
    if (!older.length) return live
    const ids = new Set(live.map((o) => o.id))
    const merged = [...live, ...older.filter((o) => !ids.has(o.id))]
    return merged
  }, [state?.orders, older])

  // Opsi dropdown di-derive dari data yang ada (client-side).
  const options = useMemo(() => {
    const strat = new Set()
    const sym = new Set()
    const rsn = new Set()
    for (const o of orders) {
      strat.add(o.strategy || 'manual')
      if (o.symbol) sym.add(o.symbol)
      for (const r of orderReasons(o)) rsn.add(r)
    }
    const sort = (s) => [...s].sort((a, b) => a.localeCompare(b))
    return { strategi: sort(strat), symbol: sort(sym), reason: sort(rsn) }
  }, [orders])

  const shown = useMemo(
    () => orders.filter((o) => matchesFilters(o, filter, filters)),
    [orders, filter, filters],
  )
  const dirty = filtersDirty(filter, filters)

  function patchFilters(patch) {
    setFilters((f) => ({ ...f, ...patch }))
  }

  function clearFilters() {
    setFilter('semua')
    setFilters(DEFAULT_FILTERS)
  }

  function toggleRow(o) {
    const next = openId === o.id ? null : o.id
    setOpenId(next)
    if (next && o.events == null && !evState[o.id] && loadingId !== o.id) {
      setLoadingId(o.id)
      desk.loadOrderEvents(o.id)
        .then((events) => setEvState((s) => ({ ...s, [o.id]: { events: events || [] } })))
        .catch((ex) => setEvState((s) => ({ ...s, [o.id]: { error: ex.message } })))
        .finally(() => setLoadingId(null))
    }
  }

  return (
    <div className="lld-page lld-history">
      {/* Header bar tunggal: judul + subjudul di kiri, aksi (CSV + tab status)
          di kanan. Sebelumnya judul dan aksi terpisah dua blok. */}
      <header className="lld-hdr">
        <div className="lld-hdr-main">
          <h1 className="lld-title">Riwayat order</h1>
          <p className="lld-sub">Buku besar event · setiap transisi state terekam append-only.</p>
        </div>
        <div className="lld-hdr-actions">
          <button
            type="button"
            className="btn btn-ghost btn-sm lld-export"
            onClick={() => downloadCsv(shown, exporter, filterDesc(filter, filters))}
            disabled={shown.length === 0}
            title="Unduh daftar order sesuai filter aktif sebagai CSV"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" className="btn-icon">
              <path d="M12 3v12m0 0 4-4m-4 4-4-4" />
              <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
            </svg>
            CSV
          </button>
          <div className="lld-tabs" role="group" aria-label="Filter status">
            {FILTERS.map((f) => (
              <button key={f} type="button" className={`lld-tab ${filter === f ? 'is-active' : ''}`} aria-pressed={filter === f} onClick={() => setFilter(f)}>
                {f === 'semua' ? 'Semua' : STATUS_LABEL[f] || f}
              </button>
            ))}
          </div>
        </div>
      </header>

      <ModeLegend className="lld-legend" />

      <HistoryFilters
        filters={filters}
        onChange={patchFilters}
        options={options}
        onClear={clearFilters}
        dirty={dirty}
      />

      {/* Tabel full-width: wrapper yang menggulir horizontal sekaligus membawa
          border + radius, header sticky di surface #18181b. */}
      <section className="lld-table-wrap" aria-label="Buku besar order">
        {shown.length === 0 ? (
          <div className="lld-empty">Belum ada order pada filter ini.</div>
        ) : (
          <table className="lld-table">
            <thead>
              <tr>
                <th scope="col" className="lld-col-chev"><span className="sr-only">Detail</span></th>
                <th scope="col" className="lld-col-nowrap">Waktu</th>
                <th scope="col" className="lld-col-nowrap">Order</th>
                <th scope="col">Mode</th>
                <th scope="col">Arah</th>
                <th scope="col" className="lld-col-num">Volume</th>
                <th scope="col" className="lld-col-num">Requested → Filled</th>
                <th scope="col" className="lld-col-num">SL</th>
                <th scope="col" className="lld-col-num">TP</th>
                <th scope="col" className="lld-col-nowrap">Status</th>
                <th scope="col" className="lld-col-risk">Risk</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((o) => (
                <HistoryRow
                  key={o.id}
                  o={o}
                  open={openId === o.id}
                  onToggle={() => toggleRow(o)}
                  ev={evState[o.id]}
                  loading={loadingId === o.id}
                />
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}

function SlipCell({ o }) {
  const { requested, filled } = orderPrices(o)
  const slip = slippageOf(o)
  const side = String(o.side || '').toLowerCase()
  // Slippage adverse utk BUY = fill di atas requested; utk SELL = di bawah.
  const adverse = slip && (side === 'buy' ? slip.delta > 0 : slip.delta < 0)
  const cls = !slip || slip.delta === 0 ? '' : adverse ? 'slip-adverse' : 'slip-favor'
  return (
    <span className="req-fill">
      <span className="req-fill-main">
        <span>{requested != null ? requested.toFixed(2) : '·'}</span>
        <span className="req-fill-arrow" aria-hidden="true">→</span>
        <span>{filled != null ? filled.toFixed(2) : '·'}</span>
      </span>
      {slip && <span className={`req-fill-slip ${cls}`}>{fmtSlip(o, slip)}</span>}
    </span>
  )
}

function RiskCell({ o }) {
  const risk = riskOf(o)
  if (!risk.decision) return <span className="lld-risk-none">·</span>
  const reasons = orderReasons(o)
  // Semua reason ditampilkan (bukan hanya yang pertama + "+n"): kolom RISK
  // melebar 220px dan membungkus, jadi "DITOLAK / auto lot …" terbaca utuh.
  return (
    <span className="lld-risk">
      <span className={`chip ${risk.decision === 'LULUS' ? 'chip-up' : 'chip-down'}`}>{risk.decision}</span>
      {reasons.length > 0 && (
        <span className="lld-risk-reason" title={reasons.join(' · ')}>{reasons.join(' · ')}</span>
      )}
    </span>
  )
}

function HistoryRow({ o, open, onToggle, ev, loading }) {
  const events = o.events ?? ev?.events
  const last = events?.at(-1)
  const fillEvt = events?.find((e) => e.state === 'FILLED')
  const side = String(o.side || '').toLowerCase()
  const t0 = events?.[0]?.t ?? o.createdMs
  const risk = riskOf(o)
  const rejected = risk.decision === 'DITOLAK'
  const reasons = orderReasons(o)
  return (
    <>
      <tr className={`history-row ${open ? 'is-open' : ''}`} onClick={onToggle}>
        <td className="cell-action lld-col-chev">
          <svg className={`chev ${open ? 'chev-open' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="m6 9 6 6 6-6" />
          </svg>
        </td>
        <td className="num text-faint lld-col-nowrap">{t0 ? timeOf(t0) : '·'}</td>
        <td className="num lld-col-nowrap">{o.id}</td>
        <td className="lld-col-nowrap">
          <ModeBadge mode={DATA_MODE} />
        </td>
        <td className="lld-col-nowrap">
          <span className={`chip ${side === 'buy' ? 'chip-up' : 'chip-down'}`}>{side === 'buy' ? 'BELI' : 'JUAL'}</span>
        </td>
        <td className="num lld-col-num">{Number(o.volume).toFixed(2)}</td>
        <td className="num lld-col-num"><SlipCell o={o} /></td>
        <td className="num lld-col-num down-text">{o.sl != null ? Number(o.sl).toFixed(2) : '·'}</td>
        <td className="num lld-col-num up-text">{o.tp != null ? Number(o.tp).toFixed(2) : '·'}</td>
        <td className="lld-col-nowrap">
          <span className={`chip ${o.status === 'FILLED' || o.status === 'CLOSED' || o.status === 'FILLED_THEN_CLOSED' ? 'chip-up' : o.status === 'RISK_FAIL' || o.status === 'FAILED' || o.status === 'STUCK' ? 'chip-down' : ''}`}>
            {STATUS_LABEL[o.status] || o.status}
          </span>
        </td>
        <td className="lld-col-risk"><RiskCell o={o} /></td>
      </tr>
      {open && (
        <tr className="eventrow">
          <td colSpan={11}>
            <div className="eventline">
              {rejected && (
                <div className="risk-detail">
                  <span className="chip chip-down">DITOLAK</span>
                  <span className="risk-detail-reasons">{reasons.join(' · ') || '·'}</span>
                  {risk.lastGate && (
                    <span className="risk-detail-gate">
                      Risk gate terakhir: <strong>{risk.lastGate.state}</strong>
                      {risk.lastGate.t != null ? ` @ ${timeOf(risk.lastGate.t)}` : ''}
                      {risk.lastGate.note ? ` — ${risk.lastGate.note}` : ''}
                    </span>
                  )}
                </div>
              )}
              <div className="eventline-title">
                Event log {o.id}
                {last?.note ? <span className="eventline-note"> · {last.note}</span> : null}
              </div>
              {ev?.error ? (
                <p className="eventline-loading">Gagal memuat event log: {ev.error}</p>
              ) : !events ? (
                <p className="eventline-loading">{loading ? 'Memuat event log…' : 'Tidak ada event tercatat.'}</p>
              ) : events.length === 0 ? (
                <p className="eventline-loading">Tidak ada event tercatat untuk order ini.</p>
              ) : (
                <>
                  <ol className="events">
                    {events.map((e, i) => (
                      <li key={e.id ?? i} className={`event ${e.state === 'FILLED' ? 'event-up' : e.state === 'RISK_FAIL' || e.state === 'FAILED' ? 'event-down' : ''}`}>
                        <span className="event-time num">{e.t != null ? timeOf(e.t) : '·'}</span>
                        <span className="event-state">{e.state}</span>
                        <span className="event-note">{e.note || '·'}</span>
                        {i > 0 && events[i - 1].t != null && e.t != null && (
                          <span className="event-delta num">
                            +{e.t - events[i - 1].t}ms
                          </span>
                        )}
                      </li>
                    ))}
                  </ol>
                  {fillEvt?.t != null && events[0]?.t != null && (
                    <p className="eventline-latency num">
                      Latensi RECEIVED → FILLED: {fillEvt.t - events[0].t} ms
                    </p>
                  )}
                </>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
