// Pemformatan angka, waktu, dan ukuran untuk halaman Pengaturan.
// Semua tampilan memakai lokal id-ID supaya angka desimal memakai koma.

const numberFmt = (digits) => new Intl.NumberFormat('id-ID', {
  minimumFractionDigits: digits,
  maximumFractionDigits: digits,
})

// Untuk batas rentang: nol di belakang koma tidak perlu dipaksakan.
const boundFmt = (digits) => new Intl.NumberFormat('id-ID', { maximumFractionDigits: digits })

export function fmtNum(value, digits = 2) {
  if (value == null || value === '') return '·'
  const n = Number(value)
  if (!Number.isFinite(n)) return '·'
  return numberFmt(digits).format(n)
}

export function fmtValue(value, unit = '', digits = 2) {
  const text = fmtNum(value, digits)
  if (text === '·') return text
  return unit ? `${text} ${unit}` : text
}

// Batas rentang ditulis sesuai besarannya: 0,0001 tetap terbaca, 1.000.000
// tidak dipaksa empat desimal.
function fmtBound(value) {
  if (value == null) return '·'
  const n = Number(value)
  if (!Number.isFinite(n)) return '·'
  const digits = Number.isInteger(n) ? 0 : Math.abs(n) < 1 ? 4 : 2
  return boundFmt(digits).format(n)
}

export function fmtRange(min, max) {
  if (min == null || max == null) return ''
  return `${fmtBound(min)}–${fmtBound(max)}`
}

export function fmtTime(iso) {
  if (!iso) return '·'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '·'
  return d.toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })
}

export function fmtShortTime(iso) {
  if (!iso) return '·'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '·'
  return d.toLocaleString('id-ID', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export function fmtAge(seconds) {
  if (seconds == null) return '·'
  const s = Math.max(0, Number(seconds))
  if (!Number.isFinite(s)) return '·'
  if (s < 90) return `${Math.round(s)} detik`
  if (s < 5400) return `${Math.round(s / 60)} menit`
  if (s < 172800) return `${Math.round(s / 3600)} jam`
  return `${Math.round(s / 86400)} hari`
}

export function fmtBytes(bytes) {
  if (bytes == null) return '·'
  const b = Number(bytes)
  if (!Number.isFinite(b)) return '·'
  if (b >= 1e9) return `${(b / 1e9).toFixed(2)} GB`
  if (b >= 1e6) return `${(b / 1e6).toFixed(1)} MB`
  if (b >= 1e3) return `${(b / 1e3).toFixed(0)} KB`
  return `${Math.round(b)} B`
}

// "12.500,50", "0,05", atau "0.05" -> angka; kosong -> null; bukan angka -> NaN.
// Koma dianggap pemisah desimal (kebiasaan id-ID): titik lain jadi pemisah
// ribuan. Tanpa koma, titik diperlakukan sebagai desimal (0.05 tetap 0,05).
export function parseDraft(raw) {
  if (raw == null) return null
  let s = String(raw).trim().replace(/\s/g, '')
  if (s === '') return null
  if (s.includes(',')) s = s.replace(/\./g, '').replace(',', '.')
  const n = Number(s)
  return Number.isFinite(n) ? n : NaN
}
