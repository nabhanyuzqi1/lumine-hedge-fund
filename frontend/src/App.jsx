import { BrowserRouter, Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import { auth } from './lib/api'
import { useDesk } from './lib/useDesk'
import Login from './pages/Login'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'
import LogsHistory from './pages/LogsHistory'
import AgentStrategi from './pages/AgentStrategi'
import SettingsHub from './pages/SettingsHub'
import Help from './pages/Help'
import EnvBadge, { LiveStrip } from './components/EnvBadge'
import StaleCodeBanner from './components/StaleCodeBanner'
import Toasts from './components/Toasts'
import './styles/tokens.css'
import './styles/global.css'
import './styles/pages.css'
import './styles/guardrail.css'
import './styles/subtabs.css'
import './styles/agent-strategi.css'
import './styles/logs-history.css'
import './styles/settings-hub.css'
import './styles/help.css'
// FONDASI UI: shell (strip alert) + chart candle. Diimpor terakhir supaya
// menang atas aturan legacy di pages.css, tanpa mengubah halaman.
import './styles/shell.css'
import './styles/chart.css'
// Workstation ergonomics Terminal (toolbar satu baris, HUD melayang, dock).
// Dimuat terakhir: menang atas layout header lama tanpa mengubah halaman lain.
import './styles/terminal-ws.css'

const NAV = [
  { to: '/', label: 'Terminal', end: true },
  { to: '/riwayat', label: 'Riwayat' },
  { to: '/agent', label: 'Agent' },
  { to: '/pengaturan', label: 'Pengaturan' },
  { to: '/bantuan', label: 'Bantuan' },
]

function Chrome() {
  // Nav mobile (§21.6): layar kecil memakai drawer/hamburger; tetap bisa
  // pindah halaman + aksi Keluar yang di topbar desktop-only.
  const [drawerOpen, setDrawerOpen] = useState(false)
  const drawerCloseRef = useRef(null)

  useEffect(() => {
    if (!drawerOpen) return
    const onKey = (e) => { if (e.key === 'Escape') setDrawerOpen(false) }
    window.addEventListener('keydown', onKey)
    // Kunci scroll body selama drawer terbuka; fokus awal ke tombol tutup.
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const t = setTimeout(() => drawerCloseRef.current?.focus(), 0)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
      clearTimeout(t)
    }
  }, [drawerOpen])

  return (
    <div className="chrome">
      <header className="topbar">
        <div className="topbar-inner">
          <button
            type="button"
            className="nav-burger"
            onClick={() => setDrawerOpen(true)}
            aria-label="Buka menu navigasi"
            aria-expanded={drawerOpen}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <NavLink to="/" className="brand" aria-label="Lumine Fund">
            <svg className="brand-mark" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round">
              <polygon points="12 2 21 7 21 17 12 22 3 17 3 7 12 2" />
              <line x1="12" y1="22" x2="12" y2="12" />
              <polyline points="21 7 12 12 3 7" />
            </svg>
            <span className="brand-word">LUMINE</span>
            <span className="brand-sub">FUND</span>
          </NavLink>
          <nav className="topnav" aria-label="Navigasi utama">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className="topnav-link">
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="topbar-side">
            <LivePrice />
            {/* §21.1: environment DEV/DEMO/LIVE selalu terlihat di topbar. */}
            <EnvBadge />
            <button className="btn btn-ghost btn-exit" onClick={() => auth.logout()} type="button">
              Keluar
            </button>
          </div>
        </div>
      </header>
      {/* §21.1: strip peringatan LIVE di semua halaman saat env live. */}
      <LiveStrip />
      {/* Sinkronisasi kode: banner hanya muncul bila proses API lebih tua
          dari file di disk (prompt version berbeda). */}
      <StaleCodeBanner />
      <main className="main" id="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/riwayat" element={<LogsHistory />} />
          <Route path="/agent" element={<AgentStrategi />} />
          <Route path="/pengaturan" element={<SettingsHub />} />
          <Route path="/bantuan" element={<Help />} />
          {/* Rute lama diarahkan ke halaman gabungan (bookmark tetap hidup). */}
          <Route path="/lab" element={<Navigate to="/agent?tab=strategi" replace />} />
          <Route path="/ops" element={<Navigate to="/pengaturan?tab=darurat" replace />} />
          <Route path="/admin/guardrail" element={<Navigate to="/pengaturan?tab=risiko" replace />} />
          <Route path="/settings" element={<Navigate to="/pengaturan?tab=agent" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <nav className="bottomnav" aria-label="Navigasi bawah">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className="bottomnav-link">
            <NavIcon name={n.to} />
            <span>{n.short || n.label}</span>
          </NavLink>
        ))}
      </nav>

      {drawerOpen && (
        <div className="drawer-backdrop" onClick={() => setDrawerOpen(false)}>
          <aside
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Menu navigasi"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="drawer-head">
              <span className="drawer-title">Menu</span>
              <button
                ref={drawerCloseRef}
                type="button"
                className="btn btn-ghost drawer-close"
                onClick={() => setDrawerOpen(false)}
                aria-label="Tutup menu"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                  <path d="m6 6 12 12M18 6 6 18" />
                </svg>
              </button>
            </div>
            <nav className="drawer-nav" aria-label="Navigasi menu">
              {NAV.map((n) => (
                <NavLink
                  key={n.to}
                  to={n.to}
                  end={n.end}
                  className="drawer-link"
                  onClick={() => setDrawerOpen(false)}
                >
                  <span>{n.label}</span>
                  <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="m9 6 6 6-6 6" />
                  </svg>
                </NavLink>
              ))}
            </nav>
            <div className="drawer-meta">
              <LivePrice />
              <EnvBadge />
            </div>
            <button className="btn drawer-exit" type="button" onClick={() => auth.logout()}>
              Keluar
            </button>
          </aside>
        </div>
      )}
    </div>
  )
}

