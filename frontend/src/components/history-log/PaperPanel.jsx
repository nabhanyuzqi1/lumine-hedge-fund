// Sub-tab "Paper": buku besar paper_orders (runner simulasi).
// Trade paper tidak pernah dikirim ke broker, jadi tidak muncul di tab
// "Riwayat order" (GET /orders = ledger live). Di sinilah P&L yang tampil
// di Strategy Lab bisa ditelusuri per trade (kapan entry/exit, kenapa exit).
import { useEffect, useMemo, useState } from 'react'
import { fetchPaperOrders } from '../../lib/api'
import { formatLot, formatPrice, formatStamp } from './reasons'

const STATUS_TABS = ['semua', 'CLOSED', 'OPEN', 'REJECTED']
const STATUS_LABEL = {
  CLOSED: 'Closed',
  OPEN: 'Open',
  REJECTED: 'Ditolak',
  PENDING: 'Pending',
}

function tone(status) {
  if (status === 'CLOSED') return 'is-ok'
  if (status === 'REJECTED') return 'is-bad'
  return 'is-warn'
}

function stampOf(iso) {
  const parsed = iso ? Date.parse(iso) : null
  return Number.isFinite(parsed) ? formatStamp(parsed) : '·'
}

function priceText(value) {
  return value === null || value === undefined ? '·' : formatPrice(value)
}

export default function PaperPanel() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [strategies, setStrategies] = useState([])
  const [strategy, setStrategy] = useState('semua')
  const [status, setStatus] = useState('semua')

  useEffect(() => {
    let alive = true
    setLoading(true)
    fetchPaperOrders({ limit: 200 })
      .then((data) => {
        if (!alive) return
        const list = Array.isArray(data) ? data : []
        setRows(list)
        setStrategies([...new Set(list.map((row) => row.strategy).filter(Boolean))].sort())
        setError(null)
      })
      .catch((err) => { if (alive) setError(err.message) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])

  const filtered = useMemo(() => rows.filter((row) => {
    if (strategy !== 'semua' && row.strategy !== strategy) return false
    if (status !== 'semua' && row.status !== status) return false
    return true
  }), [rows, strategy, status])

  const summary = useMemo(() => {
    const closed = filtered.filter((row) => row.status === 'CLOSED')
    const net = closed.reduce((total, row) => total + (row.profit ?? 0), 0)
    const wins = closed.filter((row) => (row.profit ?? 0) > 0).length
    return {
      closed: closed.length,
      open: filtered.filter((row) => row.status === 'OPEN').length,
      rejected: filtered.filter((row) => row.status === 'REJECTED').length,
      net,
      winrate: closed.length ? Math.round((wins / closed.length) * 100) : null,
    }
  }, [filtered])

  const hasFilters = strategy !== 'semua' || status !== 'semua'

  return (
    <section className="lh-panel">
      <p className="lh-sub lh-paper-note">
        Trade <strong>paper</strong> (simulasi runner) tidak pernah dikirim ke broker,
        jadi tidak muncul di tab “Riwayat order”. Rekap di sini harus sama dengan
        P&amp;L strategi di Agent &amp; Strategi.
      </p>

      <div className="lh-paper-sum" aria-live="polite">
        <span className="lh-chip">{summary.closed} closed</span>
        <span className="lh-chip">{summary.open} open</span>
        <span className="lh-chip">{summary.rejected} ditolak</span>
        <span className={`lh-chip lh-pnl ${summary.net >= 0 ? 'is-up' : 'is-down'}`}>
          Net {summary.net >= 0 ? '+' : ''}{summary.net.toFixed(2)} USD
        </span>
        {summary.winrate !== null && (
          <span className="lh-chip">Winrate {summary.winrate}%</span>
        )}
      </div>

      <div className="lld-toolbar" role="group" aria-label="Filter trade paper">
        <div className="lld-field">
          <span className="lld-field-label">Strategi</span>
          <select
            className={`lld-select ${strategy !== 'semua' ? 'is-active' : ''}`}
            value={strategy}
            onChange={(event) => setStrategy(event.target.value)}
          >
            <option value="semua">semua</option>
            {strategies.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </div>
        <div className="lld-field">
          <span className="lld-field-label">Status</span>
          <div className="lld-tabs" role="group" aria-label="Status trade">
            {STATUS_TABS.map((item) => (
              <button
                key={item}
                type="button"
                className={`lld-tab ${status === item ? 'is-active' : ''}`}
                onClick={() => setStatus(item)}
              >
                {item === 'semua' ? 'semua' : STATUS_LABEL[item] ?? item}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && <p className="lh-error" role="alert">Gagal memuat ledger paper: {error}</p>}
      {loading ? (
        <p className="lh-sub">Memuat…</p>
      ) : filtered.length === 0 ? (
        <p className="lh-sub">{hasFilters ? 'Tidak ada trade paper yang cocok dengan filter.' : 'Belum ada trade paper.'}</p>
      ) : (
        <div className="lh-table-wrap">
          <table className="lh-table">
            <caption className="sr-only">Daftar trade paper per strategi</caption>
            <thead>
              <tr>
                <th scope="col">Waktu</th>
                <th scope="col">Strategi</th>
                <th scope="col">Simbol</th>
                <th scope="col">Sisi</th>
                <th scope="col" className="lh-num">Lot</th>
                <th scope="col" className="lh-num">Entry</th>
                <th scope="col" className="lh-num">Exit</th>
                <th scope="col" className="lh-num">P/L</th>
                <th scope="col">Status</th>
                <th scope="col">Alasan</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr key={row.id} className="lh-row">
                  <td className="lh-col-time">{stampOf(row.closed_at ?? row.opened_at ?? row.created_at)}</td>
                  <td className="lh-col-symbol">{row.strategy}</td>
                  <td className="lh-col-symbol">{row.symbol}</td>
                  <td>
                    <span className={`lh-side ${String(row.side).toLowerCase() === 'buy' ? 'is-buy' : 'is-sell'}`}>
                      {String(row.side).toUpperCase()}
                    </span>
                  </td>
                  <td className="lh-num">{formatLot(row.volume)}</td>
                  <td className="lh-num lh-price">{priceText(row.entry_price)}</td>
                  <td className="lh-num lh-price">{priceText(row.exit_price)}</td>
                  <td className="lh-num">
                    {row.status === 'CLOSED' && (
                      <span className={`lh-pnl ${(row.profit ?? 0) >= 0 ? 'is-up' : 'is-down'}`}>
                        {(row.profit ?? 0) >= 0 ? '+' : ''}{(row.profit ?? 0).toFixed(2)}
                      </span>
                    )}
                  </td>
                  <td>
                    <span className={`lh-status ${tone(row.status)}`}>
                      {STATUS_LABEL[row.status] ?? row.status}
                    </span>
                  </td>
                  <td className="lh-col-reason">{row.reason ?? '·'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
