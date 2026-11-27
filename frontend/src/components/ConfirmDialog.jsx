// Dialog konfirmasi dua langkah untuk aksi sensitif (PRD v2.2 §21.6):
//   Langkah 1: konsekuensi tindakan (teks eksplisit, bukan hanya warna) +
//              checklist recovery opsional + checkbox pengakuan.
//   Langkah 2: verifikasi 2FA (TOTP) bila aksi membutuhkannya, termasuk
//              alur pendaftaran bila 2FA belum aktif.
// Default action SELALU Batal (tidak ada default berbahaya); tombol bahaya
// tidak aktif sampai syarat terpenuhi. Escape membatalkan.
import { useEffect, useRef, useState } from 'react'
import { desk, toast } from '../lib/api'

export default function ConfirmDialog({
  open,
  title,
  description,
  consequences = [],
  checklist = null,          // array string -> ditampilkan sbg checklist recovery
  ackLabel = 'Saya paham konsekuensi tindakan ini',
  requires2fa = false,       // langkah 2: kode TOTP wajib
  confirmLabel = 'Konfirmasi',
  busy = false,
  confirmDisabled = false,   // syarat tambahan dari pemanggil (mis. password wajib)
  children = null,           // konten tambahan (mis. form trigger risiko)
  onCancel,
  onConfirm,                 // (twoFaCode | null) -> Promise
}) {
  const [ack, setAck] = useState(false)
  const [code, setCode] = useState('')
  const [step2, setStep2] = useState(false)
  const [enrolling, setEnrolling] = useState(false)
  const [secret, setSecret] = useState('')
  const [otpauthUri, setOtpauthUri] = useState('')
  const [err, setErr] = useState('')
  const [localBusy, setLocalBusy] = useState(false)
  const cancelRef = useRef(null)

  useEffect(() => {
    if (open) {
      setAck(false); setCode(''); setStep2(false); setEnrolling(false)
      setSecret(''); setOtpauthUri(''); setErr('')
      // fokus ke Batal: default yang aman
      setTimeout(() => cancelRef.current?.focus(), 0)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') onCancel() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onCancel])

  if (!open) return null

  const pending = busy || localBusy
  const canConfirm = ack && !confirmDisabled
    && (!requires2fa || (step2 && code.trim().length >= 6))

  async function startEnrollment() {
    setLocalBusy(true); setErr('')
    try {
      const r = await desk.twoFaSetup()
      setSecret(r.secret)
      setOtpauthUri(r.otpauth_uri || '')
      setEnrolling(true)
    } catch (ex) {
      setErr(ex.message === 'DEMO' ? '2FA tidak tersedia di mode demo' : ex.message)
    } finally { setLocalBusy(false) }
  }

  async function enable2fa() {
    setLocalBusy(true); setErr('')
    try {
      await desk.twoFaEnable(code.trim())
      setEnrolling(false)
      setStep2(true)
      setCode('')
      toast('2FA aktif', 'Kode TOTP kini wajib untuk aksi sensitif')
    } catch (ex) {
      setErr(ex.message === 'DEMO' ? '2FA tidak tersedia di mode demo' : ex.message)
    } finally { setLocalBusy(false) }
  }

  async function goStep2() {
    // Langkah 1 -> 2: cek status 2FA dulu. Sudah terdaftar -> input kode;
    // belum terdaftar -> pendaftaran di tempat, user tidak pernah buntu.
    setErr('')
    if (!requires2fa) {
      // Dialog tanpa 2FA (mis. kirim order): langkah 1 adalah eksekusi.
      await confirm()
      return
    }
    setLocalBusy(true)
    try {
      const st = await desk.twoFaStatus()
      if (st.enabled) {
        setStep2(true)
      } else {
        await startEnrollment()
        // Panel pendaftaran dirender di bawah step2 (step2 && enrolling):
        // tanpa ini pendaftaran inline tidak pernah tampil (user buntu).
        setStep2(true)
      }
    } catch (ex) {
      setErr(ex.message === 'DEMO' ? '2FA tidak tersedia di mode demo' : ex.message)
    } finally {
      setLocalBusy(false)
    }
  }

  async function confirm() {
    setErr('')
    setLocalBusy(true)
    try {
      if (requires2fa) {
        // assertion 2FA diperbarui dulu (challenge), baru aksi dieksekusi
        await desk.twoFaChallenge(code.trim())
      }
      await onConfirm(requires2fa ? code.trim() : null)
    } catch (ex) {
      const msg = ex.message === 'DEMO' ? 'Aksi tidak tersedia di mode demo' : ex.message
      setErr(msg)
      // assertion kedaluwarsa / belum daftar -> kembali ke langkah 2
      if (/2FA/i.test(msg)) setStep2(true)
    } finally { setLocalBusy(false) }
  }

  return (
    <div className="dialog-backdrop" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
      <div className="dialog confirm-dialog">
        <h3 className="dialog-title" id="confirm-title">{title}</h3>
        {description && <p className="dialog-sub">{description}</p>}

        {consequences.length > 0 && (
          <div className="consequences" aria-label="Konsekuensi tindakan">
            <p className="consequences-title">Konsekuensi tindakan ini:</p>
            <ul>
              {consequences.map((c, i) => (
                <li key={i}>
                  <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 3 2.5 20h19L12 3Zm0 6v5m0 3v.5" strokeLinejoin="round" />
                  </svg>
                  <span>{c}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {checklist && (
          <ul className="checklist">
            {checklist.map((item, i) => <li key={i}>{item}</li>)}
          </ul>
        )}

        {children}

        {!step2 && (
          <label className="confirm-ack">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            <span>{ackLabel}</span>
          </label>
        )}

        {step2 && !enrolling && (
          <div className="twofa-step">
            <p className="twofa-hint">Langkah 2 · Verifikasi 2FA: masukkan 6 kode digit dari authenticator app.</p>
            <input
              className="input twofa-code num"
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="······"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              aria-label="Kode 2FA"
            />
          </div>
        )}

        {step2 && enrolling && (
          <div className="twofa-step">
            <p className="twofa-hint">
              2FA belum terdaftar. Tambahkan secret ini ke authenticator app (Google
              Authenticator, Aegis, 1Password), lalu masukkan kode 6 digit untuk mengaktifkan.
            </p>
            <code className="twofa-secret num" selectability="text">{secret}</code>
            {otpauthUri && <p className="twofa-uri num">{otpauthUri}</p>}
            <input
              className="input twofa-code num"
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="······"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              aria-label="Kode 2FA pendaftaran"
            />
          </div>
        )}

        {err && <p className="field-error" role="alert">{err}</p>}
        {err && /belum terdaftar|not enrolled/i.test(err) && (
          <button type="button" className="btn btn-xs" onClick={startEnrollment} disabled={localBusy}>
            Daftar 2FA sekarang
          </button>
        )}

        <div className="dialog-actions">
          <button ref={cancelRef} className="btn" type="button" onClick={onCancel} disabled={pending}>
            Batal
          </button>
          {!step2 && (
            <button
              className="btn btn-danger"
              type="button"
              disabled={!ack || pending}
              onClick={goStep2}
            >
              {requires2fa ? 'Lanjut verifikasi 2FA' : confirmLabel}
            </button>
          )}
          {step2 && !enrolling && (
            <button
              className="btn btn-danger"
              type="button"
              disabled={!canConfirm || pending}
              onClick={confirm}
            >
              {pending ? 'Memproses…' : confirmLabel}
            </button>
          )}
          {step2 && enrolling && (
            <button
              className="btn btn-primary"
              type="button"
              disabled={code.trim().length < 6 || pending}
              onClick={enable2fa}
            >
              {pending ? 'Memeriksa…' : 'Aktifkan 2FA'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