function NavIcon({ name }) {
  const common = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }
  if (name === '/agent')
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
        <path d="M4 15.5 8.2 11l3.1 3.1L20 5.4" />
        <path d="M4 20h16" />
        <circle cx="8.2" cy="11" r="1.3" fill="currentColor" stroke="none" />
      </svg>
    )
  if (name === '/settings')
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
        <path d="M4 7h10M18 7h2M4 12h4M12 12h8M4 17h9M17 17h3" />
        <circle cx="16" cy="7" r="2" />
        <circle cx="10" cy="12" r="2" />
        <circle cx="15" cy="17" r="2" />
      </svg>
    )
  if (name === '/admin/guardrail')
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
        <path d="M12 3 5 6v5c0 4.5 3 7.7 7 9 4-1.3 7-4.5 7-9V6l-7-3Z" />
        <path d="m9.2 12 2 2 3.6-4" />
      </svg>
    )
  if (name === '/riwayat')
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
        <path d="M4 6h16M4 12h16M4 18h10" />
      </svg>
    )
  if (name === '/lab')
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
        <path d="M10 3v6L4.8 18a2 2 0 0 0 1.8 3h10.8a2 2 0 0 0 1.8-3L14 9V3M8.5 3h7" />
      </svg>
    )
  if (name === '/ops')
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
        <circle cx="12" cy="12" r="8.5" />
        <circle cx="12" cy="12" r="3.5" />
        <path d="M12 3.5v3M12 17.5v3M3.5 12h3M17.5 12h3" />
      </svg>
    )
  if (name === '/bantuan')
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
        <circle cx="12" cy="12" r="8.5" />
        <path d="M9.5 9.3a2.6 2.6 0 1 1 3.7 2.4c-.8.4-1.2 1-1.2 1.8v.4" />
        <circle cx="12" cy="17.1" r=".9" fill="currentColor" stroke="none" />
      </svg>
    )
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
      <path d="M3 20V10M10 20V4M17 20v-7M3 20h18" />
    </svg>
  )
}

function LivePrice() {
  const state = useDesk()
  const symbol = state?.symbol
  const price = symbol ? state?.quotes?.[symbol]?.price : null
  const [dir, setDir] = useState(0)
  const prevRef = useRef(null)
  useEffect(() => {
    if (price == null) return
    const prev = prevRef.current
    // Arah hanya dihitung dalam simbol yang sama; perpindahan simbol tidak
    // dianggap naik/turun (skala harga XAU vs BTC beda jauh).
    if (prev && prev.symbol === symbol && price !== prev.price) setDir(price > prev.price ? 1 : -1)
    prevRef.current = { symbol, price }
  }, [price, symbol])
  if (price == null || !symbol) return null
  return (
    <div className={`liveprice ${dir > 0 ? 'is-up' : dir < 0 ? 'is-down' : ''}`} aria-label={`Harga live ${symbol}`}>
      <span className="liveprice-dot" aria-hidden="true" />
      <span className="liveprice-label">{symbol}</span>
      <span className="liveprice-num tnum">{price.toFixed(2)}</span>
    </div>
  )
}

function Gate() {
  const [ready, setReady] = useState(auth.isAuthed())
  const location = useLocation()
  useEffect(() => {
    const off = auth.onAuth(() => setReady(auth.isAuthed()))
    // Cookie sesi HttpOnly: verifikasi status awal ke GET /auth/me.
    auth.checkAuth().then(setReady)
    return off
  }, [])
  // Landing publik: selalu bisa diakses, di dalam maupun di luar sesi.
  if (location.pathname === '/landing') return <Landing />
  if (!ready) return <Login />
  if (location.pathname === '/login') return <Navigate to="/" replace />
  return <Chrome />
}

export default function App() {
  return (
    <BrowserRouter>
      {/* Toast feedback global (arm kill-switch, demo reject, order status). */}
      <Toasts />
      <Gate />
    </BrowserRouter>
  )
}
