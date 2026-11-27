// Sub-tab 3 · Konfigurasi Agent & Kalender.
// Nilai aktif selalu tampil; yang bisa diubah hanya setelan yang memang punya
// kanal simpan (siklus agent + auto-lot). Prompt dan filter kalender tampil
// sebagai nilai aktif dengan alasan jelas kenapa belum bisa diubah dari sini.
import { useCallback, useEffect, useState } from 'react'
import ConfirmDialog from '../ConfirmDialog'
import { DebugOnly } from '../../lib/debug'
import {
  DEMO,
  getAgentConfig,
  resumeLlmAgent,
  toast,
  updateRiskSettings,
} from '../../lib/api'
import { ActiveChip, EmptyLine, HubCard, LockedNote, MetaRow, StatusPill, Switch } from './ui'
import { fmtNum, fmtRange, fmtTime, parseDraft } from './format'

const DEMO_CONFIG = {
  system_prompt: '[DEMO] System prompt contoh. Mode demo tidak memanggil API; tidak ada data live di halaman ini.',
  prompt_version: 'DEMO-0.0.1',
  model: 'demo-model',
  interval_s: 300,
  interval_range_s: { min: 30, max: 86400 },
  llm_risk: { max_orders_per_day: 20 },
  llm_auto_lot: { enabled: true, risk_pct: null },
  calendar: {
    blackout_active: false,
    blackout_reason: null,
    data: {
      status: 'ok',
      source: 'demo',
      as_of: new Date().toISOString(),
      next_high_impact_utc: null,
      minutes_to_next_high_impact: null,
      events: [],
    },
  },
  pause: { active: false, reason: null, activated_at: null },
  symbol_policy: { mode: 'parallel', custom: { XAUUSD: [0, 1, 2, 3, 4], BTCUSD: [5, 6] } },
  symbol_policy_modes: [
    { value: 'parallel', label: 'Paralel: semua simbol dianalisa setiap hari' },
    { value: 'hybrid', label: 'Hybrid: BTC hanya saat XAU tutup atau basi' },
    { value: 'weekend_only', label: 'Weekend only: XAU hari kerja, BTC akhir pekan' },
    { value: 'custom', label: 'Pilih hari sendiri per simbol' },
  ],
  symbol_policy_days: ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu'],
  active_symbols: ['XAUUSD', 'BTCUSD'],
}

const MODE_SHORT = {
  parallel: 'Paralel',
  hybrid: 'Hybrid',
  weekend_only: 'Weekend only',
  custom: 'Pilih hari',
}

const IMPACT_LABEL = { High: 'Tinggi', Medium: 'Sedang', Low: 'Rendah' }

function impactText(impact) {
  if (impact == null || impact === '') return '·'
  return IMPACT_LABEL[impact] || String(impact)
}

