import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { desk, toast } from '../lib/api'
import { useDesk } from '../lib/useDesk'
import {
  SYMBOLS,
  MARKET_CLOSED_MSG,
  isMarketClosed,
  isMarketClosedError,
  useMarketStatus,
} from '../lib/market'
import ConfirmDialog from './ConfirmDialog'

const SESSION_LABEL = { asia: 'Asia', london: 'London', ny: 'New York', sydney: 'Sydney' }

// Preset volume (lot) — hanya mengisi state volume, tidak menambah aturan
// validasi: batas 0..5 lot tetap milik risk gate.
const LOT_PRESETS = ['0.01', '0.05', '0.10', '0.25', '0.50']

// Keadaan buka/tutup kartu order disimpan per browser. Default: TERTUTUP di
// mobile (layar kecil -> chart dulu), TERBUKA di desktop >=1024px.
const OPEN_KEY = 'term.order.open'
const DESKTOP_QUERY = '(min-width: 1024px)'

function readOpenPref() {
  try {
    const v = localStorage.getItem(OPEN_KEY)
    if (v === '1') return true
    if (v === '0') return false
  } catch {
    // localStorage bisa diblokir (mode privat): jatuh ke default viewport.
  }
  return typeof window !== 'undefined' && window.matchMedia(DESKTOP_QUERY).matches
}

function writeOpenPref(open) {
  try {
    localStorage.setItem(OPEN_KEY, open ? '1' : '0')
  } catch {
    // tidak persisten: keadaan tetap berlaku untuk sesi ini
  }
}

export function SessionBadges({ sessions }) {
  const all = ['asia', 'london', 'ny']
  return (
    <div className="sessions" aria-label="Sesi likuiditas">
      {all.map((s) => {
        const on = sessions?.includes(s)
        return (
          <span key={s} className={`session ${on ? 'session-on' : ''}`}>
            <i />
            {SESSION_LABEL[s]}
          </span>
        )
      })}
    </div>
  )
}

// Angka dolar ringkas untuk baris P/L: <1000 tetap 2 desimal, di atasnya
// dibulatkan supaya satu baris tidak meluber di kolom sempit.
function fmtUsd(v) {
  return v >= 1000 ? Math.round(v).toLocaleString('id-ID') : v.toFixed(2)
}

export default function OrderForm() {
  const state = useDesk()
  const symbol = state?.symbol
  if (!symbol) return null
  // key={symbol}: ganti simbol = ganti satuan harga, jadi seluruh state form
  // (SL/TP/touched/konfirmasi) di-reset oleh React tanpa efek tambahan agar
  // angka simbol lama tidak terkirim ke simbol baru.
  return <OrderFormBody key={symbol} state={state} symbol={symbol} />
}

