// Stream kesimpulan agent Lumine. Read-only: tidak ada input, tidak ada
// tombol aksi. Sumbernya /llm-agent/conclusions (keputusan akhir siklus),
// dipoll pelan supaya tidak menambah beban saat chart sedang sibuk.
import { useEffect, useRef, useState } from 'react'
import { DEMO, getAgentConclusions } from '../../lib/api'

const POLL_MS = 20000

const KIND_LABEL = {
  order: 'ORDER',
  hold: 'TAHAN',
  close: 'TUTUP',
  cut: 'CUT',
  sl: 'SL',
  be: 'BE',
  tp: 'TP',
}

function toneFor(item) {
  if (item.kind === 'order') return item.action === 'sell' ? 'is-down' : 'is-up'
  if (item.kind === 'close' || item.kind === 'cut') return 'is-down'
  if (item.kind === 'hold') return 'is-neutral'
  return 'is-up'
}

function labelFor(item) {
  if (item.kind === 'order') {
    return item.action === 'sell' ? 'JUAL' : 'BELI'
  }
  return KIND_LABEL[item.kind] || String(item.kind || '').toUpperCase()
}

function clock(iso) {
  if (!iso) return '·'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '·'
  return d.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' })
}

export default function AgentStream() {
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    if (DEMO) return () => { alive.current = false }
    const load = () => {
      getAgentConclusions(10)
        .then((body) => {
          if (!alive.current) return
          setData(body)
          setFailed(false)
        })
        .catch(() => {
          if (alive.current) setFailed(true)
        })
    }
    load()
    const t = setInterval(load, POLL_MS)
    return () => {
      alive.current = false
      clearInterval(t)
    }
  }, [])

  const items = data?.items || []
  const paused = data?.pause?.active
  const lastAt = items[0]?.at

  let body
  if (DEMO) {
    body = <p className="as-empty">Mode demo tidak menampilkan stream agent.</p>
  } else if (failed && !data) {
    body = <p className="as-empty">Stream agent belum bisa dimuat.</p>
  } else if (!data) {
    body = <p className="as-empty">Menghubungkan ke agent…</p>
  } else if (!items.length) {
    body = <p className="as-empty">Belum ada kesimpulan. Agent menulis setelah siklus pertama.</p>
  } else {
    body = items.map((item, i) => (
      <article className="as-row" key={`${item.cycle_id || i}-${item.at || i}`}>
        <div className="as-meta">
          <span className="as-sym">{item.symbol ? item.symbol.replace('USD', '') : '·'}</span>
          <span className={`as-verdict ${toneFor(item)}`}>{labelFor(item)}</span>
          {item.confidence != null && (
            <span className="as-conf tnum">{Math.round(item.confidence * 100)}%</span>
          )}
          <time className="as-time tnum">{clock(item.at)}</time>
        </div>
        <p className="as-text">{item.summary || 'Tidak ada catatan alasan pada siklus ini.'}</p>
      </article>
    ))
  }

  return (
    <section className="card agent-stream" aria-label="Stream kesimpulan agent Lumine">
      <header className="as-head">
        <span className="as-title">
          <span className="as-spark" aria-hidden="true" />
          Agent Lumine
        </span>
        <span className={`as-live ${paused ? 'is-idle' : ''}`.trim()}>
          <i aria-hidden="true" />
          {paused ? 'Jeda' : 'Live'}
        </span>
      </header>
      <div className="as-body">{body}</div>
      <footer className="as-foot tnum">
        kesimpulan saja{lastAt ? ` · terakhir ${clock(lastAt)}` : ''}
        {data?.interval_s ? ` · tiap ${data.interval_s}s` : ''}
      </footer>
    </section>
  )
}
