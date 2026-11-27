// Format angka, waktu, dan teks untuk halaman Agent & Strategi.
// Semua label di sini dipakai langsung di UI: bahasa Indonesia, tanpa istilah
// internal (nama endpoint, kode status, id teknis).
import { useEffect, useState } from 'react'

export const DASH = '—'

export function money(value) {
  if (value == null || value === '') return DASH
  const n = Number(value)
  if (!Number.isFinite(n)) return DASH
  return `$${n.toLocaleString('id-ID', { maximumFractionDigits: 0 })}`
}

export function pct(value, digits = 1) {
  if (value == null || value === '') return DASH
  const n = Number(value)
  if (!Number.isFinite(n)) return DASH
  return `${(n * 100).toLocaleString('id-ID', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`
}

export function signedPct(value, digits = 1) {
  if (value == null || value === '') return DASH
  const n = Number(value)
  if (!Number.isFinite(n)) return DASH
  const body = `${Math.abs(n).toLocaleString('id-ID', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`
  if (n > 0) return `+${body}`
  if (n < 0) return `-${body}`
  return body
}

export function dec(value, digits = 2) {
  if (value == null || value === '') return DASH
  const n = Number(value)
  if (!Number.isFinite(n)) return DASH
  return n.toLocaleString('id-ID', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function relativeTime(ms, now = Date.now()) {
  if (ms == null) return DASH
  const diff = Number(now) - Number(ms)
  if (!Number.isFinite(diff)) return DASH
  const s = Math.max(0, Math.round(diff / 1000))
  if (s < 10) return 'baru saja'
  if (s < 60) return `${s} dtk lalu`
  if (s < 3600) return `${Math.floor(s / 60)} mnt lalu`
  if (s < 86400) return `${Math.floor(s / 3600)} jam lalu`
  return `${Math.floor(s / 86400)} hari lalu`
}

const CLOCK = new Intl.DateTimeFormat('id-ID', {
  day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
})

export function clockLabel(ms) {
  if (ms == null) return DASH
  const d = new Date(ms)
  if (Number.isNaN(d.getTime())) return DASH
  return CLOCK.format(d)
}

export function dateLabel(iso) {
  if (!iso) return DASH
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return DASH
  return CLOCK.format(d)
}

// Interval siklus dalam satuan terbesar yang membagi habis (300 -> "5 menit").
export function intervalLabel(seconds) {
  const s = Number(seconds)
  if (!Number.isFinite(s) || s <= 0) return DASH
  if (s % 86400 === 0) return `${s / 86400} hari`
  if (s % 3600 === 0) return `${s / 3600} jam`
  if (s % 60 === 0) return `${s / 60} menit`
  return `${Math.round(s)} detik`
}

export function durationMs(ms) {
  if (ms == null) return DASH
  const n = Number(ms)
  if (!Number.isFinite(n)) return DASH
  return n >= 1000 ? `${(n / 1000).toFixed(1).replace('.', ',')} s` : `${Math.round(n)} ms`
}

// Alasan keputusan kadang membawa payload order mentah di depan prosa
// ("risk gate ... {json} | prosa"). UI hanya menampilkan prosa yang terbaca.
export function readableReason(text) {
  const src = String(text || '').trim()
  if (!src) return 'Tanpa catatan alasan.'
  const brace = src.indexOf('{')
  if (brace > 0 && /reject|tolak/i.test(src.slice(0, brace))) {
    const sep = src.indexOf(' | ')
    const tail = sep >= 0 ? src.slice(sep + 3).trim() : ''
    if (tail) return tail
    return src.slice(0, brace).replace(/[:;,\s]+$/, '')
  }
  return src
}

// Jam berjalan untuk label "x menit lalu" tanpa polling data.
export function useNow(intervalMs = 30000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(t)
  }, [intervalMs])
  return now
}
