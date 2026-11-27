import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

/* Landing publik Lumine Fund — dunia "monochrome glass institutional".
   Halaman Persuade: satu signature moment (kanvas "optical filter": kekacauan
   pasar disaring menjadi sinyal bersih), sisanya restraint. Tanpa panggilan
   API: halaman ini publik, sehingga tidak ada data live yang diklaim. */

const SECTIONS = [
  { id: 'intelligence', label: 'Intelijen' },
  { id: 'pipeline', label: 'Pipeline' },
  { id: 'strategies', label: 'Strategi' },
  { id: 'risk', label: 'Risiko' },
  { id: 'access', label: 'Akses' },
]

// Fakta yang bisa dipertanggungjawabkan tanpa angka marketing: tidak ada
// AUM/investor/detensi palsu di halaman publik ini.
const TRUST = ['Modal sendiri', 'Bridge MT5', 'Audit append-only', 'Akses undangan']

/* Kanvas "optical filter": partikel chaos (kiri) melewati bidang filter dan
   menyusun satu garis sinyal bersih (kanan). Hemat: ~72 partikel, rAF tunggal,
   berhenti saat tab tersembunyi, bingkai statis untuk prefers-reduced-motion. */
function OpticalFilter() {
  const ref = useRef(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let raf = 0
    let w = 0
    let h = 0
    let dpr = 1

    const N = 110
    const parts = Array.from({ length: N }, (_, i) => ({
      seed: (i * 137.508) % 360,
      // Noise hanya lahir di sisi kanan komposisi (kolom teks kiri dibiarkan bersih).
      x: 0.53 + Math.random() * 0.45,
      y: Math.random(),
      v: 0.0016 + Math.random() * 0.0014,
    }))

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      w = canvas.clientWidth
      h = canvas.clientHeight
      canvas.width = w * dpr
      canvas.height = h * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    // Sinyal bersih: satu gelombang teredam di koordinat ternormalisasi (0..1).
    // Frekuensi sengaja rendah supaya garis terbaca sebagai sinyal tersaring,
    // bukan polyline harga berfrekuensi tinggi.
    const signalY = (u, t) =>
      h * 0.52 + Math.sin(u * 5.2 + t * 0.55) * h * 0.05 + Math.sin(u * 9.4 - t * 0.35) * h * 0.014

    function frame(tms) {
      const t = tms / 1000
      ctx.clearRect(0, 0, w, h)
      const filterX = w * 0.66

      // Bidang filter: band tipis + garis ambang + tick, supaya kanvas terbaca
      // sebagai gerbang penyaring (noise → sinyal), bukan grafik harga.
      const band = ctx.createLinearGradient(filterX - 30, 0, filterX + 30, 0)
      band.addColorStop(0, 'rgba(244, 245, 248, 0)')
      band.addColorStop(0.5, 'rgba(244, 245, 248, 0.075)')
      band.addColorStop(1, 'rgba(244, 245, 248, 0)')
      ctx.fillStyle = band
      ctx.fillRect(filterX - 30, h * 0.06, 60, h * 0.88)

      ctx.strokeStyle = 'rgba(244, 245, 248, 0.26)'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(filterX, h * 0.06)
      ctx.lineTo(filterX, h * 0.94)
      ctx.stroke()

      // tick ambang: penanda bahwa ini gerbang, bukan sumbu chart
      ctx.strokeStyle = 'rgba(244, 245, 248, 0.16)'
      for (let y = h * 0.1; y <= h * 0.9; y += h * 0.04) {
        ctx.beginPath()
        ctx.moveTo(filterX - 4, y)
        ctx.lineTo(filterX + 4, y)
        ctx.stroke()
      }

      ctx.font = '500 10px "IBM Plex Mono", ui-monospace, monospace'
      ctx.fillStyle = 'rgba(139, 144, 158, 0.85)'
      ctx.fillText('NOISE', filterX - 96, h * 0.11)
      ctx.fillText('GATE', filterX + 12, h * 0.11)
      ctx.fillStyle = 'rgba(16, 185, 129, 0.8)'
      ctx.fillText('CLEAN SIGNAL', filterX + 12, h * 0.89)

      // Garis sinyal pasca-filter digambar analitik (halus), bukan polyline
      // titik-titik — supaya tidak terbaca sebagai chart harga.
      ctx.strokeStyle = 'rgba(16, 185, 129, 0.5)'
      ctx.lineWidth = 1.5
      ctx.beginPath()
      for (let x = filterX; x <= w; x += 3) {
        const y = signalY(x / w, t)
        if (x === filterX) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      ctx.stroke()

      for (const p of parts) {
        p.x += p.v
        if (p.x > 1.02) {
          p.x = 0.53
          p.y = Math.random()
        }
        const px = p.x * w
        const chaos = Math.sin(p.seed + t * 2.1) * h * 0.035 + Math.sin(p.seed * 3 + t * 3.7) * h * 0.02
        const through = px > filterX
        const py = through ? signalY(px / w, t) + (p.y - 0.5) * 0.9 : p.y * h + chaos
        if (through) {
          // pasca-filter: titik hijau rapat pada garis sinyal
          ctx.fillStyle = 'rgba(16, 185, 129, 0.55)'
          ctx.beginPath()
          ctx.arc(px, py, 1.4, 0, Math.PI * 2)
          ctx.fill()
        } else {
          // pra-filter: coretan vertikal pendek (microstructure mentah), bukan titik data
          ctx.strokeStyle = 'rgba(244, 245, 248, 0.18)'
          ctx.lineWidth = 1
          ctx.beginPath()
          ctx.moveTo(px, py - 3.5)
          ctx.lineTo(px, py + 3.5)
          ctx.stroke()
        }
      }

      if (!reduced) raf = requestAnimationFrame(frame)
    }

    resize()
    window.addEventListener('resize', resize)
    if (reduced) frame(0)
    else raf = requestAnimationFrame(frame)
    const onVis = () => {
      if (document.hidden) cancelAnimationFrame(raf)
      else if (!reduced) raf = requestAnimationFrame(frame)
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [])

  return <canvas ref={ref} className="landing-canvas" aria-hidden="true" />
}

/* Jam sesi (ASIA / LONDON / NY) — jam dinding nyata per zona waktu. */
function SessionClocks() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])
  const zones = [
    { code: 'ASIA · TY3', tz: 'Asia/Jakarta' },
    { code: 'LONDON · LD4', tz: 'Europe/London' },
    { code: 'NY · NY4', tz: 'America/New_York' },
  ]
  const fmt = (tz) =>
    new Intl.DateTimeFormat('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
      timeZone: tz,
    }).format(now)
  return (
    <div className="landing-clocks num" aria-label="Jam sesi perdagangan">
      {zones.map((z) => (
        <span key={z.code} className="landing-clock">
          <i aria-hidden="true" />
          {z.code} <strong>{fmt(z.tz)}</strong>
        </span>
      ))}
    </div>
  )
}

