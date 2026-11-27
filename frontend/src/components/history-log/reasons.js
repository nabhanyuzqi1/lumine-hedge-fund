// Turunan data order untuk halaman "Riwayat & Log".
//
// Sumber tunggal: baris GET /orders (tabel orders + order_events) dan
// GET /orders/{id}. Tidak ada endpoint baru dan tidak ada efek samping:
// semua fungsi di file ini murni supaya bisa diuji langsung.
//
// MASALAH YANG DISELESAIKAN: `fail_reason` menyimpan SEMUA alasan gate yang
// digabung dengan "; " plus kode stage, contoh:
//   "rejected: open exposure 35950.70 exceeds max 30000.00 (open 0.00 +
//    order 35950.70); portfolio: trade risk 72.20 exceeds 0.5% of equity;
//    order rate limit exceeded (stage=risk_gate)"
// Dulu string ini ditempel utuh di kolom RISK sehingga satu baris order bisa
// memuntahkan belasan baris teks. Di sini setiap alasan dipecah menjadi satu
// kalimat pendek berbahasa operasional + satu badge pendek yang stabil.

export const STATUS_LABEL = {
  FILLED: 'Terisi',
  SENT: 'Terkirim',
  DELIVERED: 'Diterima EA',
  RECEIVED: 'Diterima',
  RISK_PASS: 'Lolos risk',
  RISK_FAIL: 'Ditolak risk',
  FAILED: 'Gagal',
  STUCK: 'Macet',
  RECONCILED: 'Terekonsiliasi',
  FILLED_THEN_CLOSED: 'Terisi lalu ditutup',
  ORPHAN_ADOPTED: 'Posisi yatim diadopsi',
  ORPHAN_CLOSED: 'Posisi yatim ditutup',
  CLOSED: 'Ditutup',
  REJECTED: 'Ditolak',
}

export const MODE_LABEL = {
  STOP_NEW_ORDERS: 'tolak order baru',
  STOP_AND_FLATTEN: 'tolak order + tutup posisi',
  PAUSE_STRATEGY: 'jeda strategi',
  GLOBAL_HALT: 'henti total',
}

// Badge RISK yang tampil per baris tabel. Alasan selebihnya diringkas jadi
// tombol "+N" yang membuka drawer.
export const MAX_BADGES = 2

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']

const pad = (value) => String(value).padStart(2, '0')

/* ── angka ──────────────────────────────────────────────────────────────── */

export function toNumber(value) {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  const parsed = Number(String(value).replace(',', '.'))
  return Number.isFinite(parsed) ? parsed : null
}

