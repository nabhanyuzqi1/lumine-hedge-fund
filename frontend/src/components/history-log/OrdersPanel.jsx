// Sub-tab 1: tabel Riwayat Order.
// Kolom RISK sengaja diringkas (maksimal dua badge + "+N"); seluruh alasan
// hidup di drawer detail. Filter/pagination memakai ulang HistoryFilters.
import { useMemo, useState } from 'react'
import { toast } from '../../lib/api'
import HistoryFilters from '../HistoryFilters'
import RiskBadges from './RiskBadges'
import {
  STATUS_LABEL,
  analyzeOrder,
  createdAt,
  formatLot,
  formatPrice,
  formatStamp,
  formatSlippage,
  orderPrices,
  slippageOf,
} from './reasons'

const STATUS_TABS = ['semua', 'FILLED', 'CLOSED', 'RISK_FAIL', 'FAILED']
const PAGE_SIZE = 25
const DEFAULT_FILTERS = { strategi: '', symbol: '', reason: '', range: 'semua' }

function matches(order, status, filters) {
  if (status !== 'semua' && order.status !== status) return false
  if (filters.strategi && (order.strategy || 'manual') !== filters.strategi) return false
  if (filters.symbol && order.symbol !== filters.symbol) return false
  if (filters.reason) {
    const labels = analyzeOrder(order).groups.map((group) => group.label)
    if (!labels.includes(filters.reason)) return false
  }
  if (filters.range !== 'semua') {
    const stamp = createdAt(order)
    if (stamp === null) return false
    if (filters.range === 'hari') {
      const start = new Date()
      start.setHours(0, 0, 0, 0)
      if (stamp < start.getTime()) return false
    } else if (stamp < Date.now() - 7 * 86400000) return false
  }
  return true
}

