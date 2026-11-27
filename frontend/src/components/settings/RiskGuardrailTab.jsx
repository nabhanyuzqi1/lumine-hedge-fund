// Sub-tab 1 · Batas Risiko & Guardrail.
// Satu tempat: nilai AKTIF tampil di samping tiap kolom, form di kanan, dan
// simpan selalu lewat dialog konfirmasi + password ulang + kode 2FA. Tidak ada
// panel baca-saja terpisah dari form ubahnya.
import { useCallback, useEffect, useMemo, useState } from 'react'
import ConfirmDialog from '../ConfirmDialog'
import { DebugOnly } from '../../lib/debug'
import {
  DEMO,
  fetchGuardrailSettings,
  fetchKillSwitchStatus,
  fetchSettingsAudit,
  toast,
  updateRiskSettings,
} from '../../lib/api'
import { ActiveChip, EmptyLine, HubCard, LockedNote, MetaRow, StatusPill, Switch } from './ui'
import { fmtNum, fmtRange, fmtTime, fmtValue, parseDraft } from './format'

// Empat guardrail inti + dua batas yang ditegakkan di jalur agent. Sumber tiap
// angka berbeda di server, tetapi operator melihatnya sebagai satu daftar.
const FIELDS = [
  {
    key: 'max_volume',
    source: 'core',
    label: 'Volume maksimum per order',
    unit: 'lot',
    digits: 2,
    hint: 'Batas lot untuk satu order.',
  },
  {
    key: 'max_orders_per_min',
    source: 'core',
    label: 'Order maksimum per menit',
    unit: 'order/menit',
    digits: 0,
    integer: true,
    hint: 'Dihitung per akun, termasuk order dari agent.',
  },
  {
    key: 'max_orders_per_day',
    source: 'llm',
    label: 'Order maksimum per hari',
    unit: 'order/hari',
    digits: 0,
    integer: true,
    hint: 'Batas order harian untuk agent otomatis.',
  },
  {
    key: 'daily_drawdown_pct',
    source: 'trigger',
    label: 'Batas rugi harian',
    unit: '% equity',
    digits: 1,
    hint: 'Rugi terhadap equity awal hari; memicu penghentian otomatis.',
  },
  {
    key: 'max_spread',
    source: 'core',
    label: 'Spread maksimum',
    unit: 'poin',
    digits: 2,
    hint: 'Order ditolak bila spread melebar melewati angka ini.',
  },
]

const MODE_LABEL = {
  GLOBAL_HALT: 'Hentikan semua entry',
  STOP_NEW_ORDERS: 'Hentikan entry baru saja',
}

const AUDIT_LABEL = {
  ...Object.fromEntries(FIELDS.map((f) => [f.key, f.label])),
  kill_switch_triggers: 'Penghentian otomatis',
  llm_risk: 'Batas order agent',
}

const DEMO_DATA = {
  values: { max_volume: 0.05, max_orders_per_min: 5, max_spread: 0.5, max_daily_drawdown: 292.02 },
  ranges: {
    max_volume: { min: 0.01, max: 100 },
    max_orders_per_min: { min: 1, max: 600 },
    max_spread: { min: 0.0001, max: 1000000 },
    max_daily_drawdown: { min: 1, max: 1000000000 },
  },
  triggers: { daily_drawdown_pct: 3, check_interval_seconds: 5 },
  trigger_ranges: { daily_drawdown_pct: { min: 0.1, max: 50 } },
  trigger_modes: { daily_drawdown: 'GLOBAL_HALT' },
  llm: {
    risk: { max_orders_per_day: 20 },
    risk_ranges: { max_orders_per_day: { min: 1, max: 2000 } },
  },
}

function emptyDrafts() {
  return Object.fromEntries(FIELDS.map((f) => [f.key, '']))
}

