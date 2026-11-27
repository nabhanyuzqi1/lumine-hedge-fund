// Drawer detail order (slide-over kanan). Isi: ringkasan order, SELURUH alasan
// penolakan sebagai daftar pendek, jejak status, dan (hanya Mode Debug) data
// mentah. Esc + klik overlay menutup; fokus terkunci di dalam drawer.
import { useEffect, useRef } from 'react'
import { DebugOnly } from '../../lib/debug'
import {
  STATUS_LABEL,
  analyzeOrder,
  createdAt,
  formatFull,
  formatLot,
  formatPrice,
  formatSlippage,
  formatStamp,
  orderEvents,
  orderPrices,
  slippageOf,
  toMs,
} from './reasons'

function sideLabel(side) {
  return String(side ?? '').toLowerCase() === 'buy' ? 'Beli' : 'Jual'
}

export default function OrderDrawer({ order, events, loading, error, onClose }) {
  const panelRef = useRef(null)
  const closeRef = useRef(null)
  const open = Boolean(order)

  useEffect(() => {
    if (!open) return undefined
    const previous = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const focusables = () => Array.from(
      panelRef.current?.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])') ?? [],
    ).filter((element) => !element.disabled && element.getClientRects().length > 0)

    const onKey = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      const elements = focusables()
      if (elements.length === 0) return
      const first = elements[0]
      const last = elements[elements.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKey)
    const timer = setTimeout(() => closeRef.current?.focus(), 0)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previousOverflow
      clearTimeout(timer)
      if (previous instanceof HTMLElement) previous.focus()
    }
  }, [open, onClose])

  if (!order) return null

  const list = Array.isArray(events) ? events : orderEvents(order)
  const fillEvent = list.find((event) => event?.state === 'FILLED')
  const fillMs = toMs(fillEvent?.t)
  const lastEvent = list.at(-1)
  const { requested, filled } = orderPrices(order)
  const slip = slippageOf(order)
  const analysis = analyzeOrder({ ...order, events: order.events ?? list })
  const rejected = analysis.verdict === 'DITOLAK'
  const decided = analysis.verdict === 'LULUS' ? 'pass' : rejected ? 'reject' : null
  const created = createdAt(order)

  const rows = [
    ['ID order', order.id],
    ['Simbol', order.symbol || '·'],
    ['Sisi', sideLabel(order.side)],
    ['Lot', formatLot(order.volume)],
    ['Status', STATUS_LABEL[order.status] ?? order.status ?? '·'],
    ['Strategi', order.strategy || 'Manual'],
    ['Dibuat', formatFull(created)],
    ['Waktu eksekusi', fillMs ? formatFull(fillMs) : 'Belum terisi'],
    ['Status terakhir', lastEvent?.t ? formatStamp(lastEvent.t) : '·'],
    ['Harga diminta', requested !== null ? formatPrice(requested) : '·'],
    ['Harga terisi', filled !== null ? formatPrice(filled) : '·'],
    ['Slippage', slip ? formatSlippage(order, slip) : '·'],
    ['Stop loss', order.sl != null ? formatPrice(order.sl) : '·'],
    ['Take profit', order.tp != null ? formatPrice(order.tp) : '·'],
  ]

  const rawNotes = list
    .map((event) => event?.note)
    .filter((note) => typeof note === 'string' && note.trim())

  return (
    <div className="lh-overlay" onClick={onClose} role="presentation">
      <aside
        className="lh-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="lh-drawer-title"
        ref={panelRef}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="lh-drawer-head">
          <div className="lh-drawer-head-main">
            <p className="lh-drawer-kicker">Detail order</p>
            <h2 className="lh-drawer-title" id="lh-drawer-title">
              {order.symbol || 'Order'} · {sideLabel(order.side)} {formatLot(order.volume)} lot
            </h2>
            <p className="lh-drawer-id num">{order.id}</p>
          </div>
          <button ref={closeRef} type="button" className="lh-close" onClick={onClose} aria-label="Tutup detail order">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M18 6 6 18M6 6l12 12" strokeLinecap="round" />
            </svg>
          </button>
        </header>

        <div className="lh-drawer-body">
          <div className="lh-drawer-status">
            {decided && (
              <span className={`lh-chip ${decided === 'reject' ? 'is-bad' : 'is-ok'}`}>
                {decided === 'reject' ? 'Ditolak' : 'Lulus'}
              </span>
            )}
            <span className="lh-chip">{STATUS_LABEL[order.status] ?? order.status ?? '·'}</span>
            {rejected && analysis.groups.length > 0 && (
              <span className="lh-drawer-status-note">{analysis.groups.length} alasan tercatat</span>
            )}
          </div>

          {rejected && analysis.items.length > 0 && (
            <section className="lh-section" aria-label="Alasan penolakan">
              <h3 className="lh-section-title">Alasan penolakan</h3>
              <ul className="lh-reasons">
                {analysis.items.map((item, index) => (
                  <li key={`${item.label}-${index}`} className="lh-reason">
                    <span className="lh-reason-label">{item.label}</span>
                    <span className="lh-reason-text">{item.detail}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {rejected && analysis.items.length === 0 && (
            <section className="lh-section" aria-label="Alasan penolakan">
              <h3 className="lh-section-title">Alasan penolakan</h3>
              <p className="lh-muted">Order ditolak tanpa alasan terperinci yang tercatat.</p>
            </section>
          )}

          <section className="lh-section" aria-label="Rincian order">
            <h3 className="lh-section-title">Rincian order</h3>
            <dl className="lh-kv">
              {rows.map(([label, value]) => (
                <div key={label} className="lh-kv-row">
                  <dt>{label}</dt>
                  <dd className={label === 'ID order' ? 'num lh-kv-id' : 'num'}>{value}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="lh-section" aria-label="Jejak status">
            <h3 className="lh-section-title">Jejak status</h3>
            {error ? (
              <p className="lh-muted">Jejak status tidak dapat dimuat sekarang.</p>
            ) : loading && list.length === 0 ? (
              <p className="lh-muted">Memuat jejak status…</p>
            ) : list.length === 0 ? (
              <p className="lh-muted">Belum ada jejak status untuk order ini.</p>
            ) : (
              <ol className="lh-timeline">
                {list.map((event, index) => (
                  <li key={event?.id ?? index} className="lh-timeline-item">
                    <span className="lh-timeline-dot" aria-hidden="true" />
                    <span className="lh-timeline-state">{STATUS_LABEL[event?.state] ?? event?.state ?? '·'}</span>
                    <span className="lh-timeline-time num">{formatStamp(event?.t)}</span>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <DebugOnly label="Data mentah">
            <div className="lh-debug">
              <p>fail_reason: {order.fail_reason || '·'}</p>
              <p>fail_detail: {order.fail_detail ? JSON.stringify(order.fail_detail) : '·'}</p>
              <p>events: {list.length}</p>
              {rawNotes.slice(0, 6).map((note, index) => (
                <p key={index}>note {index + 1}: {note}</p>
              ))}
            </div>
          </DebugOnly>
        </div>

        <footer className="lh-drawer-foot">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Tutup</button>
        </footer>
      </aside>
    </div>
  )
}