function csvCell(value) {
  if (value === null || value === undefined) return ''
  const text = String(value)
  return /[",\n;]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

function buildCsv(rows) {
  const head = [
    'waktu', 'order_id', 'simbol', 'sisi', 'lot', 'harga_diminta', 'harga_terisi',
    'slippage', 'sl', 'tp', 'status', 'strategi', 'keputusan_risk', 'alasan_singkat', 'alasan_lengkap',
  ]
  const lines = rows.map((order) => {
    const { requested, filled } = orderPrices(order)
    const slip = slippageOf(order)
    const analysis = analyzeOrder(order)
    return [
      formatStamp(createdAt(order)),
      order.id,
      order.symbol,
      String(order.side ?? '').toUpperCase(),
      order.volume,
      requested ?? '',
      filled ?? '',
      slip ? formatSlippage(order, slip) : '',
      order.sl ?? '',
      order.tp ?? '',
      order.status,
      order.strategy || 'manual',
      analysis.verdict || '',
      analysis.groups.map((group) => group.label).join(' | '),
      analysis.items.map((item) => item.detail).join(' | '),
    ].map(csvCell).join(';')
  })
  const meta = `# Ekspor riwayat order; tanggal=${new Date().toISOString()}; baris=${rows.length}`
  // BOM + delimiter ; supaya Excel locale Indonesia membuka kolom dengan benar.
  return `\uFEFF${meta}\n${head.join(';')}\n${lines.join('\n')}`
}

function downloadCsv(rows) {
  const blob = new Blob([buildCsv(rows)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const now = new Date()
  const stamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`
  link.href = url
  link.download = `riwayat-order-${stamp}.csv`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
  toast('CSV diunduh', `${rows.length} order diekspor sesuai filter aktif`)
}

function statusTone(status) {
  if (['FILLED', 'CLOSED', 'FILLED_THEN_CLOSED', 'RECONCILED', 'ORPHAN_CLOSED'].includes(status)) return 'is-ok'
  if (['RISK_FAIL', 'FAILED', 'STUCK'].includes(status)) return 'is-bad'
  return 'is-neutral'
}

export default function OrdersPanel({ orders, selectedId, onOpenOrder }) {
  const [status, setStatus] = useState('semua')
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [page, setPage] = useState(0)

  const options = useMemo(() => {
    const strategi = new Set()
    const symbol = new Set()
    const reason = new Set()
    for (const order of orders) {
      strategi.add(order.strategy || 'manual')
      if (order.symbol) symbol.add(order.symbol)
      for (const group of analyzeOrder(order).groups) reason.add(group.label)
    }
    const sorted = (set) => [...set].sort((a, b) => a.localeCompare(b, 'id'))
    return { strategi: sorted(strategi), symbol: sorted(symbol), reason: sorted(reason) }
  }, [orders])

  const filtered = useMemo(
    () =>
      orders
        .filter((order) => matches(order, status, filters))
        // Urutan tampilan selalu terbaru dulu, termasuk saat daftar berasal
        // dari gabungan jendela SSE + riwayat mendalam (urutan tidak dijamin).
        .sort((a, b) => (createdAt(b) ?? 0) - (createdAt(a) ?? 0)),
    [orders, status, filters],
  )

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const current = Math.min(page, pageCount - 1)
  const start = current * PAGE_SIZE
  const rows = filtered.slice(start, start + PAGE_SIZE)

  const dirty = status !== 'semua' || Boolean(filters.strategi || filters.symbol || filters.reason) || filters.range !== 'semua'

  function patchFilters(patch) {
    setFilters((previous) => ({ ...previous, ...patch }))
    setPage(0)
  }

  function clearFilters() {
    setFilters(DEFAULT_FILTERS)
    setStatus('semua')
    setPage(0)
  }

  return (
    <section className="lh-panel" aria-label="Riwayat order">
      <div className="lh-panel-head">
        <div className="lh-panel-title">
          <h2>Riwayat order</h2>
          <p>Setiap order yang dikirim ke broker, terbaru dulu. Klik satu baris untuk detail dan seluruh alasan penolakan.</p>
        </div>
        <div className="lh-panel-actions">
          <div className="lh-tabs" role="group" aria-label="Filter status order">
            {STATUS_TABS.map((id) => (
              <button
                key={id}
                type="button"
                className={`lh-tab ${status === id ? 'is-active' : ''}`}
                aria-pressed={status === id}
                onClick={() => { setStatus(id); setPage(0) }}
              >
                {id === 'semua' ? 'Semua' : STATUS_LABEL[id] ?? id}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => downloadCsv(filtered)}
            disabled={filtered.length === 0}
            title="Unduh daftar order sesuai filter aktif"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" className="btn-icon">
              <path d="M12 3v12m0 0 4-4m-4 4-4-4" />
              <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
            </svg>
            CSV
          </button>
        </div>
      </div>

      <HistoryFilters
        filters={filters}
        onChange={patchFilters}
        options={options}
        onClear={clearFilters}
        dirty={dirty}
      />

      <div className="lh-table-wrap">
        {filtered.length === 0 ? (
          <p className="lh-empty">
            {orders.length === 0 ? 'Belum ada order yang tercatat.' : 'Belum ada order pada filter ini.'}
          </p>
        ) : (
          <table className="lh-table">
            <caption className="sr-only">Daftar order beserta ringkasan keputusan risiko</caption>
            <thead>
              <tr>
                <th scope="col">Waktu</th>
                <th scope="col">Simbol</th>
                <th scope="col">Sisi</th>
                <th scope="col" className="lh-num">Lot</th>
                <th scope="col" className="lh-num">Harga</th>
                <th scope="col">Status</th>
                <th scope="col" className="lh-col-risk">Risiko</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((order) => {
                const { requested, filled } = orderPrices(order)
                const side = String(order.side ?? '').toLowerCase()
                const price = filled ?? requested
                return (
                  <tr
                    key={order.id}
                    className={`lh-row ${selectedId === order.id ? 'is-open' : ''}`}
                    onClick={() => onOpenOrder(order)}
                  >
                    <td className="lh-col-time">
                      <button
                        type="button"
                        className="lh-row-open num"
                        onClick={(event) => {
                          event.stopPropagation()
                          onOpenOrder(order)
                        }}
                        aria-label={`Buka detail order ${order.symbol || ''} ${formatLot(order.volume)} lot`}
                      >
                        {formatStamp(createdAt(order))}
                      </button>
                    </td>
                    <td className="lh-col-symbol">{order.symbol || '·'}</td>
                    <td>
                      <span className={`lh-side is-${side === 'buy' ? 'buy' : 'sell'}`}>
                        {side === 'buy' ? 'BUY' : 'SELL'}
                      </span>
                    </td>
                    <td className="lh-num">{formatLot(order.volume)}</td>
                    <td className="lh-num lh-price">
                      <span className="lh-price-main">{price !== null ? formatPrice(price) : '·'}</span>
                      {filled !== null && requested !== null && (
                        <span className="lh-price-sub">minta {formatPrice(requested)}</span>
                      )}
                    </td>
                    <td>
                      <span className={`lh-status ${statusTone(order.status)}`}>
                        {STATUS_LABEL[order.status] ?? order.status ?? '·'}
                      </span>
                    </td>
                    <td className="lh-col-risk">
                      <RiskBadges order={order} onOpen={() => onOpenOrder(order)} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="lh-pager">
        <span className="lh-pager-info" aria-live="polite">
          {filtered.length === 0
            ? '0 order'
            : `${start + 1}–${Math.min(start + PAGE_SIZE, filtered.length)} dari ${filtered.length} order`}
        </span>
        <div className="lh-pager-buttons">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setPage(Math.max(0, current - 1))}
            disabled={current <= 0}
          >
            Sebelumnya
          </button>
          <span className="lh-pager-page num">{current + 1} / {pageCount}</span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setPage(Math.min(pageCount - 1, current + 1))}
            disabled={current >= pageCount - 1}
          >
            Berikutnya
          </button>
        </div>
      </div>
    </section>
  )
}
