import { useState } from 'react'
import { Link } from 'react-router-dom'
import { auth, DEMO } from '../lib/api'
import EnvBadge from '../components/EnvBadge'

// Gerbang "Allocator Authentication" — kartu kaca institusional sesuai
// referensi owner (monochrome glass risk ops).
// Logika auth tidak berubah: POST /auth/login (sesi cookie HttpOnly) lalu
// GET /auth/me. Badge env tetap tampil SEBELUM login (QA D6 GAP-1).
// Panel "Minta Akses" sengaja informatif: provisioning allocator dilakukan
// owner di luar aplikasi, jadi tidak ada formulir yang berpura-pura mengirim.

const SECURITY_ITEMS = [
  { k: 'Sesi', v: 'Cookie HttpOnly + CSRF token per request' },
  { k: '2FA', v: 'TOTP step-up untuk flatten, rilis kill-switch, aktivasi live' },
  { k: 'Jejak', v: 'Setiap aksi tercatat append-only di audit ledger' },
]

export default function Login() {
  const [tab, setTab] = useState('signin')
  const [user, setUser] = useState('')
  const [pass, setPass] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setErr('')
    setBusy(true)
    try {
      await auth.login(user.trim(), pass)
    } catch (ex) {
      setErr(ex.message)
      setBusy(false)
    }
    // Sukses: <Gate> melepas halaman ini; tombol tetap "busy" agar tidak
    // ada klik ganda di antara respons dan navigasi.
  }

  return (
    <div className="auth">
      <div className="auth-ambient" aria-hidden="true" />

      <header className="auth-top">
        <Link to="/landing" className="auth-back">
          <span aria-hidden="true">←</span>
          <span>Kembali ke lumine.fund</span>
        </Link>
        <EnvBadge />
      </header>

      <main className="auth-main">
        <section className="auth-card" aria-label="Allocator authentication">
          <div className="auth-brand">
            <span className="auth-mark" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round">
                <polygon points="12 2 21 7 21 17 12 22 3 17 3 7 12 2" />
                <line x1="12" y1="22" x2="12" y2="12" />
                <polyline points="21 7 12 12 3 7" />
              </svg>
            </span>
            <span className="auth-brand-text">
              <span className="auth-word">LUMINE FUND</span>
              <span className="auth-word-sub">Institutional gateway</span>
            </span>
            <span className="auth-tls" title="Sesi terenkripsi">
              <i aria-hidden="true" />
              TLS 1.3
            </span>
          </div>

          <div className="auth-tabs" role="tablist" aria-label="Mode akses">
            <button
              type="button"
              role="tab"
              id="auth-tab-signin"
              aria-selected={tab === 'signin'}
              aria-controls="auth-panel-signin"
              className={`auth-tab ${tab === 'signin' ? 'is-active' : ''}`}
              onClick={() => setTab('signin')}
            >
              Masuk allocator
            </button>
            <button
              type="button"
              role="tab"
              id="auth-tab-request"
              aria-selected={tab === 'request'}
              aria-controls="auth-panel-request"
              className={`auth-tab ${tab === 'request' ? 'is-active' : ''}`}
              onClick={() => setTab('request')}
            >
              Minta akses
            </button>
          </div>

          {tab === 'signin' ? (
            <div className="auth-panel" id="auth-panel-signin" role="tabpanel" aria-labelledby="auth-tab-signin">
              <div className="auth-panel-head">
                <h1 className="auth-title">Allocator Authentication</h1>
              </div>

              <form className="auth-form" onSubmit={submit} noValidate>
                <label className="auth-field">
                  <span className="auth-label">ID Allocator</span>
                  <input
                    className="auth-input"
                    value={user}
                    onChange={(e) => setUser(e.target.value)}
                    autoComplete="username"
                    autoFocus
                    required
                    spellCheck="false"
                    placeholder="allocator"
                    aria-invalid={!!err}
                  />
                </label>
                <label className="auth-field">
                  <span className="auth-label">Passcode</span>
                  <span className="auth-input-wrap">
                    <input
                      className="auth-input"
                      type={showPass ? 'text' : 'password'}
                      value={pass}
                      onChange={(e) => setPass(e.target.value)}
                      autoComplete="current-password"
                      required
                      placeholder="••••••••••••"
                      aria-invalid={!!err}
                    />
                    <button
                      type="button"
                      className="auth-reveal"
                      onClick={() => setShowPass((v) => !v)}
                      aria-label={showPass ? 'Sembunyikan passcode' : 'Tampilkan passcode'}
                      aria-pressed={showPass}
                    >
                      {showPass ? 'Sembunyikan' : 'Tampilkan'}
                    </button>
                  </span>
                </label>

                {err && (
                  <p className="auth-error" role="alert">
                    <span aria-hidden="true">!</span>
                    {err}
                  </p>
                )}

                <button className="auth-submit" type="submit" disabled={busy}>
                  {busy ? 'Memverifikasi…' : 'Masuk ke workstation →'}
                </button>
              </form>

              <div className="auth-security">
                <div className="auth-security-head">
                  <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="4" y="10" width="16" height="11" rx="2" />
                    <path d="M8 10V7a4 4 0 0 1 8 0v3" />
                  </svg>
                  <span>Kontrol akses</span>
                </div>
                <dl className="auth-security-list">
                  {SECURITY_ITEMS.map((it) => (
                    <div key={it.k}>
                      <dt>{it.k}</dt>
                      <dd>{it.v}</dd>
                    </div>
                  ))}
                </dl>
              </div>

              {DEMO && (
                <p className="auth-demo">
                  <span className="demo-badge">DEMO</span>
                  Data pasar sintetis. Kredensial demo diberikan operator; tidak ada dana nyata di sesi ini.
                </p>
              )}
            </div>
          ) : (
            <div className="auth-panel" id="auth-panel-request" role="tabpanel" aria-labelledby="auth-tab-request">
              <div className="auth-panel-head">
                <h1 className="auth-title">Akses allocator</h1>
              </div>
              <p className="auth-lede">
                Terminal ini tidak membuka pendaftaran mandiri. Akses diberikan
                operator Lumine setelah entitas diverifikasi; permintaan dikirim
                lewat kanal resmi yang sama dengan perjanjian alokasi Anda.
              </p>
              <ol className="auth-steps">
                <li>
                  <span className="auth-step-num num">01</span>
                  <div>
                    <strong>Verifikasi entitas</strong>
                    <p>Profil institusi dan lawan transaksi diperiksa sebelum provisioning.</p>
                  </div>
                </li>
                <li>
                  <span className="auth-step-num num">02</span>
                  <div>
                    <strong>Provisioning akun</strong>
                    <p>Operator membuat ID allocator, peran, dan passcode awal.</p>
                  </div>
                </li>
                <li>
                  <span className="auth-step-num num">03</span>
                  <div>
                    <strong>Enrolment 2FA</strong>
                    <p>TOTP didaftarkan di sesi pertama; aksi sensitif menolak tanpa step-up.</p>
                  </div>
                </li>
              </ol>
              <Link to="/landing#access" className="auth-secondary">
                Baca cakupan akses di portal publik →
              </Link>
            </div>
          )}

          <p className="auth-foot">
            SESI TERENKRIPSI · AKSES TERBATAS
            <span className="auth-foot-meta">
              Modal sendiri · XAUUSD &amp; BTCUSD lewat bridge MT5 · setiap order melewati gerbang risiko
            </span>
          </p>
        </section>
      </main>
    </div>
  )
}
