// Pilihan model LLM per peran. Fungsi simpan sama dengan panel model di
// halaman lama: baca katalog + pilihan tersimpan, simpan lewat kanal owner
// (wajib kode 2FA), lalu segarkan nilai efektif dari server. Tampilan sengaja
// bersih: tanpa id siklus, versi prompt, atau nama variabel internal.
import { useCallback, useEffect, useState } from 'react'
import { DEMO, desk, getAgentModels, putAgentModels } from '../../lib/api'
import { DebugOnly } from '../../lib/debug'

const GLOBALS = [
  { key: 'specialist', label: 'Specialist', hint: 'Empat analis paralel: struktur harga, makro, sentimen, portofolio.' },
  { key: 'synth', label: 'Synthesizer', hint: 'Menyatukan hasil analis menjadi satu keputusan.' },
  { key: 'fallback', label: 'Fallback', hint: 'Dipakai bila synthesizer gagal menjawab.' },
]

const ROLES = [
  { key: 'technical', label: 'Technical', hint: 'level, momentum, struktur' },
  { key: 'macro', label: 'Macro', hint: 'berita, suku bunga, korelasi' },
  { key: 'sentiment', label: 'Sentiment', hint: 'posisi pasar, arus order' },
  { key: 'portfolio', label: 'Portfolio', hint: 'eksposur, batas risiko' },
]

const emptyRoleForm = (saved) => Object.fromEntries(ROLES.map((r) => [r.key, saved?.[r.key] || '']))

function formFromBody(body) {
  const effective = body?.effective || {}
  return {
    specialist: effective.specialist || '',
    synth: effective.synth || '',
    fallback: effective.fallback || '',
    parallel: effective.parallel !== false,
    roles: emptyRoleForm(body?.roles_saved),
  }
}

