// Kartu performa per strategi. Semua angka dibaca dari ringkasan strategi
// yang sudah dipakai halaman Strategy Lab; tidak ada metrik yang dihitung
// ulang atau dikarang. Strategi tanpa trade ditandai "belum ada trade" agar
// nol tidak terbaca sebagai hasil.
import { useState } from 'react'
import { DebugOnly } from '../../lib/debug'
import { dec, money, pct, signedPct } from './format'

const MODE_LABEL = { paper: 'Paper', live: 'Live', off: 'Nonaktif' }
const MODE_TONE = { paper: 'is-paper', live: 'is-live', off: 'is-idle' }
const TRACK_LABEL = { A: 'Rule-based', B: 'Machine learning', C: 'Reinforcement learning' }

function equityOf(strategy) {
  const mini = Array.isArray(strategy.equity_mini) ? strategy.equity_mini : []
  const lastMini = mini.length ? mini[mini.length - 1]?.v : null
  if (lastMini != null) return lastMini
  const curve = Array.isArray(strategy.curve) ? strategy.curve : []
  if (curve.length) return curve[curve.length - 1]
  return strategy.pnl?.balance ?? strategy.balance ?? null
}

export default function StrategyCards({ strategies, loaded, onReload }) {
  const [busy, setBusy] = useState(false)
  const list = strategies || []

  const reload = () => {
    setBusy(true)
    Promise.resolve(onReload?.()).finally(() => setBusy(false))
  }

  let body
  if (!loaded) {
    body = <p className="agx-empty">Memuat strategi…</p>
  } else if (list.length === 0) {
    body = <p className="agx-empty">Belum ada strategi terdaftar.</p>
  } else {
    body = (
      <div className="agx-strategies">
        {list.map((strategy) => (
          <StrategyCard key={strategy.id} strategy={strategy} />
        ))}
      </div>
    )
  }

  return (
    <section className="agx-tab" aria-label="Strategi dan performa">
      <header className="agx-panel-head">
        <div>
          <h2 className="agx-h2">Strategi</h2>
          <p className="agx-hint">
            {list.length > 0
              ? `${list.length} strategi terdaftar · statistik sejak pencatatan paper dimulai`
              : 'Daftar strategi Lumine Fund'}
          </p>
        </div>
        <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={reload}>
          {busy ? 'Memuat…' : 'Muat ulang'}
        </button>
      </header>
      {body}
      <DebugOnly label="sumber">/strategies · statistik ledger paper · equity dari titik terakhir kurva</DebugOnly>
    </section>
  )
}

function StrategyCard({ strategy }) {
  const trades = Number(strategy.trades ?? 0)
  const noTrades = trades === 0
  const mode = String(strategy.mode || '').toLowerCase()
  const equity = equityOf(strategy)
  const returnPct = strategy.pnl?.return_pct
  const deltaTone = Number(returnPct) > 0 ? 'is-up' : Number(returnPct) < 0 ? 'is-down' : ''
  const paused = strategy.active === false

  return (
    <article className="agx-strategy">
      <header className="agx-strategy-head">
        <div className="agx-strategy-id">
          <h3 className="agx-strategy-name">{strategy.name || 'Strategi'}</h3>
          <p className="agx-hint">
            {[strategy.symbol, TRACK_LABEL[strategy.track]].filter(Boolean).join(' · ')}
          </p>
        </div>
        <div className="agx-strategy-chips">
          <span className={`agx-chip ${MODE_TONE[mode] || 'is-idle'}`}>{MODE_LABEL[mode] || '—'}</span>
          {paused && mode !== 'off' && <span className="agx-chip is-warn">Dijeda</span>}
        </div>
      </header>

      <div className="agx-equity">
        <span className="agx-label">Equity</span>
        <div className="agx-equity-line">
          <span className="agx-equity-value num">{money(equity)}</span>
          {returnPct != null && (
            <span className={`agx-equity-delta num ${deltaTone}`}>{signedPct(returnPct)}</span>
          )}
        </div>
      </div>

      <dl className="agx-metrics">
        <div>
          <dt>Winrate</dt>
          <dd className="num">{noTrades ? '—' : pct(strategy.win)}</dd>
        </div>
        <div>
          <dt>Profit factor</dt>
          <dd className="num">{noTrades ? '—' : dec(strategy.pf)}</dd>
        </div>
        <div>
          <dt>Max drawdown</dt>
          <dd className="num">{noTrades ? '—' : pct(strategy.dd)}</dd>
        </div>
        <div>
          <dt>Sharpe</dt>
          <dd className="num">{noTrades ? '—' : dec(strategy.sharpe)}</dd>
        </div>
      </dl>

      <footer className="agx-strategy-foot">
        <span>{noTrades ? 'Belum ada trade' : `${trades.toLocaleString('id-ID')} trade tertutup`}</span>
        {strategy.pnl?.open_trades != null && (
          <span>{Number(strategy.pnl.open_trades).toLocaleString('id-ID')} posisi terbuka</span>
        )}
      </footer>
      <DebugOnly label="detail">
        {strategy.id} · pause_reasons: {(strategy.pause_reasons || []).join(', ') || 'tidak ada'}
      </DebugOnly>
    </article>
  )
}