function OrderFormBody({ state, symbol }) {
  const quote = state?.quotes?.[symbol]
  // Metadata simbol mengikuti simbol terpilih: jarak hint SL/TP dan kontrak
  // risiko berbeda per simbol (XAU 100 oz/lot, BTC 1 coin/lot).
  const cfg = SYMBOLS[symbol] || Object.values(SYMBOLS)[0]
  // Pasar tutup: tombol Kirim nonaktif dan form menjelaskan alasannya.
  const market = useMarketStatus(symbol)
  const marketClosed = isMarketClosed(market)

  const [side, setSide] = useState('buy')
  const [volume, setVolume] = useState('0.10')
  const [sl, setSl] = useState('')
  const [tp, setTp] = useState('')
  const [touched, setTouched] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [sending, setSending] = useState(false)
  // Pesan 409 dari server (code=market_closed) — sama dengan pesan tombol
  // nonaktif, tanpa retry otomatis.
  const [closedNotice, setClosedNotice] = useState('')
  // Kartu order dua keadaan: ringkas (satu baris) / terbuka (form penuh).
  const [open, setOpen] = useState(readOpenPref)
  const cardRef = useRef(null)

  // Preferensi ditulis HANYA saat user menekan toggle. Menulis saat mount
  // akan mengunci default viewport (mis. tab dibuka kecil lalu diperbesar)
  // menjadi pilihan permanen yang tidak pernah diminta user.
  const scrollOnOpenRef = useRef(false)

  function toggleOpen() {
    setOpen((v) => {
      const next = !v
      writeOpenPref(next)
      // Mobile: form ±540px lebih tinggi dari layar, jadi membuka kartu harus
      // ikut menggeser layar (seperti sheet aplikasi). Desktop tidak perlu:
      // kartu ada di kolom kanan yang sticky.
      scrollOnOpenRef.current = next && typeof window !== 'undefined'
        && window.matchMedia('(max-width: 1023px)').matches
      return next
    })
  }

  // Geser setelah DOM form terpasang (useLayoutEffect: berjalan sebelum paint,
  // tidak bergantung timer/rAF yang di-throttle saat tab background).
  useLayoutEffect(() => {
    if (!open || !scrollOnOpenRef.current) return
    scrollOnOpenRef.current = false
    const card = cardRef.current
    if (!card) return
    const bar = document.querySelector('.term-sysbar')
    const topbar = document.querySelector('.topbar')
    const hdr = document.querySelector('.term-hdr')
    const topOffset = (topbar ? topbar.offsetHeight : 48) + (hdr ? hdr.offsetHeight : 0) + 10
    const y0 = window.scrollY
    const cardTop = card.getBoundingClientRect().top + y0
    let target = Math.max(0, cardTop - topOffset)
    // Kalau kartu menempel di bawah header membuat tombol Kirim jatuh di balik
    // bar status, geser sekali lagi sampai CTA terlihat penuh.
    const cta = card.querySelector('.term-cta')
    if (cta && bar) {
      const ctaBottom = cta.getBoundingClientRect().bottom + y0
      const room = window.innerHeight - bar.offsetHeight - 12
      if (ctaBottom - target > room) target = ctaBottom - room
    }
    // Instan, bukan smooth: membuka sheet harus langsung menempatkan tombol
    // Kirim di tempat yang bisa ditekan (animasi halus membuat aksi tertunda).
    window.scrollTo({ top: target, behavior: 'auto' })
  }, [open])

  const vol = parseFloat(volume)
  const slN = parseFloat(sl)
  const tpN = parseFloat(tp)
  const price = quote?.price

  const errors = useMemo(() => {
    const e = {}
    if (!vol || vol <= 0) e.volume = 'Volume harus lebih dari 0'
    if (vol > 5) e.volume = 'Melebihi batas volume (maks 5.0 lot)'
    if (!slN) e.sl = 'Stop loss wajib diisi'
    else if (price && ((side === 'buy' && slN >= price) || (side === 'sell' && slN <= price)))
      e.sl = side === 'buy' ? 'SL harus di bawah harga sekarang' : 'SL harus di atas harga sekarang'
    if (!tpN) e.tp = 'Take profit wajib diisi'
    else if (price && ((side === 'buy' && tpN <= price) || (side === 'sell' && tpN >= price)))
      e.tp = side === 'buy' ? 'TP harus di atas harga sekarang' : 'TP harus di bawah harga sekarang'
    return e
  }, [vol, slN, tpN, price, side])

  const valid = Object.keys(errors).length === 0
  // Harga eksekusi yang BENAR untuk sisi ini: beli kena ASK, jual kena BID.
  // Dipakai hanya untuk preview risiko di UI; gate risiko tetap dihitung
  // server dengan harga tick otoritatif.
  const entry = (side === 'buy' ? quote?.ask : quote?.bid) ?? price
  const riskUsd = vol && slN && entry ? Math.abs(entry - slN) * vol * cfg.contract : null
  const rewardUsd = vol && tpN && entry ? Math.abs(tpN - entry) * vol * cfg.contract : null
  const rr = riskUsd && rewardUsd && riskUsd > 0 ? rewardUsd / riskUsd : null
  const riskPct = riskUsd && state?.equity ? (riskUsd / state.equity) * 100 : null
  const slHint = price ? (side === 'buy' ? price - cfg.slDist : price + cfg.slDist).toFixed(cfg.digits) : ''
  const tpHint = price ? (side === 'buy' ? price + cfg.tpDist : price - cfg.tpDist).toFixed(cfg.digits) : ''

  function submit(e) {
    e.preventDefault()
    setTouched(true)
    if (marketClosed) {
      // Jangan buka dialog konfirmasi saat pasar tutup: tidak ada yang bisa
      // dikirim, dan user harus melihat alasan yang eksplisit.
      setClosedNotice(MARKET_CLOSED_MSG)
      return
    }
    if (!valid) return
    setConfirming(true)
  }

  async function send() {
    setSending(true)
    try {
      const o = await desk.placeOrder({ symbol, side, volume: vol, sl: slN, tp: tpN })
      setConfirming(false)
      setSl('')
      setTp('')
      setTouched(false)
      setClosedNotice('')
      toast(`Order ${o.id} dikirim`, `${side === 'buy' ? 'BELI' : 'JUAL'} ${symbol} ${vol.toFixed(2)} lot · SL ${slN.toFixed(cfg.digits)} · TP ${tpN.toFixed(cfg.digits)} · status: ${o.status}`, o.status === 'FILLED' ? 'up' : '')
    } catch (ex) {
      // HTTP 409 code=market_closed: tampilkan pesan yang sama dengan tombol
      // nonaktif, tutup dialog, dan JANGAN mengulang submit.
      if (isMarketClosedError(ex)) {
        setClosedNotice(MARKET_CLOSED_MSG)
        setConfirming(false)
        toast('Order ditolak', MARKET_CLOSED_MSG, 'down')
        return
      }
      // Dilempar agar ConfirmDialog menampilkan error inline (dialog tetap terbuka).
      throw new Error(ex.message === 'DEMO' ? 'Order tidak tersedia di mode demo' : ex.message)
    } finally {
      setSending(false)
    }
  }

  if (!symbol) return null

  if (state?.halted) {
    return (
      <section className="card orderform term-order is-halted" aria-label={`Order baru ${symbol}`}>
        <div className="term-order-bar">
          <div className="term-order-sum">
            <span className="term-order-sym">{symbol}</span>
            <span className="term-order-state">HALT</span>
          </div>
        </div>
        <p className="term-order-halted">
          Kill-switch aktif: order baru diblokir. Posisi terbuka tidak terpengaruh. Lepas dari chip
          kill-switch di header.
        </p>
      </section>
    )
  }

  return (
    <>
      <form
        ref={cardRef}
        className={`card orderform term-order ${open ? 'is-open' : 'is-collapsed'}`.trim()}
        onSubmit={submit}
        noValidate
        aria-label={`Order baru ${symbol}`}
      >
        {/* Baris ringkas: selalu terlihat, satu baris, satu tombol 44px. */}
        <div className="term-order-bar">
          <div className="term-order-sum">
            <span className="term-order-sym">{symbol}</span>
            <span className={`term-order-side ${side === 'buy' ? 'is-buy' : 'is-sell'}`}>
              {side === 'buy' ? 'BELI' : 'JUAL'}
            </span>
            <span className="term-order-vol num">{volume || '·'} lot</span>
            {marketClosed && <span className="term-order-state">TUTUP</span>}
          </div>
          <button
            type="button"
            className={`term-order-toggle ${side === 'buy' ? 'is-buy' : 'is-sell'}`.trim()}
            aria-expanded={open}
            aria-controls="term-order-body"
            onClick={toggleOpen}
            title={open ? 'Sembunyikan form order' : 'Buka form order'}
          >
            {open ? 'Tutup' : 'Order'}
            <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d={open ? 'M6 15l6-6 6 6' : 'M6 9l6 6 6-6'} />
            </svg>
          </button>
        </div>

        {open && (
          <div className="orderform-body term-order-body" id="term-order-body">
            {/* Segmented Beli/Jual full-width: emerald = beli, crimson = jual */}
            <div className="side-toggle term-side" role="radiogroup" aria-label="Arah order">
              <button type="button" role="radio" aria-checked={side === 'buy'} className={`side-btn side-buy ${side === 'buy' ? 'is-active' : ''}`} onClick={() => setSide('buy')}>
                Beli
              </button>
              <button type="button" role="radio" aria-checked={side === 'sell'} className={`side-btn side-sell ${side === 'sell' ? 'is-active' : ''}`} onClick={() => setSide('sell')}>
                Jual
              </button>
            </div>

            {/* Harga kedua sisi selalu terlihat; sisi yang dipakai order diberi
                penanda kontras supaya trader tidak salah baca ask vs bid. */}
            <div className="term-price-pair">
              <div className={`term-price-cell ${side === 'buy' ? 'is-on is-buy' : ''}`.trim()}>
                <span className="term-price-key">ASK</span>
                <span className="term-price-val num">{quote?.ask != null ? quote.ask.toFixed(cfg.digits) : '·'}</span>
              </div>
              <div className={`term-price-cell ${side === 'sell' ? 'is-on is-sell' : ''}`.trim()}>
                <span className="term-price-key">BID</span>
                <span className="term-price-val num">{quote?.bid != null ? quote.bid.toFixed(cfg.digits) : '·'}</span>
              </div>
            </div>

            <div className="field term-vol">
              <label className="field-label" htmlFor="term-volume">Volume <span className="term-unit">lot</span></label>
              <input
                id="term-volume"
                className={`input num ${touched && errors.volume ? 'input-error' : ''}`}
                inputMode="decimal"
                value={volume}
                onChange={(e) => setVolume(e.target.value)}
              />
              <div className="term-presets" role="group" aria-label="Preset volume lot">
                {LOT_PRESETS.map((v) => (
                  <button
                    key={v}
                    type="button"
                    className={`term-preset ${volume === v ? 'is-active' : ''}`.trim()}
                    aria-pressed={volume === v}
                    onClick={() => setVolume(v)}
                  >
                    {v}
                  </button>
                ))}
              </div>
              {touched && errors.volume && <span className="field-error">{errors.volume}</span>}
            </div>

            <div className="field-pair term-sl-tp">
              <label className="field">
                <span className="field-label">Stop loss <span className="req term-req">wajib</span></span>
                <input
                  className={`input num ${touched && errors.sl ? 'input-error' : ''}`}
                  inputMode="decimal"
                  placeholder={slHint}
                  value={sl}
                  onChange={(e) => setSl(e.target.value)}
                />
                {touched && errors.sl && <span className="field-error">{errors.sl}</span>}
              </label>
              <label className="field">
                <span className="field-label">Take profit <span className="req term-req">wajib</span></span>
                <input
                  className={`input num ${touched && errors.tp ? 'input-error' : ''}`}
                  inputMode="decimal"
                  placeholder={tpHint}
                  value={tp}
                  onChange={(e) => setTp(e.target.value)}
                />
                {touched && errors.tp && <span className="field-error">{errors.tp}</span>}
              </label>
            </div>

            {/* Preview risiko & R:R: dihitung dari lot, harga sisi ini
                (ASK/BID), SL dan TP yang sedang diisi. Angka hilang bila
                input belum lengkap — tidak ada nilai karangan. */}
            <div className="term-risk-line num" aria-label="Estimasi profit, loss, dan risk reward">
              <div className="term-risk-cell" title={riskPct != null ? `Risiko ${riskPct.toFixed(2)}% dari equity` : 'Estimasi loss bila SL kena'}>
                <span className="term-risk-k">P</span>
                <b className="up-text">{rewardUsd != null ? `+$${fmtUsd(rewardUsd)}` : '·'}</b>
              </div>
              <div className="term-risk-cell" title="Estimasi loss bila SL kena">
                <span className="term-risk-k">L</span>
                <b className="down-text">{riskUsd != null ? `-$${fmtUsd(riskUsd)}` : '·'}</b>
              </div>
              <div className="term-risk-cell" title="Risk : Reward">
                <span className="term-risk-k">RR</span>
                <b className={rr != null && rr >= 2 ? 'up-text' : ''}>{rr != null ? `1:${rr.toFixed(2)}` : '·'}</b>
              </div>
            </div>

            {(marketClosed || closedNotice) && (
              <p className="term-closed-notice" role="status">
                <span className="term-closed-dot" aria-hidden="true" />
                {MARKET_CLOSED_MSG}
              </p>
            )}

            <button
              className={`btn btn-order term-cta ${side === 'buy' ? 'is-buy' : 'is-sell'}`}
              type="submit"
              disabled={sending || marketClosed}
              aria-disabled={sending || marketClosed}
              title={marketClosed ? MARKET_CLOSED_MSG : undefined}
            >
              {sending ? 'Mengirim…' : `Kirim order · ${side === 'buy' ? 'BELI' : 'JUAL'}`}
            </button>
            <p className="field-hint term-order-foot">
              SL dan TP wajib. Order market langsung dikirim ke broker dan tidak bisa dibatalkan.
            </p>
          </div>
        )}
      </form>

      {confirming && (
        <ConfirmDialog
          open={confirming}
          title={`Kirim order ${side === 'buy' ? 'BELI' : 'JUAL'} · ${symbol}`}
          description="Periksa sekali lagi: order market langsung dikirim ke broker."
          consequences={[
            `${side === 'buy' ? 'Beli' : 'Jual'} ${vol.toFixed(2)} lot ${symbol} di harga pasar sekarang (${(side === 'buy' ? quote?.ask : quote?.bid)?.toFixed(cfg.digits) ?? '·'})`,
            'Order market: harga eksekusi bisa berbeda dari harga layar (slippage), apalagi pasar cepat',
            riskUsd != null
              ? `Risiko jika SL kena: $${riskUsd.toFixed(2)}${riskPct != null ? ` (${riskPct.toFixed(2)}% equity)` : ''}`
              : 'Stop loss wajib terpasang sebagai batas rugi',
            'Order yang sudah terkirim tidak bisa dibatalkan',
          ]}
          ackLabel="Saya paham order ini langsung dikirim ke broker dan tidak bisa dibatalkan"
          confirmLabel="Ya, kirim order"
          busy={sending}
          onCancel={() => { if (!sending) setConfirming(false) }}
          onConfirm={send}
        >
          <dl className="dialog-rows">
            <div className="dialog-row"><dt>Arah</dt><dd className={side === 'buy' ? 'up-text' : 'down-text'}>{side === 'buy' ? 'BELI' : 'JUAL'} {symbol}</dd></div>
            <div className="dialog-row"><dt>Volume</dt><dd>{vol.toFixed(2)} lot</dd></div>
            <div className="dialog-row"><dt>Harga pasaran</dt><dd>{(side === 'buy' ? quote?.ask : quote?.bid)?.toFixed(cfg.digits)}</dd></div>
            <div className="dialog-row"><dt>Stop loss</dt><dd className="down-text">{slN.toFixed(cfg.digits)}</dd></div>
            <div className="dialog-row"><dt>Take profit</dt><dd className="up-text">{tpN.toFixed(cfg.digits)}</dd></div>
            {riskUsd != null && <div className="dialog-row"><dt>Risiko maksimum</dt><dd>${riskUsd.toFixed(2)}</dd></div>}
          </dl>
        </ConfirmDialog>
      )}
    </>
  )
}