export default function AgentModelsPanel() {
  const [data, setData] = useState(null)
  const [form, setForm] = useState(null)
  const [loading, setLoading] = useState(!DEMO)
  const [err, setErr] = useState(null)
  const [note, setNote] = useState(null)
  const [busy, setBusy] = useState(false)
  const [needCode, setNeedCode] = useState(false)
  const [code, setCode] = useState('')

  const load = useCallback(() => {
    if (DEMO) return
    getAgentModels()
      .then((body) => {
        setData(body)
        setForm(formFromBody(body))
        setErr(null)
        setNeedCode(false)
        setCode('')
      })
      .catch((ex) => setErr(ex?.code === 'DEMO' ? 'DEMO' : 'gagal'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const catalog = data?.catalog || []
  const options = (current) => {
    if (catalog.length) return catalog
    return [data?.env_model, current].filter(Boolean)
  }
  const roleOptions = (role) => {
    const saved = form?.roles?.[role]
    const list = catalog.slice()
    if (saved && !list.includes(saved)) list.unshift(saved)
    return list
  }
  const roleFallback = (role) => data?.role_defaults?.[role] || form?.specialist || data?.effective?.specialist

  const setField = (key, value) => setForm((prev) => ({ ...prev, [key]: value }))
  const setRole = (role, value) =>
    setForm((prev) => ({ ...prev, roles: { ...prev.roles, [role]: value } }))

  const validate = () => {
    if (!form) return 'Pilihan model belum siap.'
    for (const field of GLOBALS) {
      const value = form[field.key]
      if (!value) return `Model ${field.label} belum dipilih.`
      if (catalog.length && !catalog.includes(value)) {
        return `Model "${value}" tidak ada di daftar. Pilih dari daftar.`
      }
    }
    for (const role of ROLES) {
      const value = form.roles[role.key]
      if (value && catalog.length && !catalog.includes(value)) {
        return `Model "${value}" untuk ${role.label} tidak ada di daftar.`
      }
    }
    return null
  }

  const save = async () => {
    const invalid = validate()
    if (invalid) {
      setErr(invalid)
      setNote(null)
      return
    }
    setBusy(true)
    setErr(null)
    setNote(null)
    try {
      const body = await putAgentModels({
        specialist: form.specialist,
        synth: form.synth,
        fallback: form.fallback,
        parallel: form.parallel,
        roles: Object.fromEntries(ROLES.map((r) => [r.key, form.roles[r.key] || ''])),
      })
      setData((prev) => ({ ...prev, effective: body.effective, roles_saved: body.roles_saved || {} }))
      setForm((prev) => ({ ...prev, roles: emptyRoleForm(body.roles_saved) }))
      setNeedCode(false)
      setCode('')
      setNote('Tersimpan. Pilihan baru dipakai pada siklus berikutnya.')
    } catch (ex) {
      if (ex?.code === 'TWOFA') {
        setNeedCode(true)
        setErr('Perlu kode 2FA untuk menyimpan pilihan model.')
      } else {
        setErr(ex?.message || 'Gagal menyimpan pilihan model.')
      }
    } finally {
      setBusy(false)
    }
  }

  const verify = async () => {
    setBusy(true)
    setErr(null)
    try {
      await desk.twoFaChallenge(code.trim())
      setCode('')
      await save()
    } catch (ex) {
      setErr(ex?.message || 'Kode 2FA ditolak.')
    } finally {
      setBusy(false)
    }
  }

  let body
  if (DEMO) {
    body = <p className="agx-empty">Mode demo: pilihan model hanya bisa diubah pada data nyata.</p>
  } else if (loading) {
    body = <p className="agx-empty">Memuat pilihan model…</p>
  } else if (!form) {
    body = <p className="agx-empty">Pilihan model belum bisa dimuat.</p>
  } else {
    body = (
      <>
        {GLOBALS.map((field) => (
          <label className="agx-field" key={field.key}>
            <span className="agx-label">{field.label}</span>
            <select
              className="agx-select num"
              value={form[field.key]}
              disabled={busy}
              aria-label={`Model ${field.label}`}
              onChange={(e) => setField(field.key, e.target.value)}
            >
              {options(form[field.key]).map((model) => (
                <option key={model} value={model}>{model}</option>
              ))}
            </select>
            <span className="agx-hint">{field.hint}</span>
          </label>
        ))}

        <label className="agx-check">
          <input
            type="checkbox"
            checked={form.parallel}
            disabled={busy}
            onChange={(e) => setField('parallel', e.target.checked)}
          />
          <span>Jalankan empat analis secara bersamaan</span>
        </label>

        <details className="agx-details">
          <summary>Atur model per analis</summary>
          <p className="agx-hint">
            Kosongkan pilihan bila analis cukup mengikuti model Specialist.
          </p>
          <div className="agx-role-form">
            {ROLES.map((role) => (
              <label className="agx-role-form-row" key={role.key}>
                <span className="agx-role-form-name">
                  {role.label}
                  <span className="agx-hint">{role.hint}</span>
                </span>
                <select
                  className="agx-select num"
                  value={form.roles[role.key]}
                  disabled={busy}
                  aria-label={`Model untuk ${role.label}`}
                  onChange={(e) => setRole(role.key, e.target.value)}
                >
                  <option value="">Ikut Specialist ({roleFallback(role.key) || '—'})</option>
                  {roleOptions(role.key).map((model) => (
                    <option key={model} value={model}>{model}</option>
                  ))}
                </select>
              </label>
            ))}
          </div>
        </details>

        {needCode && (
          <div className="agx-field">
            <span className="agx-label">Kode 2FA</span>
            <input
              className="agx-input num"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              placeholder="6 digit"
              aria-label="Kode 2FA untuk menyimpan model"
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            />
            <div className="agx-actions">
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={busy || code.trim().length < 6}
                onClick={verify}
              >
                Verifikasi &amp; simpan
              </button>
            </div>
          </div>
        )}

        <div className="agx-actions">
          <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={save}>
            {busy ? 'Menyimpan…' : 'Simpan pilihan'}
          </button>
          <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={load}>
            Muat ulang
          </button>
        </div>
      </>
    )
  }

  return (
    <section className="agx-panel" aria-label="Model LLM per peran">
      <header className="agx-panel-head">
        <div>
          <h2 className="agx-h2">Model LLM</h2>
          <p className="agx-hint">Pilihan tersimpan dipakai pada siklus berikutnya.</p>
        </div>
        {catalog.length > 0 && <span className="agx-chip is-idle">{catalog.length} model</span>}
      </header>

      {err && err !== 'DEMO' && <p className="agx-note is-down" role="alert">{err}</p>}
      {note && <p className="agx-note is-up" role="status">{note}</p>}
      {body}
      <DebugOnly label="sumber">
        /llm-agent/models · katalog dari server · peran: specialist, synth, fallback, technical, macro, sentiment, portfolio
      </DebugOnly>
    </section>
  )
}
