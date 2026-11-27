// UI-D3b (PRD v2.2 §21.4, §10): panel degradation satu strategi.
// Sumber: GET /strategies/{id}/degradation -> {state:{status, indicators,
// last_evaluated_at, since,...}, events:[transisi append-only]}.
// Re-enable HANYA muncul bila status bukan NORMAL (PRD §10.3: eskalasi hanya
// naik, penurunan status hanya lewat approval owner + 2FA + review_note).
// ConfirmDialog tidak diubah: syarat review_note >=10 char diterapkan lewat
// kelas is-invalid pada textarea (CSS menonaktifkan tombol konfirmasi dialog
// via :has) + guard di onConfirm + validasi min_length di API.
import { useEffect, useState } from 'react'
import ConfirmDialog from './ConfirmDialog'
import { fetchDegradation, reEnableDegradation, toast } from '../lib/api'

const STATUS_LABEL = {
  NORMAL: 'NORMAL',
  WATCH: 'WATCH',
  DEGRADED: 'DEGRADED',
  HALTED: 'HALTED',
}

function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function fmtVal(v) {
  if (v == null || v === '') return '—'
  if (typeof v === 'number') {
    return Math.abs(v) >= 1000 ? v.toLocaleString('id-ID', { maximumFractionDigits: 2 }) : String(v)
  }
  return String(v)
}

const SEVERITY_LABEL = { 0: 'ok', 1: 'warn', 2: 'degraded', 3: 'halt' }

export default function DegradationPanel({ strategyId, onChanged }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [reOpen, setReOpen] = useState(false)
  const [reviewNote, setReviewNote] = useState('')
  const [busy, setBusy] = useState(false)

  function load() {
    fetchDegradation(strategyId)
      .then(setData)
      .catch((ex) => setErr(ex.message))
  }

  useEffect(() => {
    setData(null)
    setErr('')
    setReviewNote('')
    setReOpen(false)
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategyId])

  const state = data?.state || {}
  const status = state.status || 'NORMAL'
  const indicators = Array.isArray(state.indicators) ? state.indicators : []
  const events = Array.isArray(data?.events) ? data.events : []
  const canReEnable = status !== 'NORMAL'
  const noteOk = reviewNote.trim().length >= 10

  function reEnable() {
    // Guard: tanpa review_note valid, aksi tidak pernah dipanggil
    // (API juga memvalidasi min_length=10).
    if (!noteOk) return
    setBusy(true)
    reEnableDegradation(strategyId, reviewNote.trim())
      .then(() => {
        setReOpen(false)
        setReviewNote('')
        toast('Re-enable berhasil', `${strategyId} kembali NORMAL — catatan review tersimpan di event log`, 'up')
        load()
        onChanged?.()
      })
      .catch((ex) => toast('Re-enable gagal', ex.message, 'down'))
      .finally(() => setBusy(false))
  }

  if (err) return <p className="degradation-error" role="alert">{err}</p>
  if (!data) return <p className="eventline-loading">Memuat status degradasi…</p>

  return (
    <div className="degradation">
      <div className="degradation-head">
        <span className={`degradation-badge degradation-${status}`} title={`Status degradation: ${STATUS_LABEL[status] || status}`}>
          <i aria-hidden="true" />
          {STATUS_LABEL[status] || status}
        </span>
        <span className="text-faint">
          Sejak {fmtTime(state.since)} · evaluasi terakhir {fmtTime(state.last_evaluated_at)}
          {state.cooldown_until ? ` · cooldown sampai ${fmtTime(state.cooldown_until)}` : ''}
        </span>
        {canReEnable && (
          <button type="button" className="btn btn-sm degradation-reenable-btn" onClick={() => setReOpen(true)}>
            Re-enable
          </button>
        )}
      </div>

      <h4 className="degradation-subtitle">Indikator terakhir</h4>
      {indicators.length === 0 ? (
        <p className="text-faint">Belum ada indikator terevaluasi.</p>
      ) : (
        <table className="ops-table" aria-label="Indikator degradation">
          <thead>
            <tr>
              <th>Indikator</th>
              <th>Nilai</th>
              <th>Ambang</th>
              <th>Sampel</th>
              <th>Status</th>
              <th>Catatan</th>
            </tr>
          </thead>
          <tbody>
            {indicators.map((ind) => (
              <tr key={ind.name} className={ind.severity > 0 && ind.sample_ok ? `degradation-row-sev${ind.severity}` : ''}>
                <td className="num">{ind.name}</td>
                <td className="num">{fmtVal(ind.value)}</td>
                <td className="num">{fmtVal(ind.threshold)}</td>
                <td className="num" title={ind.sample_ok ? 'sampel cukup' : 'sampel kurang: indikator nonaktif (PRD §10.4)'}>
                  {ind.sample_size ?? 0}{ind.sample_ok ? '' : '*'}
                </td>
                <td>
                  <span className={`chip degradation-sev degradation-sev-${ind.severity ?? 0}`}>
                    {SEVERITY_LABEL[ind.severity] || 'ok'}{ind.sample_ok === false ? ' · nonaktif' : ''}
                  </span>
                </td>
                <td className="degradation-reason" title={ind.reason || ''}>{ind.reason || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h4 className="degradation-subtitle">Event transisi</h4>
      {events.length === 0 ? (
        <p className="text-faint">Belum ada transisi status (append-only, PRD §10).</p>
      ) : (
        <ul className="degradation-events">
          {events.map((e, i) => (
            <li key={i} className="degradation-event">
              <span className="num degradation-event-time">{fmtTime(e.created_at)}</span>
              <span className="num">{e.from_status || '—'} → {e.to_status}</span>
              <span className="text-faint">{e.trigger}{e.actor ? ` · ${e.actor}` : ''}</span>
              <span className="degradation-event-reason" title={e.reason || ''}>{e.reason}</span>
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={reOpen}
        title={`Re-enable strategi · ${strategyId}`}
        description="Re-enable menurunkan status degradation kembali ke NORMAL. Ini keputusan owner: tidak pernah otomatis (PRD §10.3)."
        consequences={[
          'Strategi akan aktif kembali untuk entry baru sesuai mode (paper/live) yang berjalan',
          'Indikator degradation terus dievaluasi; eskalasi berikutnya tetap mungkin terjadi',
          'Catatan review wajib tersimpan append-only di degradation_events',
        ]}
        ackLabel="Saya paham strategi ini akan aktif kembali untuk entry baru"
        requires2fa
        confirmLabel="Re-enable ke NORMAL"
        busy={busy}
        onCancel={() => { if (!busy) setReOpen(false) }}
        onConfirm={reEnable}
      >
        <label className="degradation-note-field">
          <span>Catatan review (wajib, min. 10 karakter)</span>
          <textarea
            className={`input degradation-note ${noteOk ? '' : 'degradation-note-invalid'}`}
            rows={3}
            maxLength={500}
            placeholder="Jelaskan hasil review dan alasan re-enable…"
            value={reviewNote}
            onChange={(e) => setReviewNote(e.target.value)}
            disabled={busy}
          />
          <span className="text-faint">
            {reviewNote.trim().length}/10 karakter minimum ({reviewNote.length}/500)
          </span>
        </label>
      </ConfirmDialog>
    </div>
  )
}