export default function RiskGuardrailTab() {
  const [data, setData] = useState(() => (DEMO ? DEMO_DATA : null))
  const [audit, setAudit] = useState([])
  const [loading, setLoading] = useState(!DEMO)
  const [loadErr, setLoadErr] = useState('')
  const [draft, setDraft] = useState(emptyDrafts)
  const [modeDraft, setModeDraft] = useState(null)
  const [dlgOpen, setDlgOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [lastSaved, setLastSaved] = useState(null)

  const load = useCallback(async () => {
    if (DEMO) return
    setLoadErr('')
    try {
      const [body, ks, auditBody] = await Promise.all([
        fetchGuardrailSettings(),
        fetchKillSwitchStatus(),
        fetchSettingsAudit(20).catch(() => ({ rows: [] })),
      ])
      setData({
        ...body,
        triggers: { ...(ks?.triggers || {}), ...(body?.triggers || {}) },
        trigger_modes: { ...(ks?.triggers?.modes || {}), ...(body?.trigger_modes || {}) },
      })
      setAudit(Array.isArray(auditBody?.rows) ? auditBody.rows : [])
      setDraft(emptyDrafts())
      setModeDraft(null)
    } catch (ex) {
      setLoadErr(
        ex.code === 'FORBIDDEN'
          ? 'Batas risiko hanya bisa dibuka oleh admin.'
          : 'Nilai batas risiko belum bisa dimuat.',
      )
    } finally {
      setLoading(false)
    }
  }, [])

  // Defer satu microtask supaya pemuatan awal tidak memicu cascading render.
  useEffect(() => { Promise.resolve().then(load) }, [load])

  const currentMode = data?.trigger_modes?.daily_drawdown || 'GLOBAL_HALT'
  const modeChanged = modeDraft != null && modeDraft !== currentMode

  // Perubahan = hanya field yang berbeda dari nilai aktif. Field kosong
  // diabaikan, jadi simpan selalu parsial dan tidak pernah mereset nilai lain.
  const { changes, errors } = useMemo(() => {
    const ch = {}
    const er = {}
    for (const f of FIELDS) {
      const parsed = parseDraft(draft[f.key])
      if (parsed == null) continue
      if (Number.isNaN(parsed)) { er[f.key] = 'Harus berupa angka'; continue }
      if (f.integer && !Number.isInteger(parsed)) { er[f.key] = 'Harus bilangan bulat'; continue }
      if (parsed <= 0) { er[f.key] = 'Harus lebih dari 0'; continue }
      let range = null
      let active = null
      if (f.source === 'core') {
        range = data?.ranges?.[f.key]
        active = data?.values?.[f.key]
      } else if (f.source === 'trigger') {
        range = data?.trigger_ranges?.[f.key]
        active = data?.triggers?.[f.key]
      } else {
        range = data?.llm?.risk_ranges?.[f.key]
        active = data?.llm?.risk?.[f.key]
      }
      if (range && (parsed < range.min || parsed > range.max)) {
        er[f.key] = `Harus di antara ${fmtRange(range.min, range.max)}`
        continue
      }
      const cur = Number(active)
      const same = Number.isFinite(cur) && Math.abs(cur - parsed) < 1e-9
      if (!same) ch[f.key] = { field: f, old: Number.isFinite(cur) ? cur : null, new: parsed }
    }
    return { changes: ch, errors: er }
  }, [draft, data])

  const changeCount = Object.keys(changes).length
  const hasError = Object.keys(errors).length > 0
  const dirty = changeCount > 0 || modeChanged

  const diffRows = useMemo(() => {
    const rows = Object.values(changes).map((v) => ({
      key: v.field.key,
      label: v.field.label,
      old: fmtValue(v.old, v.field.unit, v.field.digits),
      next: fmtValue(v.new, v.field.unit, v.field.digits),
    }))
    if (modeChanged) {
      rows.push({
        key: 'mode',
        label: 'Aksi saat batas rugi tersentuh',
        old: MODE_LABEL[currentMode] || '·',
        next: MODE_LABEL[modeDraft] || '·',
      })
    }
    return rows
  }, [changes, modeChanged, currentMode, modeDraft])

  function resetDraft() {
    setDraft(emptyDrafts())
    setModeDraft(null)
  }

  function openDialog() {
    if (!dirty || hasError) return
    setPassword('')
    setDlgOpen(true)
  }

  async function onConfirm() {
    const payload = { password: password.trim() }
    const triggerPatch = {}
    const llmPatch = {}
    for (const [key, v] of Object.entries(changes)) {
      if (v.field.source === 'core') payload[key] = v.new
      else if (v.field.source === 'trigger') triggerPatch[key] = v.new
      else llmPatch[key] = v.new
    }
    if (modeChanged) triggerPatch.modes = { daily_drawdown: modeDraft }
    if (Object.keys(triggerPatch).length) payload.kill_switch_triggers = triggerPatch
    if (Object.keys(llmPatch).length) payload.llm_risk = llmPatch

    try {
      await updateRiskSettings(payload)
    } catch (ex) {
      const raw = ex.message || ''
      throw new Error(
        /password/i.test(raw)
          ? 'Password akun salah. Tidak ada nilai yang berubah.'
          : 'Nilai ditolak. Periksa rentang tiap kolom lalu coba lagi.',
      )
    }
    toast('Batas risiko tersimpan', 'Nilai baru dipakai untuk order dan monitor berikutnya')
    setLastSaved(new Date().toISOString())
    setDlgOpen(false)
    setPassword('')
    await load()
  }

  if (loading) return <p className="sh-empty">Memuat batas risiko…</p>

  if (loadErr) {
    return (
      <HubCard title="Batas risiko" badge={<StatusPill tone="is-down">TIDAK TERSEDIA</StatusPill>}>
        <EmptyLine>{loadErr}</EmptyLine>
        {!DEMO && (
          <button type="button" className="btn sh-btn" onClick={() => { setLoading(true); load() }}>
            Muat ulang
          </button>
        )}
      </HubCard>
    )
  }

  return (
    <div className="sh-grid sh-grid-main">
      <HubCard
        title="Nilai aktif dan nilai baru"
        badge={(
          <StatusPill tone={dirty ? 'is-warn' : ''}>
            {dirty ? `${diffRows.length} perubahan belum disimpan` : 'SESUAI NILAI AKTIF'}
          </StatusPill>
        )}
        note="Isi kolom hanya untuk nilai yang ingin diubah. Kolom kosong berarti nilai aktif dipertahankan."
      >
        <div className="sh-fields">
          {FIELDS.map((f) => {
            const changed = changes[f.key]
            const err = errors[f.key]
            let active = null
            let range = null
            if (f.source === 'core') {
              active = data?.values?.[f.key]
              range = data?.ranges?.[f.key]
            } else if (f.source === 'trigger') {
              active = data?.triggers?.[f.key]
              range = data?.trigger_ranges?.[f.key]
            } else {
              active = data?.llm?.risk?.[f.key]
              range = data?.llm?.risk_ranges?.[f.key]
            }
            return (
              <div className="sh-field" key={f.key}>
                <div className="sh-field-main">
                  <div className="sh-field-top">
                    <span className="sh-field-label">{f.label}</span>
                    <ActiveChip>{fmtValue(active, f.unit, f.digits)}</ActiveChip>
                    {changed && (
                      <span className="sh-delta">→ {fmtValue(changed.new, f.unit, f.digits)}</span>
                    )}
                  </div>
                  <span className="sh-field-hint">
                    {f.hint}
                    {range && ` Rentang wajar ${fmtRange(range.min, range.max)}.`}
                    {f.key === 'max_volume' && data?.effective_max_volume && (
                      ` Topi efektif per simbol: ${Object.entries(data.effective_max_volume)
                        .map(([sym, cap]) => `${sym} ${cap == null ? '·' : fmtNum(cap, 2)}`)
                        .join(' · ')} (gate menegakkan min(topi akun, vol_max_lot simbol)).`
                    )}
                    {f.key === 'max_orders_per_day' && (
                      ' Hanya membatasi order agent LLM, bukan order manual.'
                    )}
                  </span>
                  {err && <span className="sh-field-err">{err}</span>}
                </div>
                <div className="sh-ctl">
                  <input
                    className={`sh-input ${err ? 'is-error' : ''}`.trim()}
                    inputMode="decimal"
                    aria-label={`Nilai baru ${f.label}`}
                    placeholder={fmtNum(active, f.digits)}
                    value={draft[f.key] ?? ''}
                    onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                  />
                  <span className="sh-unit">{f.unit}</span>
                </div>
              </div>
            )
          })}
        </div>

        {hasError && <p className="sh-field-err">Perbaiki nilai yang ditandai sebelum menyimpan.</p>}

        <div className="sh-actions">
          <button
            type="button"
            className="btn btn-primary sh-btn"
            disabled={!dirty || hasError || DEMO}
            onClick={openDialog}
          >
            {dirty ? `Simpan ${diffRows.length} perubahan` : 'Tidak ada perubahan'}
          </button>
          {dirty && (
            <button type="button" className="btn sh-btn" onClick={resetDraft} disabled={DEMO}>
              Batalkan
            </button>
          )}
          {lastSaved && <span className="sh-saved">tersimpan {fmtTime(lastSaved)}</span>}
        </div>
        {DEMO && <LockedNote>Mode demo: penyimpanan dinonaktifkan, angka di atas hanya contoh.</LockedNote>}
      </HubCard>

      <HubCard
        title="Penghentian otomatis"
        badge={<StatusPill tone={currentMode === 'GLOBAL_HALT' ? 'is-warn' : ''}>{MODE_LABEL[currentMode]}</StatusPill>}
        note="Pemantau otomatis berjalan terus. Saklar ini menentukan seberapa luas penghentian saat batas rugi harian tersentuh."
      >
        <div className="sh-switch-row">
          <div className="sh-field-main">
            <span className="sh-field-label">Hentikan semua entry saat batas rugi tersentuh</span>
            <span className="sh-field-hint">
              {modeChanged
                ? `Draf: ${MODE_LABEL[modeDraft]}. Simpan untuk menerapkan.`
                : 'ON memblokir semua entry. OFF hanya memblokir entry baru dan membiarkan posisi berjalan.'}
            </span>
          </div>
          <Switch
            label="Hentikan semua entry saat batas rugi tersentuh"
            checked={(modeDraft || currentMode) === 'GLOBAL_HALT'}
            disabled={DEMO}
            onChange={(next) => setModeDraft(next ? 'GLOBAL_HALT' : 'STOP_NEW_ORDERS')}
          />
        </div>

        <div className="sh-meta-list">
          <MetaRow
            label="Pemantau berjalan setiap"
            value={data?.triggers?.check_interval_seconds != null
              ? `${fmtNum(data.triggers.check_interval_seconds, 0)} detik`
              : '·'}
          />
          <MetaRow label="Ambang rugi harian" value={fmtValue(data?.triggers?.daily_drawdown_pct, '% equity', 1)} />
        </div>

        <div className="sh-actions">
          <button
            type="button"
            className="btn btn-primary sh-btn"
            disabled={!modeChanged || hasError || DEMO}
            onClick={openDialog}
          >
            {modeChanged ? 'Simpan penghentian otomatis' : 'Tidak ada perubahan'}
          </button>
          {modeChanged && (
            <button type="button" className="btn sh-btn" onClick={resetDraft} disabled={DEMO}>
              Batalkan
            </button>
          )}
        </div>
      </HubCard>

      <HubCard
        title="Riwayat perubahan terakhir"
        badge={<StatusPill>{audit.length ? `${Math.min(audit.length, 5)} baris` : 'BELUM ADA'}</StatusPill>}
      >
        {audit.length === 0 ? (
          <EmptyLine>Belum ada perubahan batas risiko yang tercatat.</EmptyLine>
        ) : (
          <ul className="sh-history">
            {audit.slice(0, 5).map((row) => {
              const label = AUDIT_LABEL[row.key] || 'Nilai konfigurasi'
              const asText = (v) => (v && typeof v === 'object' ? 'beberapa nilai sekaligus' : fmtNum(v, 2))
              return (
                <li key={row.id || `${row.key}-${row.changed_at}`}>
                  <span className="sh-history-time">{fmtTime(row.changed_at)}</span>
                  <span className="sh-history-main">
                    <strong>{label}</strong>
                    <span className="sh-history-flow">
                      {asText(row.old_value)} → {asText(row.new_value)}
                    </span>
                  </span>
                  <span className="sh-history-actor">{row.changed_by || '·'}</span>
                </li>
              )
            })}
          </ul>
        )}
        <DebugOnly label="riwayat konfigurasi">{JSON.stringify(audit.slice(0, 2))}</DebugOnly>
      </HubCard>

      <ConfirmDialog
        open={dlgOpen}
        title="Simpan batas risiko"
        description="Periksa nilai lama dan nilai baru. Simpan hanya jika angka ini yang dimaksud."
        consequences={[
          'Nilai baru langsung dipakai risk gate untuk order berikutnya',
          'Perubahan tercatat permanen di riwayat audit dan tidak bisa dihapus',
          'Password akun dan kode 2FA diverifikasi server; password salah berarti tidak ada yang berubah',
        ]}
        ackLabel="Saya sudah membandingkan nilai lama dan nilai baru"
        requires2fa
        confirmLabel="Simpan"
        confirmDisabled={!password.trim()}
        onCancel={() => { setDlgOpen(false); setPassword('') }}
        onConfirm={onConfirm}
      >
        <div className="sh-diff">
          <p className="sh-diff-title">Perubahan yang akan disimpan</p>
          <div className="sh-table-wrap">
            <table className="sh-table">
              <thead>
                <tr><th scope="col">Kolom</th><th scope="col">Lama</th><th scope="col">Baru</th></tr>
              </thead>
              <tbody>
                {diffRows.map((r) => (
                  <tr key={r.key}>
                    <td>{r.label}</td>
                    <td className="sh-num">{r.old}</td>
                    <td className="sh-num sh-new">{r.next}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <label className="sh-field-stack">
          <span className="sh-field-label">Password akun</span>
          <input
            className="sh-input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-label="Password akun"
          />
          <span className="sh-field-hint">Wajib diisi; server memverifikasi password dan kode 2FA sebelum menyimpan.</span>
        </label>
      </ConfirmDialog>
    </div>
  )
}
