// Dock bawah Terminal: satu tempat untuk posisi terbuka, order pending, dan
// eksekusi hari ini — plus metrik akun di kanan judul.
//
// Kenapa dock, bukan tabel terpisah: trader butuh tiga daftar itu berdampingan
// dengan chart, bukan di halaman lain. Angka yang tampil semuanya dari server:
//   - baris posisi/trade: state desk (/positions, /orders)
//   - equity/margin/drawdown: GET /risk/portfolio + GET /metrics (poll 20 s)
// Tidak ada nilai yang dikarang: field yang tidak dikirim API tampil '·'.
import { useEffect, useMemo, useState } from 'react'
import { desk, fetchRiskPortfolio, toast } from '../../lib/api'
import { useDesk } from '../../lib/useDesk'
import { dockModel, fmtPrice, fmtUsd } from '../../lib/chartOrders'
import { SYMBOLS } from '../../lib/market'

const POLL_MS = 20000

const num = (v) => (v == null || Number.isNaN(Number(v)) ? null : Number(v))

function fmtTime(ms) {
  if (!ms) return '·'
  const d = new Date(ms)
  const p = (n) => String(n).padStart(2, '0')
  // WIB = jam kerja trader; server mengirim ISO dengan offset.
  const wib = new Date(d.getTime() + 7 * 3600 * 1000)
  return `${p(wib.getUTCDate())}/${p(wib.getUTCMonth() + 1)} ${p(wib.getUTCHours())}:${p(wib.getUTCMinutes())}`
}

function useAccountMetrics() {
  const [m, setM] = useState({ equity: null, margin: null, drawdown: null, at: 0 })
  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const [p, met] = await Promise.all([
          fetchRiskPortfolio().catch(() => null),
          fetch('/metrics', { credentials: 'include' })
            .then((r) => (r.ok ? r.json() : null))
            .catch(() => null),
        ])
        if (!alive) return
        setM({
          equity: num(p?.equity),
          margin: num(p?.margin_used),
          drawdown: num(met?.risk?.daily_drawdown_pct),
          at: Date.now(),
        })
      } catch {
        // offline: pertahankan angka terakhir, badge menandai umurnya
      }
    }
    load()
    const t = setInterval(load, POLL_MS)
    return () => { alive = false; clearInterval(t) }
  }, [])
  return m
}

function Metric({ label, value, tone = '', title }) {
  return (
    <span className="dock-metric" title={title}>
      <span className="dock-metric-key">{label}</span>
      <span className={`dock-metric-val tnum ${tone}`.trim()}>{value}</span>
    </span>
  )
}

