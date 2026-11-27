// Sub-tab 2: Event Kill-Switch.
// Kartu timeline berbahasa operasional: waktu, level (lunak/keras), pemicu,
// aksi yang dijalankan, dan status pemulihan. Data: GET /kill-switch (state +
// 20 event terakhir) yang sudah dimuat lapisan API.
import { useMemo } from 'react'
import {
  MODE_LABEL,
  actionLabel,
  cleanEventText,
  decorateKillEvents,
  levelInfo,
  recoveryText,
  sourceText,
} from './labels'
import { formatStamp, toMs } from './reasons'

function eventLevel(event) {
  const fromMode = levelInfo(event.mode)
  if (fromMode) return fromMode
  if (event.action === 'AGENT_PAUSE') return { key: 'soft', label: 'Lunak' }
  if (event.action === 'FLATTEN_REQUEST') return { key: 'hard', label: 'Keras' }
  return null
}

export default function KillSwitchPanel({ killSwitch }) {
  const state = killSwitch?.state ?? null
  const events = useMemo(() => decorateKillEvents(killSwitch?.events), [killSwitch?.events])
  const active = Boolean(state?.active)
  const level = active ? levelInfo(state?.mode) : null
  const paused = Array.isArray(killSwitch?.paused_strategies) ? killSwitch.paused_strategies : []
  const since = toMs(state?.activated_at)

  return (
    <section className="lh-panel" aria-label="Event kill-switch">
      <div className="lh-panel-head">
        <div className="lh-panel-title">
          <h2>Event kill-switch</h2>
          <p>Riwayat aktivasi, eskalasi, dan pelepasan penghenti darurat. Terbaru di atas.</p>
        </div>
      </div>

      <div className={`lh-ks-state ${active ? 'is-on' : 'is-off'}`}>
        <span className="lh-ks-dot" aria-hidden="true" />
        <div className="lh-ks-state-main">
          <p className="lh-ks-state-title">{active ? 'Kill-switch aktif' : 'Kill-switch tidak aktif'}</p>
          <p className="lh-ks-state-sub">
            {active
              ? `${MODE_LABEL[state?.mode] ?? 'Penghentian aktif'}${since ? ` · sejak ${formatStamp(since)}` : ''}`
              : 'Order baru berjalan normal melalui risk gate.'}
          </p>
          {active && state?.reason && <p className="lh-ks-state-reason">{cleanEventText(state.reason)}</p>}
          {paused.length > 0 && (
            <p className="lh-ks-state-paused">
              Strategi dijeda:
              {paused.map((name) => <span key={name} className="lh-chip">{name}</span>)}
            </p>
          )}
        </div>
        {level && <span className={`lh-level is-${level.key}`}>{level.label}</span>}
      </div>

      <p className="lh-legend">
        <strong>Lunak</strong> berarti order baru ditolak atau strategi dijeda. <strong>Keras</strong> berarti semua entry berhenti dan posisi bisa ikut ditutup.
      </p>

      {events.length === 0 ? (
        <p className="lh-empty">Belum ada kejadian kill-switch yang tercatat.</p>
      ) : (
        <ol className="lh-ks-timeline">
          {events.map((event) => {
            const eventLevelInfo = eventLevel(event)
            const recovery = recoveryText(event)
            const mode = event.mode ? MODE_LABEL[event.mode] ?? null : null
            return (
              <li key={event._key} className={`lh-ks-card is-${eventLevelInfo?.key ?? 'note'}`}>
                <div className="lh-ks-card-top">
                  <time className="lh-ks-time num" dateTime={event.created_at ?? undefined}>{formatStamp(event._ms)}</time>
                  {eventLevelInfo && <span className={`lh-level is-${eventLevelInfo.key}`}>{eventLevelInfo.label}</span>}
                </div>
                <p className="lh-ks-action">
                  {actionLabel(event.action)}
                  {mode ? <span className="lh-ks-action-dim"> · {mode}</span> : null}
                  {event.strategy ? <span className="lh-ks-action-dim"> · {event.strategy}</span> : null}
                </p>
                <dl className="lh-ks-meta">
                  <div>
                    <dt>Pemicu</dt>
                    <dd>{sourceText(event.source)}{event.actor && event.actor !== 'auto' ? ` · ${event.actor}` : ''}</dd>
                  </div>
                  <div>
                    <dt>Status pemulihan</dt>
                    <dd className={`lh-tone-${recovery.tone}`}>{recovery.label} · {recovery.detail}</dd>
                  </div>
                </dl>
                {event.reason && <p className="lh-ks-reason">{cleanEventText(event.reason)}</p>}
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
