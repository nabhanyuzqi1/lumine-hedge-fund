// Interval siklus agent: tampilkan nilai aktif, dan (untuk owner) ubah lewat
// kanal konfirmasi yang sama dengan setelan agent lain: password ulang + kode
// 2FA. Setelah simpan, nilai efektif dibaca ulang dari server supaya UI tidak
// pernah menampilkan angka yang tidak benar-benar dipakai.
import { useState } from 'react'
import { getAgentConfig, updateRiskSettings } from '../../lib/api'
import ConfirmDialog from '../ConfirmDialog'
import { DebugOnly } from '../../lib/debug'
import { intervalLabel } from './format'

const UNITS = [
  { id: 's', label: 'detik', mult: 1 },
  { id: 'm', label: 'menit', mult: 60 },
  { id: 'h', label: 'jam', mult: 3600 },
  { id: 'd', label: 'hari', mult: 86400 },
]

const DEFAULT_RANGE = { min: 30, max: 86400 }

function splitInterval(seconds) {
  const value = Number(seconds)
  if (!Number.isFinite(value) || value <= 0) return { value: '', unit: 'm' }
  for (const unit of [UNITS[3], UNITS[2], UNITS[1]]) {
    if (value % unit.mult === 0) return { value: String(value / unit.mult), unit: unit.id }
  }
  return { value: String(Math.round(value)), unit: 's' }
}

export default function CycleCard({ interval, range, isAdmin, onSaved }) {
  const bounds = range && range.min && range.max ? range : DEFAULT_RANGE

  return (
    <section className="agx-panel" aria-label="Interval siklus agent">
      <header className="agx-panel-head">
        <div>
          <h2 className="agx-h2">Interval siklus</h2>
          <p className="agx-hint">Jarak antar siklus analisa agent.</p>
        </div>
      </header>

      <div className="agx-current">
        <span className="agx-label">Aktif sekarang</span>
        <span className="agx-current-value num">{interval != null ? intervalLabel(interval) : '—'}</span>
      </div>

      {isAdmin ? (
        <IntervalForm
          key={interval == null ? 'none' : String(interval)}
          interval={interval}
          bounds={bounds}
          onSaved={onSaved}
        />
      ) : (
        <p className="agx-hint">Hanya owner yang dapat mengubah interval siklus.</p>
      )}
      <DebugOnly label="sumber">/llm-agent/config · PUT /admin/risk-settings (llm_interval_s)</DebugOnly>
    </section>
  )
}

function IntervalForm({ interval, bounds, onSaved }) {
  const start = splitInterval(interval)
  const [draft, setDraft] = useState(start.value)
  const [unit, setUnit] = useState(start.unit)
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState(null)

  const mult = UNITS.find((u) => u.id === unit)?.mult || 1
  const parsed = Number(String(draft).replace(',', '.'))
  const seconds = Number.isFinite(parsed) && parsed > 0 ? Math.round(parsed * mult) : null
  const outOfRange = seconds != null && (seconds < bounds.min || seconds > bounds.max)
  const unchanged = seconds != null && interval != null && Math.abs(seconds - Number(interval)) < 1
  const canOpen = seconds != null && !outOfRange && !unchanged

  const openDialog = () => {
    if (!canOpen) return
    setPassword('')
    setNote(null)
    setOpen(true)
  }

  const commit = async () => {
    if (!canOpen) return
    setBusy(true)
    setNote(null)
    try {
      await updateRiskSettings({ password, llm_interval_s: seconds })
      let effective = null
      try {
        const cfg = await getAgentConfig()
        effective = cfg?.interval_s ?? null
      } catch {
        effective = null
      }
      if (effective != null && Math.round(Number(effective)) !== seconds) {
        setNote({
          kind: 'warn',
          text: `Tersimpan, tetapi interval aktif masih ${intervalLabel(effective)}. Periksa pengaturan agent.`,
        })
      } else {
        setNote({ kind: 'ok', text: `Interval siklus kini ${intervalLabel(seconds)}.` })
      }
      setOpen(false)
      onSaved?.()
    } catch (ex) {
      setNote({ kind: 'down', text: ex?.message || 'Gagal menyimpan interval.' })
      setOpen(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="agx-inline">
        <label className="agx-field agx-grow">
          <span className="agx-label">Ubah ke</span>
          <input
            className="agx-input num"
            inputMode="decimal"
            value={draft}
            aria-label="Interval siklus baru"
            onChange={(e) => setDraft(e.target.value.replace(/[^0-9.,]/g, ''))}
          />
        </label>
        <label className="agx-field agx-unit">
          <span className="agx-label">Satuan</span>
          <select
            className="agx-select"
            value={unit}
            aria-label="Satuan interval"
            onChange={(e) => setUnit(e.target.value)}
          >
            {UNITS.map((u) => (
              <option key={u.id} value={u.id}>{u.label}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="btn btn-sm agx-inline-btn"
          disabled={!canOpen}
          onClick={openDialog}
        >
          Simpan
        </button>
      </div>

      <p className="agx-hint">
        {outOfRange
          ? `Nilai harus antara ${intervalLabel(bounds.min)} dan ${intervalLabel(bounds.max)}.`
          : 'Perubahan butuh password akun dan kode 2FA.'}
      </p>
      {note && <p className={`agx-note is-${note.kind === 'warn' ? 'warn' : note.kind}`} role="status">{note.text}</p>}

      <ConfirmDialog
        open={open}
        title="Ubah interval siklus"
        description={seconds != null ? `Siklus agent akan berjalan tiap ${intervalLabel(seconds)}.` : ''}
        consequences={[
          'Siklus berikutnya memakai interval baru',
          'Nilai lama tetap tercatat di riwayat perubahan',
          'Perubahan butuh kode 2FA yang masih berlaku',
        ]}
        ackLabel="Saya paham interval siklus agent akan berubah"
        requires2fa
        confirmLabel="Simpan interval"
        confirmDisabled={!password}
        busy={busy}
        onCancel={() => {
          if (!busy) setOpen(false)
        }}
        onConfirm={commit}
      >
        <label className="agx-field">
          <span className="agx-label">Password akun</span>
          <input
            className="agx-input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <span className="agx-hint">Password dan kode 2FA diverifikasi di server.</span>
        </label>
      </ConfirmDialog>
    </>
  )
}