export default function Landing() {
  return (
    <div className="landing">
      <OpticalFilter />

      <header className="landing-nav">
        <div className="landing-nav-inner">
          <Link to="/landing" className="landing-brand" aria-label="Lumine Fund">
            <span className="landing-brand-mark" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round">
                <polygon points="12 2 21 7 21 17 12 22 3 17 3 7 12 2" />
                <line x1="12" y1="22" x2="12" y2="12" />
                <polyline points="21 7 12 12 3 7" />
              </svg>
            </span>
            <span className="landing-brand-word">LUMINE</span>
            <span className="landing-brand-sub">FUND</span>
          </Link>
          <nav className="landing-links" aria-label="Navigasi landing">
            {SECTIONS.map((s) => (
              <a key={s.id} href={`#${s.id}`}>{s.label}</a>
            ))}
          </nav>
          <Link to="/login" className="landing-login">
            Masuk →
          </Link>
        </div>
      </header>

      <main className="landing-main">
        {/* ── Hero: optical filter ── */}
        <section className="landing-hero">
          <h1 className="landing-hero-title">
            Beyond Market<br />Noise.
          </h1>
          <p className="landing-hero-sub">
            Kekacauan microstructure pasar melewati filter Lumine: model LLM
            mengusulkan, gerbang risiko deterministik yang memutus, dan setiap
            keputusan tercatat append-only di buku besar audit.
          </p>
          <div className="landing-actions">
            <Link to="/login" className="btn btn-primary">Masuk portal allocator</Link>
            <a href="#pipeline" className="landing-textlink">Lihat pipeline <span aria-hidden="true">→</span></a>
          </div>
          <ul className="landing-trust num" aria-label="Cakupan platform">
            {TRUST.map((t) => <li key={t}>{t}</li>)}
          </ul>
          <div className="landing-hero-meta num">
            <span>XAUUSD · SPOT METALS</span>
            <span>BTCUSD · CRYPTO</span>
            <span>MT5 · TARGET &lt;300 MS</span>
          </div>
        </section>

        {/* ── Intelligence ── */}
        <section className="landing-section" id="intelligence">
          <h2 className="landing-h2">Intelijen yang diawasi gerbang deterministik.</h2>
          <p className="landing-lede">
            Tiga kanal konteks — sentimen pasar, fundamental makro, dan kalender
            ekonomi — disintesis untuk LLM. Usulannya tidak pernah sampai ke
            broker tanpa melewati gerbang risiko yang sama dengan order manual.
          </p>
          <div className="landing-grid3">
            <div className="lcard">
              <h3>Sentimen pasar</h3>
              <p>Berita dan aliran berita dibaca sebagai konteks, bukan sinyal mentah.</p>
            </div>
            <div className="lcard">
              <h3>Fundamental makro</h3>
              <p>Ringkasan fundamental mengikat proses ke data yang bisa diperiksa ulang.</p>
            </div>
            <div className="lcard">
              <h3>Kalender ekonomi</h3>
              <p>Peristiwa high-impact masuk blackout deterministik di sekitar jendela rilis.</p>
            </div>
          </div>
          <p className="landing-note">
            LLM tidak pernah memegang tombol order: keputusan akhir selalu milik
            gerbang deterministik dan owner.
          </p>
        </section>

        {/* ── Pipeline tiga gerbang ── */}
        <section className="landing-section" id="pipeline">
          <h2 className="landing-h2">Pipeline tiga gerbang.</h2>
          <p className="landing-lede">
            Setiap order menempuh validasi, verifikasi risiko, dan eksekusi
            terukur — bukan satu kotak hitam.
          </p>
          <ol className="landing-pipeline">
            <li>
              <div className="landing-step-head">
                <span className="landing-step-num num">01</span>
                <h3>Ingesti sinyal</h3>
                <span className="chip">M1 / M5 FRESHNESS</span>
              </div>
              <p>Candle harus segar (ambang &lt;10 menit) dan gap data likuiditas satu jam difilter sebelum inferensi; data lebih dari 24 jam gagal tertutup.</p>
            </li>
            <li>
              <div className="landing-step-head">
                <span className="landing-step-num num">02</span>
                <h3>Gerbang risiko pra-order</h3>
                <span className="chip chip-down">HARD LIMITS</span>
              </div>
              <p>Batas drawdown harian dieksekusi server-side, SL/TP wajib, dan pelampauan batas memicu GLOBAL_HALT; pelepasan butuh checklist ack + 2FA owner.</p>
            </li>
            <li>
              <div className="landing-step-head">
                <span className="landing-step-num num">03</span>
                <h3>Eksekusi terukur</h3>
                <span className="chip chip-up">T0→T2 · T0→T4</span>
              </div>
              <p>Routing MT5 dengan telemetri latensi p50/p95/p99 per order, target eksekusi &lt;300 ms, dan setiap transisi status tercatat di event log.</p>
            </li>
          </ol>
        </section>

        {/* ── Strategi ── */}
        <section className="landing-section" id="strategies">
          <h2 className="landing-h2">Regime volatilitas yang saling lepas.</h2>
          <p className="landing-lede">
            Strategi berformat skill dengan versi immutable: paper dulu, review
            owner, baru live. Performa riil hanya tampil di terminal setelah masuk.
          </p>
          <div className="landing-grid3">
            <div className="lcard">
              <div className="lcard-head">
                <h3>London Breakout + Spread Filter</h3>
                <span className="chip">PAPER</span>
              </div>
              <p className="num">XAUUSD · M5 · volatility compression breakout</p>
            </div>
            <div className="lcard">
              <div className="lcard-head">
                <h3>Mean Reversion (Bollinger re-entry)</h3>
                <span className="chip">PAPER</span>
              </div>
              <p className="num">XAUUSD · M1 · standard deviation band re-entry</p>
            </div>
            <div className="lcard">
              <div className="lcard-head">
                <h3>BTC Range Breakout 24/7</h3>
                <span className="chip">PAPER</span>
              </div>
              <p className="num">BTCUSD · M5 · continuous weekend channel expansion</p>
            </div>
          </div>
          <p className="landing-note">
            Status, versi aktif, dan hasil paper/live hanya tampil di dalam
            terminal setelah login — halaman publik tidak menampilkan angka
            performa.
          </p>
        </section>

        {/* ── Risk gyroscope ── */}
        <section className="landing-section" id="risk">
          <h2 className="landing-h2">Giro skop risiko: tiga cincin, satu tujuan.</h2>
          <p className="landing-lede">
            Tiga cincin pengaman memantau ekuitas portofolio dan menghentikan
            order baru otomatis saat drawdown melampaui batas.
          </p>
          <div className="landing-risk">
            <svg className="landing-rings" viewBox="0 0 200 200" role="img" aria-label="Tiga cincin pengaman risiko">
              <circle cx="100" cy="100" r="88" fill="none" stroke="rgba(244, 245, 248,0.10)" strokeWidth="1" />
              <circle cx="100" cy="100" r="64" fill="none" stroke="rgba(245, 158, 11,0.45)" strokeWidth="1" />
              <circle cx="100" cy="100" r="40" fill="none" stroke="rgba(239, 68, 68,0.55)" strokeWidth="1" />
              <circle cx="100" cy="100" r="4" fill="#10b981" />
            </svg>
            <div className="landing-risk-list">
              <div className="landing-risk-row">
                <span className="num">0.0%</span>
                <div><strong>NOMINAL</strong><p>Order baru mengalir normal.</p></div>
              </div>
              <div className="landing-risk-row">
                <span className="num">WATCH</span>
                <div><strong>AMBANG TERPANTAU</strong><p>Evaluator menaikkan status secara data-driven; tidak ada input manual.</p></div>
              </div>
              <div className="landing-risk-row">
                <span className="num down-text">HARD LOCK</span>
                <div><strong>GLOBAL_HALT</strong><p>Order baru berhenti; pelepasan butuh review + approval owner dengan 2FA.</p></div>
              </div>
            </div>
          </div>
        </section>

        {/* ── Akses allocator ── */}
        <section className="landing-section" id="access">
          <h2 className="landing-h2">Dibangun untuk allocator yang aktif.</h2>
          <p className="landing-lede">
            Akses diberikan oleh owner: profil institusi diverifikasi, terminal
            risk-ops disediakan, dan seluruh aktivitas tercatat.
          </p>
          <div className="landing-grid2">
            <div className="lcard lcard-action">
              <h3>Akses allocator</h3>
              <p>Masuk ke terminal risk ops: harga live, posisi, riwayat order, dan audit.</p>
              <Link to="/login" className="btn btn-primary">Masuk ke terminal</Link>
            </div>
            <div className="lcard lcard-action">
              <h3>Onboarding institusi</h3>
              <p>Profil entitas untuk verifikasi KYC/AML dan provisioning terminal. Akses diberikan operator Lumine, bukan pendaftaran mandiri.</p>
              <span className="chip">OLEH UNDANGAN · KYC / AML</span>
            </div>
          </div>
        </section>

        <footer className="landing-foot">
          <SessionClocks />
          <p className="landing-disclaimer">
            Backtest dan kinerja paper bukan jaminan performa live. Trading
            instrumen ber-leverage melibatkan risiko kehilangan modal. Seluruh
            angka performa hanya tampil di terminal untuk pengguna terautentikasi.
          </p>
          <p className="landing-copy num">LUMINE FUND · INSTITUTIONAL GATEWAY · © 2026</p>
        </footer>
      </main>
    </div>
  )
}
