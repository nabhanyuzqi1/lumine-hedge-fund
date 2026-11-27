// Halaman Bantuan (/bantuan): satu tempat untuk penjelasan yang dulu
// menumpuk di Terminal: daftar strategi aktif, arti badge, arti status pasar,
// kill switch, istilah metrik, dan langkah mengirim order.
//
// Isi halaman ini statis dan sengaja tidak memanggil API baru: daftar strategi
// diambil dari registry backend (london_breakout v1.1.0, mean_reversion
// v1.0.0, btc_range_breakout v1.0.0, semuanya mode paper), bukan dihitung
// ulang di browser. Tidak ada angka performa di sini; statistik hidup di
// halaman Agent supaya selalu berasal dari satu sumber (GET /strategies).
import { Link } from 'react-router-dom'

const STRATEGI = [
  {
    key: 'london_breakout',
    name: 'London Breakout + Spread Filter',
    version: 'v1.1.0',
    symbol: 'XAUUSD',
    cara:
      'Menunggu sesi London menembus range sesi Asia, lalu masuk searah ' +
      'tembusan hanya bila spread masih di bawah filter rata-rata.',
  },
  {
    key: 'mean_reversion',
    name: 'Mean Reversion (Bollinger re-entry)',
    version: 'v1.0.0',
    symbol: 'XAUUSD',
    cara:
      'Harga yang menyimpang keluar pita Bollinger ditunggu kembali masuk, ' +
      'lalu posisi dibuka menuju harga rata-rata.',
  },
  {
    key: 'btc_range_breakout',
    name: 'BTC Range Breakout 24/7',
    version: 'v1.0.0',
    symbol: 'BTCUSD',
    cara:
      'Mengikuti tembusan channel range Bitcoin yang terbentuk sepanjang ' +
      'hari; berjalan 24 jam tanpa jeda sesi.',
  },
]

const BADGE = [
  {
    key: 'live',
    tone: 'live',
    label: 'LIVE',
    text:
      'Order dan posisi berasal dari akun broker lewat Bridge EA. Environment ' +
      'aplikasi masih demo, jadi dana riil belum aktif.',
  },
  {
    key: 'paper',
    tone: 'paper',
    label: 'PAPER',
    text: 'Statistik dari ledger simulasi strategi: tidak ada uang yang berpindah.',
  },
  {
    key: 'demo',
    tone: 'demo',
    label: 'DEMO',
    text:
      'Mode demo (parameter ?demo=1): seluruh data sintetis, untuk mencoba ' +
      'antarmuka tanpa menyentuh server.',
  },
]

const STATUS = [
  {
    key: 'open',
    tone: 'live',
    label: 'FEED LIVE',
    text: 'Pasar buka dan harga mengalir. Order baru diterima.',
  },
  {
    key: 'closed',
    tone: 'warn',
    label: 'MARKET TUTUP',
    text:
      'Pasar libur atau sesi jeda. Order baru diblokir; posisi yang sudah ' +
      'terbuka tetap dikelola.',
  },
  {
    key: 'unknown',
    tone: 'unknown',
    label: 'UNKNOWN',
    text:
      'Server belum menerima status pasar. Form order menunggu sampai ' +
      'statusnya jelas.',
  },
]

const METRIK = [
  {
    term: 'Equity',
    def: 'Nilai akun saat ini: saldo ditambah laba atau rugi posisi yang masih terbuka.',
  },
  {
    term: 'Winrate',
    def: 'Persentase trade yang sudah tertutup dan berakhir profit.',
  },
  {
    term: 'Profit factor',
    def: 'Total profit dibagi total kerugian; di atas 1 berarti strategi untung.',
  },
  {
    term: 'Max drawdown',
    def: 'Penurunan terbesar dari puncak equity ke titik terendah sesudahnya.',
  },
  {
    term: 'Sharpe',
    def: 'Imbal hasil per unit risiko (volatilitas); makin tinggi, kurva makin halus.',
  },
]

const LANGKAH = [
  {
    title: 'Pilih simbol.',
    text: 'XAUUSD atau BTCUSD, lewat pemilih simbol di Terminal.',
  },
  {
    title: 'Buka form order.',
    text: 'Form Order baru ada di kolom kanan Terminal.',
  },
  {
    title: 'Isi volume dan SL/TP.',
    text: 'Estimasi risiko dalam dolar muncul sebelum order dikirim.',
  },
  {
    title: 'Konfirmasi order.',
    text:
      'Centang pernyataan lalu kirim. Aksi sensitif seperti flatten atau ' +
      'melepas halt meminta kode 2FA terpisah.',
  },
]