export function formatNumber(value, digits = 2) {
  const parsed = toNumber(value)
  if (parsed === null) return '·'
  return parsed.toLocaleString('id-ID', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function formatPrice(value) {
  return formatNumber(value, 2)
}

export function formatLot(value) {
  return formatNumber(value, 2)
}

// Persentase: tanpa nol ekor (0,75% bukan 0,750%).
export function formatPercent(value) {
  const parsed = toNumber(value)
  if (parsed === null) return '·'
  return parsed.toLocaleString('id-ID', { maximumFractionDigits: 2 })
}

/* ── waktu ──────────────────────────────────────────────────────────────── */

export function toMs(value) {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  const parsed = new Date(value).getTime()
  return Number.isFinite(parsed) ? parsed : null
}

export function formatTime(ms) {
  const stamp = toMs(ms)
  if (stamp === null) return '·'
  const d = new Date(stamp)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

export function formatStamp(ms) {
  const stamp = toMs(ms)
  if (stamp === null) return '·'
  const d = new Date(stamp)
  return `${pad(d.getDate())} ${MONTHS[d.getMonth()]} ${formatTime(stamp)}`
}

export function formatFull(ms) {
  const stamp = toMs(ms)
  if (stamp === null) return '·'
  const d = new Date(stamp)
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()} · ${formatTime(stamp)}`
}

/* ── harga & slippage ───────────────────────────────────────────────────── */

const POINT_SIZE = { XAUUSD: 0.01, BTCUSD: 0.01 }

// requested: price_requested; fallback payload event pertama. filled:
// price_filled/fill; fallback payload event FILLED. Sama dengan kontrak
// halaman Riwayat lama supaya angka tidak berubah.
export function orderPrices(order) {
  const events = Array.isArray(order?.events) ? order.events : []
  const fillEvent = events.find((e) => e?.state === 'FILLED')
  const firstPayload = events[0]?.payload
  const requested = order?.price_requested ?? order?.requested_price
    ?? (firstPayload && typeof firstPayload === 'object'
      ? firstPayload.price_requested ?? firstPayload.requested ?? firstPayload.price
      : null)
  const filled = order?.fill != null && order.fill > 0
    ? order.fill
    : fillEvent?.payload && typeof fillEvent.payload === 'object'
      ? fillEvent.payload.price ?? fillEvent.payload.fill
      : null
  return {
    requested: toNumber(requested),
    filled: toNumber(filled),
  }
}

export function slippageOf(order) {
  const { requested, filled } = orderPrices(order)
  if (requested === null || filled === null || requested === 0) return null
  const delta = filled - requested
  return { delta, pct: (delta / requested) * 100 }
}

export function formatSlippage(order, slip) {
  if (!slip) return '·'
  const points = slip.delta / (POINT_SIZE[order?.symbol] ?? 0.01)
  const sign = (v) => (v >= 0 ? '+' : '−')
  return `${sign(slip.delta)}${Math.abs(points).toFixed(0)} pts · ${sign(slip.pct)}${Math.abs(slip.pct).toFixed(3)}%`
}

/* ── event order ────────────────────────────────────────────────────────── */

export function orderEvents(order) {
  return Array.isArray(order?.events) ? order.events : []
}

export function executionTime(order) {
  const events = orderEvents(order)
  const fillEvent = events.find((e) => e?.state === 'FILLED')
  return toMs(fillEvent?.t ?? events.at(-1)?.t ?? order?.createdMs)
}

export function createdAt(order) {
  return toMs(order?.createdMs ?? orderEvents(order)[0]?.t)
}

/* ── keputusan risk ─────────────────────────────────────────────────────── */

export function riskDecision(order) {
  let decision = null
  let lastGate = null
  for (const event of orderEvents(order)) {
    const payload = event?.payload
    const risk = payload && typeof payload === 'object' ? payload.risk : null
    if (event?.state === 'RISK_FAIL' || event?.state === 'RISK_PASS' || risk === 'rejected' || risk === 'pass') {
      lastGate = event
    }
    if (event?.state === 'RISK_FAIL' || risk === 'rejected') decision = 'DITOLAK'
    else if ((event?.state === 'RISK_PASS' || risk === 'pass') && decision === null) decision = 'LULUS'
  }
  if (order?.status === 'RISK_FAIL') decision = 'DITOLAK'
  if (!decision && order?.fail_reason) decision = 'DITOLAK'
  return { decision, lastGate }
}

/* ── pengumpulan alasan ─────────────────────────────────────────────────── */

// Kode stage di depan teks ("risk_gate_rejected: ...") dan penanda
// "(stage=risk_gate)" adalah metadata internal, bukan isi alasan.
const CODE_PREFIX = /^[a-z][a-z0-9_]{1,60}:\s+/
const LOOKS_LIKE_DUMP = /^[a-z][a-z0-9_]{1,24}=/

function pushText(out, value) {
  if (value === null || value === undefined) return
  if (Array.isArray(value)) {
    for (const item of value) pushText(out, item)
    return
  }
  if (typeof value === 'object') {
    const candidate = value.label ?? value.message ?? value.reason ?? value.code
    if (candidate !== null && candidate !== undefined && candidate !== '') pushText(out, candidate)
    return
  }
  const text = String(value)
  for (const part of text.split(/;\s+|\n+/)) out.push(part)
}

// Payload lama sempat menyimpan repr dict Python sebagai teks:
// "{'code': 'rejected', 'stage': 'risk_gate', 'message': 'open exposure ...'}".
// Yang dibaca manusia hanya nilai `message`.
function unwrapDictText(text) {
  if (!/^\s*\{/.test(text)) return text
  const quoted = /['"]message['"]\s*:\s*'((?:[^'\\]|\\.)*)'?/.exec(text)
    ?? /['"]message['"]\s*:\s*"((?:[^"\\]|\\.)*)"?/.exec(text)
  return quoted ? quoted[1] : text
}

export function cleanReason(input) {
  let text = unwrapDictText(String(input ?? ''))
  // fail_reason = "code: pesan; pesan (stage=x)": buang penanda stage dan kode.
  text = text.replace(/\(stage=[^()]*\)/gi, ' ')
  // Pecahan repr yang ikut terbawa: "pesan', 'backfilled_at': '...'}".
  text = text.replace(/'\s*,\s*'[a-z_]+'\s*:.*$/i, '')
  text = text.replace(/\s+/g, ' ').trim()
  for (let i = 0; i < 3; i += 1) {
    const dup = /^([a-z][a-z0-9_]{2,24}):\s+\1:\s+/i.exec(text)
    if (dup) {
      text = text.slice(dup[0].length)
      continue
    }
    if (!CODE_PREFIX.test(text)) break
    text = text.replace(CODE_PREFIX, '')
  }
  return text.replace(/[\s.;}{]+$/, '')
}

export function collectReasons(order) {
  const raw = []
  for (const event of orderEvents(order)) {
    const payload = event?.payload
    if (payload && typeof payload === 'object') {
      if (Array.isArray(payload.reasons)) pushText(raw, payload.reasons)
      if (payload.fail) pushText(raw, payload.fail)
      if ((event.state === 'FAILED' || event.state === 'RISK_FAIL') && payload.reason) {
        pushText(raw, payload.reason)
      }
    }
    if (event?.state === 'RISK_FAIL' && event.note) pushText(raw, event.note)
  }
  if (order?.fail_detail) {
    const detail = order.fail_detail
    if (typeof detail === 'string') {
      try {
        const parsed = JSON.parse(detail)
        pushText(raw, parsed?.message ?? detail)
      } catch {
        pushText(raw, detail)
      }
    } else if (typeof detail === 'object') {
      pushText(raw, detail.message)
    }
  }
  if (order?.fail_reason) pushText(raw, order.fail_reason)
  if (Array.isArray(order?.rejected_reasons)) pushText(raw, order.rejected_reasons)

  const out = []
  const seen = new Set()
  for (const item of raw) {
    const text = cleanReason(item)
    if (!text) continue
    // Catatan event hasil normalisasi payload bisa berupa dump "risk=rejected
    // · reasons=..." yang tidak berguna sebagai alasan.
    if (LOOKS_LIKE_DUMP.test(text)) continue
    if (/^[a-z ]+=/.test(text)) continue
    // Potongan sisa split (mis. "portfoli") bukan alasan yang bisa dibaca.
    if (text.length < 10) continue
    const key = text.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
    if (!key || seen.has(key)) continue
    seen.add(key)
    out.push({ text, raw: String(item ?? '') })
  }
  return out
}

/* ── klasifikasi alasan → badge + kalimat ───────────────────────────────── */

function match(text, re) {
  return re.exec(text)
}

function point(value) {
  return formatNumber(value, 2)
}

const RULES = [
  {
    key: 'killswitch',
    re: /kill[-_ ]?switch|kill switch|armed|halt aktif|mode:\s*(?:global_halt|stop_new_orders|stop_and_flatten)/i,
    build: (text) => {
      const mode = match(text, /mode:\s*([A-Z_]+)/i)?.[1]?.toUpperCase()
      const suffix = mode ? ` (mode ${MODE_LABEL[mode] ?? 'aktif'})` : ''
      return { label: 'Kill-Switch', detail: `Kill-switch aktif${suffix}; order baru ditolak.` }
    },
  },
  {
    key: 'no-sl-legs',
    re: /without sl|tanpa sl|leg\(s\) tanpa sl/i,
    build: () => ({
      label: 'Posisi Tanpa SL',
      detail: 'Ada posisi terbuka tanpa SL, jadi order baru diblokir sampai SL terpasang.',
    }),
  },
  {
    key: 'market',
    re: /market closed|market tutup|market sedang tutup|10018/i,
    build: () => ({
      label: 'Market Tutup',
      detail: 'Market sedang tutup; order tidak dapat dieksekusi sekarang.',
    }),
  },
  {
    key: 'timeout',
    re: /timeout|10012|tidak merespons/i,
    build: () => ({
      label: 'Timeout',
      detail: 'Broker tidak merespons tepat waktu; order tidak terkirim.',
    }),
  },
  {
    key: 'calendar',
    re: /kalender|calendar|blackout|high impact|economic event|\bhigh\b.*\bevent\b/i,
    build: () => ({
      label: 'Kalender Berita',
      detail: 'Data kalender ekonomi tidak tersedia; entry diblokir sampai kalender bisa dibaca.',
    }),
  },
  {
    key: 'stale',
    re: /no fresh market data|stale|data basi|tick basi/i,
    build: () => ({
      label: 'Data Basi',
      detail: 'Harga terakhir lebih lama dari batas; order ditahan sampai data segar.',
    }),
  },
  {
    key: 'spread',
    re: /\bspread\b|spread_too_wide|spread terlalu/i,
    build: (text) => {
      const pair = match(text, /spread\s+([\d.,]+)\s*(?:exceeds max|>)\s*([\d.,]+)/i)
      const detail = pair
        ? `Spread ${point(pair[1])} melebihi batas ${point(pair[2])}; order ditahan sampai spread menyempit.`
        : 'Spread pasar melebar di atas batas; order ditahan sampai spread menyempit.'
      return { label: 'Spread', detail }
    },
  },
  {
    key: 'rate',
    re: /rate limit|per menit|per minute|terlalu cepat/i,
    build: () => ({
      label: 'Rate Limit',
      detail: 'Kuota order per menit tercapai; tunggu satu menit sebelum order berikutnya.',
    }),
  },
  {
    key: 'min-lot',
    re: /below min(?:imum)? lot|minimum lot|lot di bawah minimum|lot bawah minimum|min lot/i,
    build: (text) => {
      const min = match(text, /(?:min(?:imum)? lot|minimum)\s*([\d.,]+)/i)?.[1]
      const symbol = match(text, /for\s+([A-Z]{3,10})\b/)?.[1]
      const detail = min
        ? `Lot hasil hitung di bawah minimum ${point(min)}${symbol ? ` untuk ${symbol}` : ''}; risiko tidak bisa dinyatakan dalam lot.`
        : 'Lot order di bawah minimum yang diizinkan broker.'
      return { label: 'Lot < Min', detail }
    },
  },
  {
    key: 'volume',
    re: /\bvolume\b|volume melebihi/i,
    build: (text) => {
      const pair = match(text, /volume\s+([\d.,]+)\s*(?:exceeds max|>|melebihi(?: maks(?:imum)?)?)\s*([\d.,]+)/i)
      const symbol = match(text, /for\s+([A-Z]{3,10})\b/)?.[1]
      const detail = pair
        ? `Volume ${point(pair[1])} lot melebihi maksimum ${point(pair[2])} lot${symbol ? ` untuk ${symbol}` : ''}.`
        : 'Volume order melebihi batas per simbol.'
      return { label: 'Volume > Maks', detail }
    },
  },
  {
    key: 'drawdown',
    re: /drawdown/i,
    build: (text) => {
      const now = match(text, /drawdown\s+([\d.,]+)\s*%/i)?.[1]
      const limit = match(text, /limit\s+([\d.,]+)\s*%/i)?.[1]
      const detail = now && limit
        ? `Drawdown harian ${point(now)}% sudah mencapai batas ${point(limit)}%; order baru dihentikan.`
        : 'Batas drawdown tercapai; order baru dihentikan sampai kondisi pulih.'
      return { label: 'Drawdown', detail }
    },
  },
  {
    key: 'daily-limit',
    re: /daily order limit|order limit|kuota order/i,
    build: (text) => {
      const max = match(text, /max\s+(\d+)\s*\/\s*day/i)?.[1]
      return {
        label: 'Limit Harian',
        detail: max
          ? `Kuota order agent hari ini habis (maksimum ${max} order per hari).`
          : 'Kuota order harian tercapai.',
      }
    },
  },
  {
    key: 'cooldown',
    re: /cooldown|jeda pasca order/i,
    build: (text) => {
      const secs = match(text, /([\d.]+)\s*s\s*remaining/i)?.[1]
      return {
        label: 'Cooldown',
        detail: secs
          ? `Agent masih jeda ${Math.round(Number(secs))} detik sebelum boleh order lagi.`
          : 'Agent masih dalam masa jeda setelah order sebelumnya.',
      }
    },
  },
  {
    key: 'ea-offline',
    re: /ea offline|ea tidak terhubung|terminal ea offline/i,
    build: (text) => {
      const pair = match(text, /offline\s+([\d.]+)\s*s\s*exceeds max\s+([\d.]+)\s*s/i)
      return {
        label: 'EA Offline',
        detail: pair
          ? `Terminal EA tidak terhubung ${Math.round(Number(pair[1]))} detik (batas ${Math.round(Number(pair[2]))} detik).`
          : 'Terminal EA tidak terhubung; order baru ditahan.',
      }
    },
  },
  {
    key: 'agent-paused',
    re: /paused|dijeda|pause/i,
    build: (text) => {
      const reason = match(text, /paused:\s*(.+)$/i)?.[1]
      return {
        label: 'Agent Dijeda',
        detail: reason
          ? `Agent LLM sedang dijeda: ${reason}.`
          : 'Agent LLM sedang dijeda oleh pemutus otomatis.',
      }
    },
  },
  {
    key: 'sl-tp',
    re: /requires sl|requires tp|sl is mandatory|tp is mandatory|sl\/tp/i,
    build: () => ({
      label: 'SL/TP Salah',
      detail: 'SL atau TP tidak masuk akal untuk sisi order ini (BUY wajib SL < harga < TP).',
    }),
  },
  {
    key: 'sl-distance',
    re: /sl distance|jarak sl/i,
    build: (text) => {
      const parts = match(text, /sl distance\s+([\d.]+)\s+(below min|exceeds max)\s+([\d.]+)(?:\s+for\s+([A-Z]{3,10}))?/i)
      if (!parts) return { label: 'SL Jauh', detail: 'Jarak SL di luar rentang yang diizinkan untuk simbol ini.' }
      const below = /below/i.test(parts[2])
      return {
        label: below ? 'SL Dekat' : 'SL Jauh',
        detail: `Jarak SL ${point(parts[1])} ${below ? 'di bawah minimum' : 'melebihi maksimum'} ${point(parts[3])}${parts[4] ? ` untuk ${parts[4]}` : ''}.`,
      }
    },
  },
  {
    key: 'stress',
    re: /stress loss|skenario stres/i,
    build: (text) => {
      const actual = match(text, /stress loss\s+([\d.,]+)/i)?.[1]
      const pct = match(text, /([\d.,]+)\s*%\s*of equity/i)?.[1]
      const cap = match(text, /\(([\d.,]+)\)\s*$/)?.[1]
      return {
        label: 'Stress Loss',
        detail: `Skenario stres: kerugian ${point(actual)} melebihi ${point(pct)}% ekuitas${cap ? ` (maksimum ${point(cap)})` : ''}.`,
      }
    },
  },
  {
    key: 'concentration',
    re: /concentration|konsentrasi/i,
    build: (text) => {
      const symbol = match(text, /concentration\s+([A-Z]{3,10})\b/i)?.[1]
      const actual = match(text, /risk\s+([\d.,]+)/i)?.[1]
      const pct = match(text, /([\d.,]+)\s*%\s*of equity/i)?.[1]
      return {
        label: 'Konsentrasi',
        detail: `Konsentrasi${symbol ? ` ${symbol}` : ''} ${point(actual)} melebihi ${point(pct)}% ekuitas.`,
      }
    },
  },
  {
    key: 'margin',
    re: /margin/i,
    build: (text) => {
      const actual = match(text, /margin used\s+([\d.,]+)/i)?.[1]
      const pct = match(text, /([\d.,]+)\s*%\s*of equity/i)?.[1]
      const cap = match(text, /\(([\d.,]+)\)\s*$/)?.[1]
      return {
        label: 'Margin',
        detail: `Margin terpakai ${point(actual)} melebihi ${point(pct)}% ekuitas${cap ? ` (maksimum ${point(cap)})` : ''}.`,
      }
    },
  },
  {
    key: 'max-positions',
    re: /max positions|max posisi|jumlah posisi maksimum/i,
    build: (text) => {
      const open = match(text, /open\s+(\d+)/i)?.[1]
      const max = match(text, /max\s+(\d+)/i)?.[1]
      return {
        label: 'Max Posisi',
        detail: open && max
          ? `Jumlah posisi strategi sudah maksimum (${open} dari ${max}).`
          : 'Jumlah posisi strategi sudah maksimum.',
      }
    },
  },
  {
    key: 'strategy-loss',
    re: /daily loss limit|batas rugi/i,
    build: (text) => {
      const pnl = match(text, /pnl\s+(-?[\d.,]+)/i)?.[1]
      return {
        label: 'Batas Rugi',
        detail: pnl
          ? `Batas rugi harian strategi tercapai (PnL ${point(pnl)}).`
          : 'Batas rugi harian strategi tercapai.',
      }
    },
  },
  {
    key: 'risk',
    re: /trade risk|open risk|risk per trade|risiko per trade|risk\s+.*\bexceeds\b/i,
    build: (text) => {
      const actual = match(text, /risk(?: per trade)?\s*:?\s*([\d.,]+)/i)?.[1]
        ?? match(text, /risiko(?: transaksi)?\s*:?\s*([\d.,]+)/i)?.[1]
      const pct = match(text, /(?:batas|>|melebihi)\s*([\d.,]+)\s*%/i)?.[1]
        ?? match(text, /([\d.,]+)\s*%\s*(?:of equity|ekuitas)/i)?.[1]
      const cap = match(text, /\(([\d.,]+)\)\s*$/)?.[1]
      const label = pct ? `Risk > ${formatPercent(pct)}%` : 'Risk Berlebih'
      const head = actual ? `Risiko transaksi ${point(actual)}` : 'Risiko transaksi'
      const tail = pct ? `melebihi batas ${formatPercent(pct)}% ekuitas` : 'melebihi batas ekuitas'
      const capText = cap ? ` (maksimum ${point(cap)})` : ''
      return { label, detail: `${head} ${tail}${capText}.` }
    },
  },
  {
    key: 'exposure',
    re: /exposure|eksposur/i,
    build: (text) => {
      const pair = match(text, /exposure\s+([\d.,]+)\s*exceeds max\s+([\d.,]+)/i)
      const detail = pair
        ? `Exposure terbuka ${point(pair[1])} melebihi batas ${point(pair[2])}.`
        : 'Exposure terbuka melebihi batas akun.'
      return { label: 'Max Exposure', detail }
    },
  },
  {
    key: 'symbol',
    re: /not allowed|not supported|tidak diizinkan/i,
    build: (text) => {
      const symbol = match(text, /symbol\s+([A-Z]{3,10})/i)?.[1]
      return {
        label: 'Simbol Ditolak',
        detail: symbol
          ? `Simbol ${symbol} tidak diizinkan untuk akun ini.`
          : 'Simbol order tidak diizinkan untuk akun ini.',
      }
    },
  },
  {
    key: 'no-spec',
    re: /no risk spec|tanpa aturan|belum punya aturan/i,
    build: () => ({
      label: 'Tanpa Aturan',
      detail: 'Simbol ini belum punya aturan risiko, jadi order diblokir.',
    }),
  },
  {
    key: 'degradation',
    re: /degrad/i,
    build: () => ({
      label: 'Degradasi',
      detail: 'Strategi berstatus degradasi: entry baru diblokir sampai pulih.',
    }),
  },
  {
    key: 'qa',
    re: /^qa-|qa fixture|fixture qa/i,
    build: () => ({
      label: 'Data Uji',
      detail: 'Order uji QA, bukan trafik trading live.',
    }),
  },
  {
    key: 'llm-position',
    re: /llm_position_exists|posisi llm (?:open|terbuka)|position existing/i,
    build: (text) => {
      const symbol = /\b([A-Z]{3,10})\b/.exec(text.replace(/LLM|OPEN|BE|TP|SL/g, ' '))?.[1]
      return {
        label: 'Posisi LLM Ada',
        detail: `Sudah ada posisi LLM terbuka${symbol ? ` di ${symbol}` : ''}; order baru ditahan.`,
      }
    },
  },
  {
    key: 'ea-no-result',
    re: /no ea result|ea tidak mengirim hasil/i,
    build: () => ({
      label: 'Tanpa Hasil EA',
      detail: 'EA tidak mengirim hasil eksekusi; order dianggap gagal.',
    }),
  },
  {
    key: 'position-missing',
    re: /position not found|posisi tidak ditemukan/i,
    build: () => ({
      label: 'Posisi Tidak Ada',
      detail: 'Posisi tidak ditemukan di broker saat order diproses.',
    }),
  },
  {
    key: 'broker-reject',
    re: /ordersend .*failed|retcode=\d+|broker menolak/i,
    build: () => ({
      label: 'Ditolak Broker',
      detail: 'Broker menolak permintaan eksekusi order.',
    }),
  },
  {
    key: 'invalid-intent',
    re: /gunakan (?:cut|sl|be|tp)/i,
    build: () => ({
      label: 'Perintah Tidak Valid',
      detail: 'Perintah tidak termasuk aksi yang diizinkan: cut, SL, BE, TP, layer, atau hold.',
    }),
  },
]

function shorten(text, max = 22) {
  const clean = String(text ?? '').trim()
  if (clean.length <= max) return clean
  const cut = clean.slice(0, max)
  const space = cut.lastIndexOf(' ')
  return `${(space > 8 ? cut.slice(0, space) : cut).trim()}…`
}

function sentence(text) {
  const clean = String(text ?? '').trim()
  if (!clean) return 'Alasan tidak dirinci.'
  const body = clean.charAt(0).toUpperCase() + clean.slice(1)
  return /[.!?]$/.test(body) ? body : `${body}.`
}

function capitalize(text) {
  const clean = String(text ?? '').trim()
  if (!clean) return clean
  return clean.charAt(0).toUpperCase() + clean.slice(1)
}

export function classifyReason(text) {
  for (const rule of RULES) {
    if (!rule.re.test(text)) continue
    const built = rule.build(text)
    return { key: rule.key, label: built.label, detail: built.detail }
  }
  return { key: 'other', label: capitalize(shorten(text, 22)) || 'Alasan lain', detail: sentence(text) }
}

function groupByLabel(items) {
  const groups = []
  const index = new Map()
  for (const item of items) {
    const existing = index.get(item.label)
    if (existing) {
      existing.items.push(item)
      continue
    }
    const group = { key: item.key, label: item.label, items: [item] }
    index.set(item.label, group)
    groups.push(group)
  }
  return groups
}

// Hasil lengkap satu order: keputusan risk, seluruh alasan terklasifikasi,
// dan badge yang boleh tampil di tabel (maksimum MAX_BADGES).
export function analyzeOrder(order) {
  const reasons = collectReasons(order)
  const items = []
  const seen = new Set()
  for (const entry of reasons) {
    const item = { ...classifyReason(entry.text), raw: entry.text }
    const key = `${item.label}|${item.detail}`
    // Alasan yang sama bisa terekam di event DAN di fail_reason: cukup sekali.
    if (seen.has(key)) continue
    seen.add(key)
    items.push(item)
  }
  const deduped = []
  for (const item of items) {
    const norm = (value) => value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
    const same = deduped.find((other) => other.label === item.label)
    if (!same) {
      deduped.push(item)
      continue
    }
    const a = norm(same.detail)
    const b = norm(item.detail)
    // Varian ringkas dari alasan yang sama ("... maksimum 0,10 lot" vs
    // "... maksimum 0,10 lot untuk XAUUSD") cukup satu.
    if (a.includes(b)) continue
    if (b.includes(a)) deduped[deduped.indexOf(same)] = item
  }
  const groups = groupByLabel(deduped)
  const verdict = riskDecision(order).decision
  return {
    verdict,
    items: deduped,
    groups,
    badges: groups.slice(0, MAX_BADGES).map((group) => ({ key: group.key, label: group.label })),
    hidden: Math.max(0, groups.length - MAX_BADGES),
  }
}
