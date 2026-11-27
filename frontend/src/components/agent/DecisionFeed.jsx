// Feed keputusan agent dalam bentuk kartu, bukan dinding log: aksi berwarna,
// simbol, keyakinan, alasan yang bisa dibuka, dan waktu relatif. Sumber data
// sama dengan halaman lama (audit keputusan agent), hanya disegarkan berkala.
import { useEffect, useState } from 'react'
import { DEMO, desk, getAgentDecisions } from '../../lib/api'
import { DebugOnly } from '../../lib/debug'
import { clockLabel, readableReason, relativeTime, useNow } from './format'

const POLL_MS = 20000
const LIMIT = 40

const KIND = {
  hold: { label: 'HOLD', tone: 'hold' },
  cut: { label: 'TUTUP', tone: 'sell' },
  close: { label: 'TUTUP', tone: 'sell' },
  sl: { label: 'SL', tone: 'warn' },
  be: { label: 'BE', tone: 'warn' },
  tp: { label: 'TP', tone: 'warn' },
  invalid: { label: 'DITOLAK', tone: 'sell' },
  cycle_skipped: { label: 'LEWAT', tone: 'hold' },
}

const FOLLOW_UP = {
  AGENT_ORDER: 'order dikirim',
  AGENT_LAYER: 'layer ditambah',
  AGENT_HOLD: 'tanpa order',
  AGENT_MODIFY: 'posisi disesuaikan',
  AGENT_CLOSE: 'posisi ditutup',
  AGENT_INVALID: 'ditolak risk gate',
}

function actionOf(kind, side) {
  if (kind === 'order' || kind === 'layer') {
    if (side === 'buy') return { label: 'BUY', tone: 'buy' }
    if (side === 'sell') return { label: 'SELL', tone: 'sell' }
    return { label: kind === 'layer' ? 'LAYER' : 'ORDER', tone: 'buy' }
  }
  return KIND[kind] || { label: 'CATATAN', tone: 'hold' }
}

function errorText(code) {
  if (code === 'DEMO') return 'Mode demo: feed keputusan tidak tersedia.'
  if (code === 'FORBIDDEN') return 'Sesi ini tidak punya akses ke feed keputusan agent.'
  if (code === 'AUTH') return 'Sesi berakhir. Muat ulang halaman untuk masuk lagi.'
  if (code === 'UNAVAILABLE') return 'Agent belum dikonfigurasi, feed keputusan belum bisa dimuat.'
  return 'Feed keputusan belum bisa dimuat.'
}

export default function DecisionFeed() {
  const [rows, setRows] = useState(null)
  const [errorCode, setErrorCode] = useState(null)
  const [sides, setSides] = useState({})
  const [reloadKey, setReloadKey] = useState(0)
  const now = useNow(POLL_MS)

  useEffect(() => {
    let alive = true
    const load = () => {
      getAgentDecisions({ limit: LIMIT })
        .then((body) => {
          if (!alive) return
          setRows(Array.isArray(body?.decisions) ? body.decisions : [])
          setErrorCode(null)
        })
        .catch((ex) => {
          if (!alive) return
          setErrorCode(ex?.code || 'ERROR')
          setRows((prev) => prev || [])
        })
    }
    load()
    const t = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [reloadKey])

  // Arah order (beli/jual) hanya ada di data order, bukan di catatan keputusan:
  // dibaca sekali dari daftar order terakhir, tanpa menebak.
  useEffect(() => {
    if (DEMO) return undefined
    let alive = true
    desk
      .fetchOrders(200)
      .then((list) => {
        if (!alive) return
        const map = {}
        for (const order of list || []) {
          if (order?.id && order?.side) map[order.id] = String(order.side).toLowerCase()
        }
        setSides(map)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  let body
  if (rows === null) {
    body = <p className="agx-empty">Memuat keputusan agent…</p>
  } else if (rows.length === 0) {
    body = (
      <p className="agx-empty">
        {errorCode
          ? errorText(errorCode)
          : 'Belum ada keputusan tercatat. Agent menulis catatan tiap siklus, termasuk saat menahan posisi.'}
      </p>
    )
  } else {
    body = (
      <div className="agx-decisions">
        {rows.map((entry) => (
          <DecisionCard key={entry.id} entry={entry} sides={sides} now={now} />
        ))}
      </div>
    )
  }

  return (
    <section className="agx-panel" aria-label="Keputusan agent">
      <header className="agx-panel-head">
        <div>
          <h2 className="agx-h2">Keputusan agent</h2>
          <p className="agx-hint">Diperbarui otomatis tiap beberapa detik.</p>
        </div>
        <div className="agx-panel-tools">
          {rows && rows.length > 0 && <span className="agx-chip is-idle">{rows.length} keputusan</span>}
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setReloadKey((n) => n + 1)}>
            Muat ulang
          </button>
        </div>
      </header>
      {errorCode && rows && rows.length > 0 && <p className="agx-note is-warn">{errorText(errorCode)}</p>}
      {body}
      <DebugOnly label="sumber">/llm-agent/decisions · arah order dari /orders</DebugOnly>
    </section>
  )
}

function DecisionCard({ entry, sides, now }) {
  const [open, setOpen] = useState(false)
  const decision = entry?.decision || {}
  const at = Date.parse(entry?.created_at)
  const side = entry?.order_id ? sides[entry.order_id] : undefined
  const action = actionOf(decision.kind, side)
  const confidence = Number(decision.confidence)
  const confPct = Number.isFinite(confidence)
    ? Math.max(0, Math.min(100, Math.round(confidence * 100)))
    : null
  const reason = readableReason(decision.reasoning)
  const longReason = reason.length > 100
  const followUp = FOLLOW_UP[entry?.to_status]

  return (
    <article className={`agx-decision is-${action.tone}`}>
      <header className="agx-decision-head">
        <span className={`agx-act is-${action.tone}`}>{action.label}</span>
        <span className="agx-symbol num">{decision.symbol || '—'}</span>
        <time className="agx-time" dateTime={Number.isFinite(at) ? new Date(at).toISOString() : undefined} title={clockLabel(at)}>
          {relativeTime(at, now)}
        </time>
      </header>

      <div className="agx-conf">
        <span className="agx-conf-label">Keyakinan</span>
        <span className="agx-bar" aria-hidden="true">
          <i style={{ width: `${confPct ?? 0}%` }} />
        </span>
        <span className="agx-conf-value num">{confPct == null ? '—' : `${confPct}%`}</span>
      </div>

      <p className={`agx-reason${open ? ' is-open' : ''}`}>{reason}</p>
      {longReason && (
        <button type="button" className="agx-more" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? 'Ringkas' : 'Selengkapnya'}
        </button>
      )}

      <footer className="agx-decision-foot">
        <span className="agx-foot-item num" title={decision.model || undefined}>{decision.model || '—'}</span>
        {followUp && <span className="agx-foot-item">{followUp}</span>}
      </footer>
      <DebugOnly label="detail">
        {decision.cycle_id ? `siklus ${decision.cycle_id} · ` : ''}
        {decision.latency_ms != null ? `${decision.latency_ms} ms · ` : ''}
        status {entry?.to_status || '—'}
      </DebugOnly>
    </article>
  )
}
