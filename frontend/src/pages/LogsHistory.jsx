// Halaman gabungan "Riwayat & Log" (3 sub-tab).
//   order      : tabel order + drawer detail (perbaikan kolom RISK)
//   killswitch : timeline event penghenti darurat
//   audit      : jejak audit + sesi login
// Tab aktif disimpan di query string (?tab=order|killswitch|audit) sehingga
// bisa di-deep-link dan bertahan saat reload.
//
// Data: hanya endpoint yang sudah dipakai aplikasi (GET /orders,
// GET /orders/{id}, GET /kill-switch, GET /audit, GET /auth/sessions).
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { DEMO, desk, fetchKillSwitchStatus } from '../lib/api'
import { useDesk } from '../lib/useDesk'
import SubTabs from '../components/SubTabs'
import AuditPanel from '../components/history-log/AuditPanel'
import KillSwitchPanel from '../components/history-log/KillSwitchPanel'
import OrderDrawer from '../components/history-log/OrderDrawer'
import OrdersPanel from '../components/history-log/OrdersPanel'
import PaperPanel from '../components/history-log/PaperPanel'
// Filter bar Riwayat memakai kelas lld- (satu sumber gaya dengan halaman lama).
import '../styles/ledger-lab-guard.css'
import '../styles/logs-history.css'

const TABS = [
  { id: 'order', label: 'Riwayat order' },
  { id: 'paper', label: 'Trade paper' },
  { id: 'killswitch', label: 'Event kill-switch' },
  { id: 'audit', label: 'Audit & sesi' },
]

const TAB_IDS = TABS.map((tab) => tab.id)

export default function LogsHistory() {
  const state = useDesk()
  const [params, setParams] = useSearchParams()
  const [older, setOlder] = useState([])
  const [killSwitch, setKillSwitch] = useState(null)
  const [selected, setSelected] = useState(null)
  const [eventCache, setEventCache] = useState({})
  const [loadingId, setLoadingId] = useState(null)

  const rawTab = params.get('tab')
  const tab = TAB_IDS.includes(rawTab) ? rawTab : 'order'

  const selectTab = useCallback((id) => {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      next.set('tab', id)
      return next
    }, { replace: true })
  }, [setParams])

  useEffect(() => {
    let alive = true
    // Riwayat lebih dalam dari jendela SSE (default 50): sekali muat 200 lalu
    // digabung tanpa duplikat id.
    desk.fetchOrders(200)
      .then((rows) => { if (alive) setOlder(Array.isArray(rows) ? rows : []) })
      .catch(() => { /* offline/demo: pakai daftar dari SSE */ })
    if (!DEMO) {
      fetchKillSwitchStatus()
        .then((body) => { if (alive && body) setKillSwitch(body) })
        .catch(() => { /* state dari SSE tetap dipakai */ })
    }
    return () => { alive = false }
  }, [])

  const orders = useMemo(() => {
    const live = state?.orders ?? []
    if (older.length === 0) return live
    const ids = new Set(live.map((order) => order.id))
    return [...live, ...older.filter((order) => !ids.has(order.id))]
  }, [state?.orders, older])

  const liveKillSwitch = killSwitch ?? state?.killSwitch ?? null
  const killEvents = Array.isArray(liveKillSwitch?.events) ? liveKillSwitch.events.length : 0

  const openOrder = useCallback((order) => {
    setSelected(order)
    if (order.events == null && eventCache[order.id] == null) {
      setLoadingId(order.id)
      desk.loadOrderEvents(order.id)
        .then((events) => setEventCache((cache) => ({ ...cache, [order.id]: { events: events ?? [] } })))
        .catch((error) => setEventCache((cache) => ({ ...cache, [order.id]: { error: error.message } })))
        .finally(() => setLoadingId(null))
    }
  }, [eventCache])

  const closeDrawer = useCallback(() => setSelected(null), [])

  const drawerEvents = selected ? eventCache[selected.id]?.events ?? selected.events : undefined
  const drawerError = selected ? eventCache[selected.id]?.error ?? null : null

  return (
    <div className="lh-page">
      <header className="lh-head">
        <div className="lh-head-main">
          <h1 className="lh-title">Riwayat &amp; Log</h1>
          <p className="lh-sub">Buku besar order live, trade paper (simulasi runner), kejadian kill-switch, dan jejak audit akun dalam satu halaman.</p>
        </div>
        <div className="lh-head-meta">
          <span className="lh-chip">{orders.length} order</span>
          {killEvents > 0 && <span className="lh-chip">{killEvents} kejadian</span>}
        </div>
      </header>

      <SubTabs
        tabs={TABS.map((item) => ({
          id: item.id,
          label: item.label,
          count: item.id === 'order' ? orders.length : item.id === 'killswitch' ? killEvents : undefined,
        }))}
        value={tab}
        onChange={selectTab}
        ariaLabel="Bagian riwayat dan log"
      />

      {tab === 'order' && (
        <OrdersPanel orders={orders} selectedId={selected?.id ?? null} onOpenOrder={openOrder} />
      )}
      {tab === 'paper' && <PaperPanel />}
      {tab === 'killswitch' && <KillSwitchPanel killSwitch={liveKillSwitch} />}
      {tab === 'audit' && <AuditPanel />}

      <OrderDrawer
        order={selected}
        events={drawerEvents}
        loading={Boolean(selected) && loadingId === selected?.id}
        error={drawerError}
        onClose={closeDrawer}
      />
    </div>
  )
}