export default function Help() {
  return (
    <div className="help-root">
      <header className="help-head">
        <p className="help-kicker">Panduan · Lumine Fund v2</p>
        <h1 className="help-title">Bantuan</h1>
        <p className="help-lede">
          Penjelasan singkat untuk hal yang paling sering ditanyakan: strategi
          yang aktif, arti badge dan status pasar, kill switch, istilah metrik,
          dan langkah mengirim order. Simbol yang diperdagangkan: XAUUSD dan
          BTCUSD.
        </p>
      </header>

      <div className="help-grid">
        <section className="card help-card" aria-labelledby="help-strategi">
          <div className="help-card-head">
            <h2 className="help-card-title" id="help-strategi">Strategi aktif</h2>
            <span className="help-card-note">3 strategi · paper</span>
          </div>
          <div className="help-body">
            <ul className="help-strats">
              {STRATEGI.map((s) => (
                <li className="help-strat" key={s.key}>
                  <div className="help-strat-top">
                    <h3 className="help-strat-name">{s.name}</h3>
                    <span className="help-badge help-badge-paper">PAPER</span>
                  </div>
                  <p className="help-strat-meta">
                    <span className="help-ver">{s.version}</span>
                    <span className="help-dot" aria-hidden="true">·</span>
                    <span>{s.symbol}</span>
                  </p>
                  <p className="help-strat-desc">{s.cara}</p>
                </li>
              ))}
            </ul>
            <p className="help-note">
              Mode paper berarti order dan posisinya memakai uang simulasi,
              bukan dana broker. Statistiknya dicatat di ledger terpisah dan
              tidak bercampur dengan akun LIVE.
            </p>
          </div>
        </section>

        <section className="card help-card" aria-labelledby="help-badge">
          <div className="help-card-head">
            <h2 className="help-card-title" id="help-badge">Arti badge</h2>
            <span className="help-card-note">sumber data</span>
          </div>
          <div className="help-body">
            <ul className="help-defs">
              {BADGE.map((b) => (
                <li className="help-def" key={b.key}>
                  <span className={'help-badge help-badge-' + b.tone}>{b.label}</span>
                  <span className="help-def-text">{b.text}</span>
                </li>
              ))}
            </ul>
            <p className="help-note">
              Badge menandai asal angka, bukan besarnya risiko. Angka paper
              tidak pernah berarti uang nyata.
            </p>
          </div>
        </section>

        <section className="card help-card" aria-labelledby="help-pasar">
          <div className="help-card-head">
            <h2 className="help-card-title" id="help-pasar">Status pasar</h2>
            <span className="help-card-note">gate order</span>
          </div>
          <div className="help-body">
            <ul className="help-defs">
              {STATUS.map((s) => (
                <li className="help-def" key={s.key}>
                  <span className={'help-badge help-badge-' + s.tone}>{s.label}</span>
                  <span className="help-def-text">{s.text}</span>
                </li>
              ))}
            </ul>
            <p className="help-note">
              Order baru diblokir saat pasar tutup karena tidak ada harga yang
              bisa dieksekusi: order berisiko terisi di harga basi atau ditolak
              broker. Jam buka berikutnya ditampilkan di Terminal, tepat di
              samping label status.
            </p>
          </div>
        </section>

        <section className="card help-card" aria-labelledby="help-kill">
          <div className="help-card-head">
            <h2 className="help-card-title" id="help-kill">Kill switch</h2>
            <span className="help-card-note">halt &amp; resume</span>
          </div>
          <div className="help-body">
            <ul className="help-facts">
              <li className="help-fact">
                <strong>Saat halt.</strong> Semua entry baru diblokir, baik
                order manual maupun sinyal strategi. Posisi yang sudah terbuka
                dan exit (TP/SL) tetap berjalan.
              </li>
              <li className="help-fact">
                <strong>Siapa yang bisa resume.</strong> Hanya owner atau admin
                yang login, lewat Pengaturan lalu tab Darurat. Akun service dan
                proses otomatis tidak bisa melepas halt.
              </li>
              <li className="help-fact">
                <strong>Konfirmasi 2FA.</strong> Pelepasan butuh kode 6 digit
                dari aplikasi authenticator. Halt global juga meminta checklist
                pemulihan dicentang lebih dulu.
              </li>
            </ul>
            <p className="help-note">
              Halt standar tidak menutup posisi. Penutupan paksa (flatten)
              adalah aksi terpisah dengan peringatan slippage.
            </p>
          </div>
        </section>

        <section className="card help-card" aria-labelledby="help-metrik">
          <div className="help-card-head">
            <h2 className="help-card-title" id="help-metrik">Istilah metrik</h2>
            <span className="help-card-note">angka statistik</span>
          </div>
          <div className="help-body">
            <dl className="help-metrics">
              {METRIK.map((m) => (
                <div className="help-metric" key={m.term}>
                  <dt className="help-metric-term">{m.term}</dt>
                  <dd className="help-metric-def">{m.def}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section className="card help-card" aria-labelledby="help-order">
          <div className="help-card-head">
            <h2 className="help-card-title" id="help-order">Cara order</h2>
            <span className="help-card-note">4 langkah</span>
          </div>
          <div className="help-body">
            <ol className="help-steps">
              {LANGKAH.map((l, i) => (
                <li className="help-step" key={l.title}>
                  <span className="help-step-num" aria-hidden="true">{i + 1}</span>
                  <span className="help-step-text">
                    <strong>{l.title}</strong> {l.text}
                  </span>
                </li>
              ))}
            </ol>
            <p className="help-note">
              Order hanya bisa dikirim saat status pasar FEED LIVE dan kill
              switch tidak aktif.
            </p>
          </div>
        </section>
      </div>

      <nav className="help-links" aria-label="Halaman terkait">
        <span className="help-links-lead">Halaman terkait</span>
        <Link className="help-link" to="/">
          Terminal<span className="help-link-arrow" aria-hidden="true">→</span>
        </Link>
        <Link className="help-link" to="/agent?tab=strategi">
          Statistik strategi<span className="help-link-arrow" aria-hidden="true">→</span>
        </Link>
        <Link className="help-link" to="/pengaturan?tab=risiko">
          Batas risiko<span className="help-link-arrow" aria-hidden="true">→</span>
        </Link>
      </nav>
    </div>
  )
}