function PnlCell({ pnl, equity }) {
  const n = num(pnl)
  if (n == null) return <span className="tnum">·</span>
  const pct = equity ? (n / equity) * 100 : null
  return (
    <span className={`tnum ${n >= 0 ? 'up-text' : 'down-text'}`}>
      {fmtUsd(n)}
      {pct != null && <span className="dock-pct"> · {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%</span>}
    </span>
  )
}

export default function TradingDock({ symbol }) {
  const state = useDesk()
  const [tab, setTab] = useState('open')
  const metrics = useAccountMetrics()
  const positions = state?.positions || []
  const orders = state?.orders || []
  const quotes = state?.quotes || {}
  const equity = metrics.equity ?? num(state?.equity)

  const dm = useMemo(
    () => dockModel({ positions, orders, symbol }),
    [positions, orders, symbol],
  )

  // Eksekusi hari ini: yang sudah FILLED sejak 00:00 WIB, terbaru dulu.
  const todayRows = useMemo(
    () => dm.today.slice().sort((a, b) => (b.createdMs || 0) - (a.createdMs || 0)),
    [dm.today],
  )
  const openRows = dm.open
  const pendingRows = dm.pending

  const tabs = [
    { id: 'open', label: 'Posisi Terbuka', count: openRows.length },
    { id: 'pending', label: 'Pending Order', count: pendingRows.length },
    { id: 'today', label: 'Eksekusi Hari Ini', count: todayRows.length },
  ]

  async function close(id) {
    try {
      await desk.closePosition(id)
      toast('Posisi ditutup', id)
    } catch (ex) {
      toast('Gagal menutup', ex.message, 'down')
    }
  }

  return (
    <section className="card dock" aria-label="Dock posisi dan eksekusi">
      <div className="dock-head">
        <div className="dock-tabs" role="tablist" aria-label="Daftar order dan posisi">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              className={`dock-tab ${tab === t.id ? 'is-active' : ''}`.trim()}
              onClick={() => setTab(t.id)}
            >
              {t.label}
              <span className={`dock-count ${t.count ? 'has-items' : ''}`.trim()}>{t.count}</span>
            </button>
          ))}
        </div>
        <div className="dock-metrics" aria-label="Metrik akun">
          <Metric label="Equity" value={equity != null ? `$${equity.toFixed(2)}` : '·'} />
          <Metric
            label="Margin"
            value={metrics.margin != null ? `$${metrics.margin.toFixed(2)}` : '·'}
            title="Margin terpakai dari /risk/portfolio (kosong bila broker belum mengirim)"
          />
          <Metric
            label="Floating"
            value={fmtUsd(dm.floating)}
            tone={dm.floating >= 0 ? 'up-text' : 'down-text'}
          />
          <Metric
            label="Drawdown"
            value={metrics.drawdown != null ? `${metrics.drawdown.toFixed(2)}%` : '·'}
            tone={metrics.drawdown != null && metrics.drawdown > 0 ? 'down-text' : ''}
            title="Drawdown harian dari /metrics.risk.daily_drawdown_pct"
          />
        </div>
      </div>

      <div className="dock-body">
        {tab === 'open' && (openRows.length === 0 ? (
          <div className="dock-empty">
            <strong>Tidak ada posisi terbuka</strong>
            <span>Order yang terisi muncul di sini otomatis, lengkap dengan garis entry/SL/TP di chart.</span>
          </div>
        ) : (
          <div className="dock-scroll">
            <table className="dock-table">
              <thead>
                <tr>
                  <th>Waktu</th><th>Simbol</th><th>Sisi</th><th className="ta-r">Lot</th>
                  <th className="ta-r">Harga Entry</th><th className="ta-r">Harga Sekarang</th>
                  <th className="ta-r">SL / TP</th><th className="ta-r">Floating PnL</th><th />
                </tr>
              </thead>
              <tbody>
                {openRows.map((p) => {
                  const cfg = SYMBOLS[p.symbol] || { digits: 2 }
                  const buy = String(p.side).toLowerCase() === 'buy'
                  const now = quotes[p.symbol]?.price
                  const ms = p.opened_at ? new Date(p.opened_at).getTime() : null
                  return (
                    <tr key={p.id} className="dock-row">
                      <td className="tnum dock-dim">{fmtTime(ms)}</td>
                      <td className="dock-sym">{p.symbol}</td>
                      <td><span className={`dock-side ${buy ? 'is-buy' : 'is-sell'}`}>{buy ? 'BUY' : 'SELL'}</span></td>
                      <td className="ta-r tnum">{num(p.volume) != null ? Number(p.volume).toFixed(2) : '·'}</td>
                      <td className="ta-r tnum">{fmtPrice(p.entry, cfg.digits)}</td>
                      <td className="ta-r tnum">{fmtPrice(now, cfg.digits)}</td>
                      <td className="ta-r tnum dock-sl-tp">
                        <span className="down-text">{fmtPrice(p.sl, cfg.digits)}</span>
                        <span className="dock-sep">/</span>
                        <span className="up-text">{fmtPrice(p.tp, cfg.digits)}</span>
                      </td>
                      <td className="ta-r"><PnlCell pnl={p.pnl} equity={equity} /></td>
                      <td className="ta-r">
                        <button type="button" className="dock-act" onClick={() => close(p.id)}>Tutup</button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ))}

        {tab === 'pending' && (pendingRows.length === 0 ? (
          <div className="dock-empty">
            <strong>Tidak ada order pending</strong>
            <span>Order yang belum tereksekusi tampil di sini dengan garis amber di chart.</span>
          </div>
        ) : (
          <div className="dock-scroll">
            <table className="dock-table">
              <thead>
                <tr>
                  <th>Waktu</th><th>Simbol</th><th>Sisi</th><th className="ta-r">Lot</th>
                  <th className="ta-r">Harga Order</th><th className="ta-r">SL / TP</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {pendingRows.map((o) => {
                  const cfg = SYMBOLS[o.symbol] || { digits: 2 }
                  const buy = String(o.side).toLowerCase() === 'buy'
                  return (
                    <tr key={o.id} className="dock-row">
                      <td className="tnum dock-dim">{fmtTime(o.createdMs)}</td>
                      <td className="dock-sym">{o.symbol}</td>
                      <td><span className={`dock-side ${buy ? 'is-buy' : 'is-sell'}`}>{buy ? 'BUY' : 'SELL'}</span></td>
                      <td className="ta-r tnum">{num(o.volume) != null ? Number(o.volume).toFixed(2) : '·'}</td>
                      <td className="ta-r tnum">{fmtPrice(o.price_requested, cfg.digits)}</td>
                      <td className="ta-r tnum dock-sl-tp">
                        <span className="down-text">{fmtPrice(o.sl, cfg.digits)}</span>
                        <span className="dock-sep">/</span>
                        <span className="up-text">{fmtPrice(o.tp, cfg.digits)}</span>
                      </td>
                      <td><span className="dock-status">{o.status}</span></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ))}

        {tab === 'today' && (todayRows.length === 0 ? (
          <div className="dock-empty">
            <strong>Belum ada eksekusi hari ini</strong>
            <span>Order yang terisi sejak 00:00 WIB muncul di sini dan ditandai di chart.</span>
          </div>
        ) : (
          <div className="dock-scroll">
            <table className="dock-table">
              <thead>
                <tr>
                  <th>Waktu</th><th>Simbol</th><th>Sisi</th><th className="ta-r">Lot</th>
                  <th className="ta-r">Harga Isi</th><th className="ta-r">SL / TP</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {todayRows.map((o) => {
                  const cfg = SYMBOLS[o.symbol] || { digits: 2 }
                  const buy = String(o.side).toLowerCase() === 'buy'
                  return (
                    <tr key={o.id} className="dock-row">
                      <td className="tnum dock-dim">{fmtTime(o.createdMs)}</td>
                      <td className="dock-sym">{o.symbol}</td>
                      <td><span className={`dock-side ${buy ? 'is-buy' : 'is-sell'}`}>{buy ? 'BUY' : 'SELL'}</span></td>
                      <td className="ta-r tnum">{num(o.volume) != null ? Number(o.volume).toFixed(2) : '·'}</td>
                      <td className="ta-r tnum">{fmtPrice(o.fill ?? o.price_filled, cfg.digits)}</td>
                      <td className="ta-r tnum dock-sl-tp">
                        <span className="down-text">{fmtPrice(o.sl, cfg.digits)}</span>
                        <span className="dock-sep">/</span>
                        <span className="up-text">{fmtPrice(o.tp, cfg.digits)}</span>
                      </td>
                      <td><span className="dock-status is-filled">{o.status}</span></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ))}
      </div>
      <span className="dock-note">
        Baris dari /positions dan /orders · metrik dari /risk/portfolio · hari bursa 00:00 WIB
      </span>
    </section>
  )
}