// Alasan blackout datang dari server dalam bentuk berkode ("calendar_blackout: …").
// Awalan kode itu urusan teknis, bukan bahasa operator.
function humanReason(raw) {
  if (!raw) return 'tidak dilaporkan'
  const text = String(raw).replace(/^[a-z_]+:\s*/i, '').trim()
  if (!text) return 'tidak dilaporkan'
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export default function AgentCalendarTab() {
  const [cfg, setCfg] = useState(() => (DEMO ? DEMO_CONFIG : null))
  const [loadErr, setLoadErr] = useState('')
  const [intervalDraft, setIntervalDraft] = useState('')
  const [autoLotDraft, setAutoLotDraft] = useState(null)
  const [copied, setCopied] = useState(false)
  const [dlgOpen, setDlgOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [resumeOpen, setResumeOpen] = useState(false)
  const [resumeErr, setResumeErr] = useState('')
  const [policyDraft, setPolicyDraft] = useState(null)

  const load = useCallback(async () => {
    if (DEMO) return
    try {
      const body = await getAgentConfig()
      setCfg(body)
      setLoadErr('')
      setIntervalDraft('')
      setAutoLotDraft(null)
      setPolicyDraft(null)
    } catch {
      setLoadErr('Konfigurasi agent belum bisa dimuat.')
    }
  }, [])

  useEffect(() => { Promise.resolve().then(load) }, [load])

  const intervalRange = cfg?.interval_range_s || { min: 30, max: 86400 }
  const activeInterval = Number(cfg?.interval_s)
  const parsedInterval = parseDraft(intervalDraft)
  let intervalError = ''
  if (intervalDraft.trim() !== '') {
    if (parsedInterval == null || Number.isNaN(parsedInterval)) intervalError = 'Harus berupa angka'
    else if (parsedInterval < intervalRange.min || parsedInterval > intervalRange.max) {
      intervalError = `Harus di antara ${fmtRange(intervalRange.min, intervalRange.max)} detik`
    }
  }
  const intervalChanged = parsedInterval != null
    && !Number.isNaN(parsedInterval)
    && Number.isFinite(activeInterval)
    && Math.abs(parsedInterval - activeInterval) > 1e-9

  const autoLotActive = !!cfg?.llm_auto_lot?.enabled
  const autoLotChanged = autoLotDraft != null && autoLotDraft !== autoLotActive

  // ── jadwal analisa simbol: mode + hari (hanya dipakai saat mode 'custom') ──
  const policyActive = cfg?.symbol_policy || { mode: 'parallel', custom: {} }
  const policyModes = cfg?.symbol_policy_modes || []
  const policyDays = cfg?.symbol_policy_days || []
  const policy = policyDraft || policyActive
  const policyChanged = policyDraft != null
    && (policyDraft.mode !== policyActive.mode
      || JSON.stringify(policyDraft.custom || {}) !== JSON.stringify(policyActive.custom || {}))
  const policySymbols = Object.keys(policyActive.custom || {})
  const activeSymbols = Array.isArray(cfg?.active_symbols) ? cfg.active_symbols : []

  function setMode(mode) {
    setPolicyDraft({ mode, custom: { ...(policy.custom || {}) } })
  }

  function toggleDay(sym, day) {
    const custom = { ...(policy.custom || {}) }
    const days = new Set(custom[sym] || [])
    if (days.has(day)) days.delete(day)
    else days.add(day)
    custom[sym] = [...days].sort((a, b) => a - b)
    setPolicyDraft({ mode: policy.mode, custom })
  }

  const dirty = intervalChanged || autoLotChanged || policyChanged

  const prompt = cfg?.system_prompt ?? ''
  const cal = cfg?.calendar || {}
  const calData = cal.data || {}
  const events = Array.isArray(calData.events) ? calData.events : []
  const pause = cfg?.pause || {}

  function copyPrompt() {
    if (!prompt) return
    navigator.clipboard?.writeText(prompt).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    }).catch(() => {})
  }

  function resetDraft() {
    setIntervalDraft('')
    setAutoLotDraft(null)
    setPolicyDraft(null)
  }

  async function onConfirm() {
    const payload = { password: password.trim() }
    if (intervalChanged) payload.llm_interval_s = parsedInterval
    if (autoLotChanged) payload.llm_auto_lot = { enabled: autoLotDraft }
    if (policyChanged) {
      payload.llm_symbol_policy = { mode: policy.mode, custom: policy.custom || {} }
    }
    try {
      await updateRiskSettings(payload)
    } catch (ex) {
      const raw = ex.message || ''
      throw new Error(
        /password/i.test(raw)
          ? 'Password akun salah. Tidak ada nilai yang berubah.'
          : /simbol|hari|mode/i.test(raw)
            ? 'Jadwal ditolak server. Periksa simbol dan hari yang dipilih.'
            : 'Nilai ditolak. Periksa rentang lalu coba lagi.',
      )
    }
    toast('Setelan agent tersimpan', 'Jadwal dan siklus baru dipakai pada putaran berikutnya')
    setDlgOpen(false)
    setPassword('')
    await load()
  }

  async function onResume() {
    setResumeErr('')
    try {
      await resumeLlmAgent()
      toast('Agent aktif kembali', 'Pause otomatis dilepas dan agent bisa mengirim order lagi')
      setResumeOpen(false)
      await load()
    } catch (ex) {
      const message = ex?.message === 'DEMO'
        ? 'Aksi tidak tersedia di mode demo.'
        : 'Agent belum bisa diaktifkan. Pastikan 2FA dan peran akun memenuhi syarat.'
      setResumeErr(message)
      throw new Error(message)
    }
  }

  if (loadErr) {
    return (
      <HubCard title="Konfigurasi agent" badge={<StatusPill tone="is-down">TIDAK TERSEDIA</StatusPill>}>
        <EmptyLine>{loadErr}</EmptyLine>
        {!DEMO && (
          <button type="button" className="btn sh-btn" onClick={load}>Muat ulang</button>
        )}
      </HubCard>
    )
  }

  if (!cfg) return <p className="sh-empty">Memuat konfigurasi agent…</p>

  return (
    <div className="sh-grid sh-grid-main">
      <HubCard
        title="Setelan siklus agent"
        badge={<StatusPill tone={dirty ? 'is-warn' : ''}>{dirty ? 'ADA DRAF' : 'SESUAI NILAI AKTIF'}</StatusPill>}
        note="Dua setelan ini tersimpan langsung ke konfigurasi yang dipakai agent."
      >
        <div className="sh-fields">
          <div className="sh-field">
            <div className="sh-field-main">
              <div className="sh-field-top">
                <span className="sh-field-label">Jeda antar siklus agent</span>
                <ActiveChip>{fmtNum(activeInterval, 0)} detik</ActiveChip>
                {intervalChanged && <span className="sh-delta">→ {fmtNum(parsedInterval, 0)} detik</span>}
              </div>
              <span className="sh-field-hint">
                Makin pendek makin sering agent menilai pasar. Rentang wajar{' '}
                {fmtRange(intervalRange.min, intervalRange.max)} detik.
              </span>
              {intervalError && <span className="sh-field-err">{intervalError}</span>}
            </div>
            <div className="sh-ctl">
              <input
                className={`sh-input ${intervalError ? 'is-error' : ''}`.trim()}
                inputMode="numeric"
                aria-label="Jeda antar siklus agent dalam detik"
                placeholder={fmtNum(activeInterval, 0)}
                value={intervalDraft}
                onChange={(e) => setIntervalDraft(e.target.value)}
              />
              <span className="sh-unit">detik</span>
            </div>
          </div>

          <div className="sh-switch-row">
            <div className="sh-field-main">
              <div className="sh-field-top">
                <span className="sh-field-label">Ukuran lot otomatis</span>
                <ActiveChip>{autoLotActive ? 'ON' : 'OFF'}</ActiveChip>
                {autoLotChanged && <span className="sh-delta">→ {autoLotDraft ? 'ON' : 'OFF'}</span>}
              </div>
              <span className="sh-field-hint">
                ON: agent menghitung lot dari risiko per trade. OFF: lot tetap memakai nilai manual.
                {autoLotActive && ' Saat ON, angka volume kiriman LLM diabaikan: lot dihitung ulang dari risiko lalu dibatasi topi lot simbol.'}
              </span>
            </div>
            <Switch
              label="Ukuran lot otomatis"
              checked={autoLotDraft ?? autoLotActive}
              disabled={DEMO}
              onChange={setAutoLotDraft}
            />
          </div>

          {autoLotActive && (
            <div className="sh-field" data-testid="autolot-effective">
              <div className="sh-field-main">
                <div className="sh-field-top">
                  <span className="sh-field-label">Risiko per trade efektif</span>
                  <ActiveChip>
                    {cfg?.llm_auto_lot?.effective_risk_pct != null
                      ? `${fmtNum(cfg.llm_auto_lot.effective_risk_pct, 2)}%`
                      : '·'}
                  </ActiveChip>
                </div>
                <span className="sh-field-hint">
                  min(override auto-lot {fmtNum(cfg?.llm_auto_lot?.risk_pct, 2)}%,
                  global {fmtNum(cfg?.risk_per_trade_pct, 2)}%).
                  Override hanya bisa menurunkan risiko, tidak menaikkan.
                  Topi lot efektif:{' '}
                  {cfg?.effective_max_volume && Object.keys(cfg.effective_max_volume).length
                    ? Object.entries(cfg.effective_max_volume)
                      .map(([sym, cap]) => `${sym} ${cap == null ? '·' : fmtNum(cap, 2)}`)
                      .join(' · ')
                    : '·'}
                  {' '}lot, ditentukan server dari min(topi akun, vol_max_lot simbol).
                </span>
              </div>
            </div>
          )}
        </div>

        <div className="sh-actions">
          <button
            type="button"
            className="btn btn-primary sh-btn"
            disabled={!dirty || !!intervalError || DEMO}
            onClick={() => { setPassword(''); setDlgOpen(true) }}
          >
            {dirty ? 'Simpan setelan agent' : 'Tidak ada perubahan'}
          </button>
          {dirty && (
            <button type="button" className="btn sh-btn" onClick={resetDraft} disabled={DEMO}>
              Batalkan
            </button>
          )}
        </div>
        {DEMO && <LockedNote>Mode demo: penyimpanan dinonaktifkan, nilai di atas hanya contoh.</LockedNote>}
      </HubCard>

      <HubCard
        title="Jadwal analisa simbol"
        badge={
          <StatusPill tone={policyChanged ? 'is-warn' : ''}>
            {policyChanged ? 'ADA DRAF' : 'AKTIF'}
          </StatusPill>
        }
        note="Menentukan simbol mana yang dianalisa agent tiap siklus. Jadwal tidak pernah membuka order ke pasar tutup: gate order tetap memutuskan sendiri."
      >
        <div className="sh-fields">
          <div className="sh-field">
            <div className="sh-field-main">
              <div className="sh-field-top">
                <span className="sh-field-label">Pola jadwal</span>
                <ActiveChip>{MODE_SHORT[policyActive.mode] || policyActive.mode}</ActiveChip>
                {policyChanged && (
                  <span className="sh-delta">→ {MODE_SHORT[policy.mode] || policy.mode}</span>
                )}
              </div>
              <span className="sh-field-hint">
                {policyModes.find((m) => m.value === policy.mode)?.label || '·'}
                {policy.mode === 'hybrid'
                  && ' Simbol cadangan hanya dipanggil bila simbol utama tutup atau datanya basi.'}
              </span>
            </div>
            <div className="sh-ctl">
              <div className="sh-seg" role="radiogroup" aria-label="Pola jadwal analisa simbol">
                {policyModes.map((m) => (
                  <button
                    key={m.value}
                    type="button"
                    role="radio"
                    aria-checked={policy.mode === m.value}
                    title={m.label}
                    className={`sh-seg-btn ${policy.mode === m.value ? 'is-on' : ''}`.trim()}
                    disabled={DEMO}
                    onClick={() => setMode(m.value)}
                  >
                    {MODE_SHORT[m.value] || m.value}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {policy.mode === 'custom' && (
            <div className="sh-field" data-testid="symbol-policy-days">
              <div className="sh-field-main">
                <div className="sh-field-top">
                  <span className="sh-field-label">Hari per simbol</span>
                  <span className="sh-field-hint">0=Senin · 6=Minggu (WIB)</span>
                </div>
                {policySymbols.map((sym, index) => (
                  <div key={sym} style={{ marginTop: index ? 10 : 4 }}>
                    <span className="sh-field-label" style={{ fontSize: 12 }}>{sym}</span>
                    <div className="sh-days">
                      {policyDays.map((name, day) => {
                        const on = (policy.custom?.[sym] || []).includes(day)
                        return (
                          <button
                            key={name}
                            type="button"
                            aria-pressed={on}
                            aria-label={`${sym} ${name}`}
                            className={`sh-day ${on ? 'is-on' : ''}`.trim()}
                            disabled={DEMO}
                            onClick={() => toggleDay(sym, day)}
                          >
                            {name.slice(0, 3)}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ))}
                <span className="sh-field-hint">
                  Simbol tanpa hari terpilih tidak pernah dianalisa. Minimal satu hari per simbol.
                </span>
              </div>
            </div>
          )}

          <div className="sh-field">
            <div className="sh-field-main">
              <div className="sh-field-top">
                <span className="sh-field-label">Dianalisa siklus ini</span>
                <ActiveChip>{activeSymbols.length ? activeSymbols.join(' · ') : 'tidak ada'}</ActiveChip>
              </div>
              <span className="sh-field-hint">
                Hasil jadwal + preflight (pasar buka, data segar, spread wajar).
                Simbol yang lolos di sini belum tentu pasar buka, dan sebaliknya.
              </span>
            </div>
          </div>
        </div>
      </HubCard>

      <HubCard
        title="Status agent"
        badge={(
          <StatusPill tone={pause.active ? 'is-down' : 'is-up'}>
            {pause.active ? 'DIJEDA' : 'BERJALAN'}
          </StatusPill>
        )}
      >
        <div className="sh-meta-list">
          <MetaRow label="Model" value={cfg.model || '·'} />
          <MetaRow label="Versi prompt" value={cfg.prompt_version || '·'} />
          <MetaRow label="Alasan jeda" value={pause.active ? (pause.reason || 'tidak dilaporkan') : '·'} />
          <MetaRow label="Dijeda sejak" value={pause.active ? fmtTime(pause.activated_at) : '·'} />
        </div>
        {pause.active ? (
          <div className="sh-actions">
            <button type="button" className="btn sh-btn" onClick={() => { setResumeErr(''); setResumeOpen(true) }} disabled={DEMO}>
              Aktifkan agent kembali
            </button>
          </div>
        ) : (
          <p className="sh-field-hint">Agent berjalan normal. Pause otomatis terjadi bila batas rugi atau kegagalan beruntun tersentuh.</p>
        )}
      </HubCard>

      <HubCard
        title="System prompt"
        badge={<StatusPill>{prompt.length.toLocaleString('id-ID')} karakter</StatusPill>}
        note="Teks yang dipakai agent pada setiap putaran. Perubahan prompt ikut rilis aplikasi, bukan pengaturan harian."
      >
        <textarea
          className="sh-prompt"
          value={prompt}
          readOnly
          spellCheck={false}
          aria-label="System prompt agent"
          rows={14}
        />
        <div className="sh-actions">
          <button type="button" className="btn sh-btn" onClick={copyPrompt} disabled={!prompt}>
            {copied ? 'Tersalin' : 'Salin prompt'}
          </button>
          <button type="button" className="btn btn-primary sh-btn" disabled>
            Simpan prompt
          </button>
        </div>
        <LockedNote>
          Penyimpanan prompt belum tersedia. Prompt berlaku sebagai bagian rilis aplikasi,
          sehingga perubahan harus lewat rilis, bukan dari halaman ini.
        </LockedNote>
        <DebugOnly label="prompt">{`${cfg.prompt_version || '·'} · ${prompt.length} karakter`}</DebugOnly>
      </HubCard>

      <HubCard
        title="Filter blackout kalender"
        badge={(
          <StatusPill tone={cal.blackout_active ? 'is-warn' : ''}>
            {cal.blackout_active ? 'BLACKOUT AKTIF' : 'JENDELA BEBAS'}
          </StatusPill>
        )}
        note="Order baru agent ditahan di sekitar event berdampak tinggi agar tidak masuk saat pasar bergerak liar."
      >
        <div className="sh-meta-list">
          <MetaRow
            label="Alasan blackout"
            value={cal.blackout_active ? humanReason(cal.blackout_reason) : '·'}
          />
          <MetaRow
            label="Event berdampak tinggi berikutnya"
            value={calData.next_high_impact_utc ? fmtTime(calData.next_high_impact_utc) : 'tidak ada di jendela data'}
          />
          <MetaRow
            label="Menuju event berikutnya"
            value={calData.minutes_to_next_high_impact != null
              ? `${fmtNum(calData.minutes_to_next_high_impact, 0)} menit`
              : '·'}
          />
          <MetaRow label="Data kalender diperbarui" value={fmtTime(calData.as_of || calData.fetched_at)} />
        </div>

        {events.length === 0 ? (
          <EmptyLine>Tidak ada event berdampak tinggi dalam jendela data saat ini.</EmptyLine>
        ) : (
          <ul className="sh-events">
            {events.slice(0, 10).map((ev, i) => {
              const currency = ev.currency || ev.country || ''
              const blocked = currency === 'USD'
              return (
                <li key={`${ev.time_utc || ev.date || i}-${ev.title || i}`} className="sh-event">
                  <span className="sh-event-time">{fmtTime(ev.time_utc || ev.date)}</span>
                  <span className="sh-event-title">{ev.title || 'Event tanpa judul'}</span>
                  <span className="sh-event-meta">{currency || '·'} · {impactText(ev.impact)}</span>
                  <Switch
                    label={`Blokir ${ev.title || 'event'}`}
                    checked={blocked}
                    disabled
                    hint="Filter per event belum bisa diubah dari aplikasi ini"
                    onChange={() => {}}
                  />
                </li>
              )
            })}
          </ul>
        )}

        <div className="sh-actions">
          <button type="button" className="btn sh-btn" disabled>Tambah event</button>
          <button type="button" className="btn sh-btn" disabled>Hapus event terpilih</button>
        </div>
        <LockedNote>
          Filter, tambah, dan hapus event belum punya kanal simpan di aplikasi ini. Sesi blackout
          saat ini mengikuti konfigurasi server dan hanya statusnya yang bisa dipantau.
        </LockedNote>
      </HubCard>

      <ConfirmDialog
        open={dlgOpen}
        title="Simpan setelan agent"
        description="Periksa nilai lama dan nilai baru sebelum menyimpan."
        consequences={[
          'Setelan baru dipakai agent pada putaran berikutnya',
          'Perubahan tercatat permanen di riwayat audit',
          'Password akun dan kode 2FA diverifikasi server sebelum menyimpan',
        ]}
        ackLabel="Saya sudah memeriksa setelan ini"
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
                <tr><th scope="col">Setelan</th><th scope="col">Lama</th><th scope="col">Baru</th></tr>
              </thead>
              <tbody>
                {intervalChanged && (
                  <tr>
                    <td>Jeda antar siklus</td>
                    <td className="sh-num">{fmtNum(activeInterval, 0)} detik</td>
                    <td className="sh-num sh-new">{fmtNum(parsedInterval, 0)} detik</td>
                  </tr>
                )}
                {autoLotChanged && (
                  <tr>
                    <td>Ukuran lot otomatis</td>
                    <td className="sh-num">{autoLotActive ? 'ON' : 'OFF'}</td>
                    <td className="sh-num sh-new">{autoLotDraft ? 'ON' : 'OFF'}</td>
                  </tr>
                )}
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
          <span className="sh-field-hint">Wajib diisi; server memverifikasi password dan kode 2FA.</span>
        </label>
      </ConfirmDialog>

      <ConfirmDialog
        open={resumeOpen}
        title="Aktifkan agent kembali"
        description="Lepas jeda otomatis agar agent bisa menilai pasar dan mengirim order lagi."
        consequences={[
          'Agent bisa mengirim order baru pada putaran berikutnya',
          'Pelepasan jeda tercatat permanen di riwayat penghentian',
          'Hanya admin dengan 2FA yang bisa melakukan ini',
        ]}
        ackLabel="Saya paham agent akan aktif kembali"
        requires2fa
        confirmLabel="Aktifkan agent"
        onCancel={() => { setResumeOpen(false); setResumeErr('') }}
        onConfirm={onResume}
      >
        {resumeErr && <p className="sh-field-err">{resumeErr}</p>}
      </ConfirmDialog>
    </div>
  )
}
