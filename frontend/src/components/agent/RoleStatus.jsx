// Status ringkas tiap peran agent: chip keadaan, model yang dipakai siklus
// terakhir, dan lamanya respons. Sumber: katalog model agent + evidence siklus
// terakhir. Tidak ada nama internal yang tampil; detail teknis di DebugOnly.
import { useEffect, useState } from 'react'
import { DEMO, getAgentModels } from '../../lib/api'
import { DebugOnly } from '../../lib/debug'
import { durationMs, relativeTime, useNow } from './format'

const POLL_MS = 30000

const SPECIALISTS = ['technical', 'macro', 'sentiment', 'portfolio']
const ROLE_LABEL = {
  technical: 'Technical',
  macro: 'Macro',
  sentiment: 'Sentiment',
  portfolio: 'Portfolio',
  synth: 'Synthesizer',
  fallback: 'Fallback',
}
const STATE_LABEL = {
  ok: { label: 'Aktif', tone: 'is-up' },
  error: { label: 'Gangguan', tone: 'is-down' },
  timeout: { label: 'Waktu habis', tone: 'is-warn' },
  running: { label: 'Berjalan', tone: 'is-up' },
  idle: { label: 'Idle', tone: 'is-idle' },
}

export default function RoleStatus() {
  const [models, setModels] = useState(null)
  const [failed, setFailed] = useState(false)
  const now = useNow(POLL_MS)

  useEffect(() => {
    if (DEMO) return undefined
    let alive = true
    const load = () => {
      getAgentModels()
        .then((body) => {
          if (!alive) return
          setModels(body)
          setFailed(false)
        })
        .catch(() => {
          if (alive) setFailed(true)
        })
    }
    load()
    const t = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  const last = models?.last_cycle || null
  const used = last?.roles || {}
  const keys = [...SPECIALISTS, ...Object.keys(used), 'synth'].filter(
    (key, index, arr) => ROLE_LABEL[key] && arr.indexOf(key) === index,
  )
  const cycleAt = last?.at ? Date.parse(last.at) : null

  let body
  if (DEMO) {
    body = <p className="agx-empty">Mode demo: status per peran hanya tersedia pada data nyata.</p>
  } else if (failed) {
    body = <p className="agx-empty">Status agent belum bisa dimuat. Coba muat ulang halaman.</p>
  } else if (!models) {
    body = <p className="agx-empty">Memuat status agent…</p>
  } else {
    body = (
      <div className="agx-roles">
        {keys.map((key) => {
          const row = used[key] || null
          const state = STATE_LABEL[row?.state] || STATE_LABEL.idle
          return (
            <div className="agx-role" key={key}>
              <div className="agx-role-head">
                <span className="agx-role-name">{ROLE_LABEL[key]}</span>
                <span className={`agx-chip ${state.tone}`}>{state.label}</span>
              </div>
              <span className="agx-role-model num" title={row?.model || undefined}>{row?.model || '—'}</span>
              <span className="agx-role-meta">
                {row?.latency_ms != null
                  ? `respons ${durationMs(row.latency_ms)}`
                  : last
                    ? 'tanpa catatan peran ini'
                    : 'menunggu siklus pertama'}
              </span>
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <section className="agx-panel" aria-label="Status agent per peran">
      <header className="agx-panel-head">
        <div>
          <h2 className="agx-h2">Status agent</h2>
          <p className="agx-hint">
            {cycleAt
              ? `Siklus terakhir ${relativeTime(cycleAt, now)}${last?.symbol ? ` · ${last.symbol}` : ''}`
              : 'Belum ada siklus yang tercatat.'}
          </p>
        </div>
      </header>
      {body}
      <DebugOnly label="sumber">/llm-agent/models · evidence AGENT_EVIDENCE siklus terakhir</DebugOnly>
    </section>
  )
}
