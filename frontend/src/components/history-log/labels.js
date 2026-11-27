// Label operasional untuk sub-tab "Event Kill-Switch" dan "Audit & Sesi".
// Semua masukan berasal dari endpoint yang sudah dipakai aplikasi:
//   GET /kill-switch  -> { state, events:[{action,mode,strategy,source,actor,
//                        reason,details,created_at}], recovery_checklist }
//   GET /audit        -> [{created_at,actor,actor_role,action,object,details,ip}]
// Kode mentah (mode/action/source) tidak pernah ditampilkan apa adanya ke user:
// setiap nilai dipetakan ke kalimat pendek berbahasa Indonesia.

import { formatStamp, toMs } from './reasons'

const ACTION_LABEL = {
  ACTIVATE: 'Kill-switch diaktifkan',
  AUTO_TRIGGER: 'Aktivasi otomatis',
  ESCALATE: 'Mode dieskalasi',
  RELEASE: 'Kill-switch dilepas',
  FLATTEN_REQUEST: 'Tutup semua posisi diminta',
  TRIGGERS_UPDATED: 'Ambang auto-trigger diubah',
  AGENT_PAUSE: 'Agent LLM dijeda',
  AGENT_RESUME: 'Agent LLM dilanjutkan',
  PAUSE_STRATEGY: 'Strategi dijeda',
}

const TRIGGER_LABEL = {
  daily_drawdown: 'drawdown harian',
  total_drawdown: 'drawdown total',
  daily_drawdown_risk_gate: 'drawdown harian di risk gate',
  ea_offline: 'EA offline',
  consecutive_failed: 'order gagal beruntun',
  position_mismatch: 'selisih posisi broker',
  llm_breaker: 'pemutus agent LLM',
  sev_credential_compromise: 'kredensial berisiko',
  mark_price_stale: 'harga tidak segar',
}

const MODE_LEVEL = {
  PAUSE_STRATEGY: 'lunak',
  STOP_NEW_ORDERS: 'lunak',
  STOP_AND_FLATTEN: 'keras',
  GLOBAL_HALT: 'keras',
}

// Nama mode dalam bahasa operasional (dipakai judul status & kartu event).
export const MODE_LABEL = {
  PAUSE_STRATEGY: 'Jeda strategi',
  STOP_NEW_ORDERS: 'Hentikan order baru',
  STOP_AND_FLATTEN: 'Hentikan dan tutup posisi',
  GLOBAL_HALT: 'Hentikan seluruh aktivitas',
}

const AUDIT_ACTION = {
  LOGIN_SUCCESS: 'Login berhasil',
  LOGIN_FAILED: 'Login gagal',
  LOGOUT: 'Keluar',
  '2FA_SETUP': 'Pendaftaran 2FA',
  '2FA_ENABLED': '2FA diaktifkan',
  '2FA_CHALLENGE_OK': 'Verifikasi 2FA berhasil',
  '2FA_CHALLENGE_FAILED': 'Verifikasi 2FA gagal',
  '2FA_VERIFY_FAILED': 'Verifikasi 2FA gagal',
  '2FA_DISABLED': '2FA dimatikan',
  CONFIG_CHANGED: 'Konfigurasi diubah',
  SETTINGS_UPDATED: 'Pengaturan diubah',
  APPROVAL: 'Persetujuan diberikan',
  SESSION_REVOKED: 'Sesi dicabut',
  RISK_SETTINGS_REJECTED: 'Perubahan risiko ditolak',
  RESEARCH_PROPOSAL_DECISION: 'Keputusan usulan riset',
  ORDER_CREATED: 'Order dibuat',
  KILL_SWITCH_ACTIVATE: 'Kill-switch diaktifkan',
  KILL_SWITCH_RELEASE: 'Kill-switch dilepas',
}

export function humanizeCode(value) {
  return String(value ?? '')
    .replace(/[_:]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

export function actionLabel(action) {
  const key = String(action ?? '').toUpperCase()
  if (ACTION_LABEL[key]) return ACTION_LABEL[key]
  const text = humanizeCode(key)
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : 'Kejadian'
}

export function levelInfo(mode) {
  const level = MODE_LEVEL[String(mode ?? '').toUpperCase()]
  if (level === 'keras') return { key: 'hard', label: 'Keras' }
  if (level === 'lunak') return { key: 'soft', label: 'Lunak' }
  return null
}

// Sumber kejadian: manual dari dashboard/Telegram atau otomatis oleh monitor.
export function sourceText(source) {
  const raw = String(source ?? '').trim()
  if (!raw) return 'Tidak tercatat'
  if (raw.toLowerCase().startsWith('auto:')) {
    const trigger = raw.slice(5)
    const known = TRIGGER_LABEL[trigger] ?? humanizeCode(trigger)
    return `Otomatis · ${known}`
  }
  if (raw.toLowerCase().startsWith('dashboard:')) {
    return `Dashboard · ${humanizeCode(raw.slice(10))}`
  }
  if (raw.toLowerCase() === 'dashboard') return 'Dashboard'
  if (raw.toLowerCase() === 'telegram') return 'Telegram'
  if (raw.toLowerCase() === 'system') return 'Sistem'
  return humanizeCode(raw).replace(/^./, (c) => c.toUpperCase())
}

// Teks bebas dari server (reason) sering membawa sisa teknis: rujukan
// endpoint, nama field snake_case, atau angka bertitik. Semua dibersihkan di
// sini supaya tidak ada kode mentah yang tampil di UI normal.
const TOKEN_LABEL = {
  credential_compromise: 'kredensial berisiko',
  sev_credential_compromise: 'kredensial berisiko',
  llm_breaker: 'pemutus agent LLM',
  ea_offline_seconds: 'ambang EA offline',
  ea_offline_halt_seconds: 'ambang henti EA offline',
  daily_drawdown_pct: 'batas drawdown harian',
  total_drawdown_pct: 'batas drawdown total',
  daily_drawdown: 'batas drawdown harian',
  consecutive_failed_orders: 'batas order gagal beruntun',
  daily_loss_limit: 'batas rugi harian',
  mark_price_stale: 'harga tidak segar',
}

export function cleanEventText(value) {
  let text = String(value ?? '').trim()
  if (!text) return ''
  // "… via PUT /admin/risk-settings: …" -> rujukan endpoint dibuang,
  // titik dua pemisah tetap dipertahankan.
  text = text.replace(/\s+via\s+(?:GET|POST|PUT|PATCH|DELETE)\s+\/[\w\-/{}.:]*?(?=[\s,;:]|$)/gi, '')
  text = text.replace(/\b(?:GET|POST|PUT|PATCH|DELETE)\s+\/[\w\-/{}.:]*/g, '')
  // Nama field snake_case: hanya yang dikenal, atau yang jelas berakhiran
  // satuan. Username seperti ceo_guardrail2 tidak boleh ikut diubah.
  text = text.replace(/\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b/g, (token) => {
    if (TOKEN_LABEL[token]) return TOKEN_LABEL[token]
    if (/_(?:seconds|pct|limit|orders|count|ms|ratio)$/.test(token)) return token.replace(/_/g, ' ')
    return token
  })
  text = text.replace(/\bthreshold (\d)/gi, 'ambang $1')
  text = text.replace(/\bstreak FAILED (\d+)\b/gi, 'order gagal beruntun $1')
  text = text.replace(/\bFAILED\b/g, 'gagal')
  text = text.replace(/(\d+)s\b/g, '$1 detik')
  text = text.replace(/checklist recovery diakui \(ack\)/gi, 'checklist pemulihan diakui')
  text = text.replace(/^release manual oleh\b/i, 'Dilepas manual oleh')
  text = text.replace(/^resume manual oleh\b/i, 'Dilanjutkan manual oleh')
  // angka gaya Indonesia: 0.75% -> 0,75%
  text = text.replace(/(\d)\.(\d)/g, '$1,$2')
  text = text.replace(/\b(\w+) \(\1\)/gi, '$1')
  text = text.replace(/\s*;\s*/g, '; ')
  text = text.replace(/\s{2,}/g, ' ').replace(/\s+([,.;:])/g, '$1').trim()
  return text.charAt(0).toUpperCase() + text.slice(1)
}

// Riwayat event: dipasangkan naik-turun supaya tiap aktivasi tahu kapan
// (dan apakah) ia dipulihkan. Event datang terbaru-dulu dari API.
export function decorateKillEvents(events) {
  const list = (Array.isArray(events) ? events : [])
    .map((event, index) => ({ ...event, _key: event?.id ?? `ev-${index}`, _ms: toMs(event?.created_at) }))
    .filter((event) => event._ms !== null)
    .sort((a, b) => a._ms - b._ms)

  const openGeneral = []
  const openAgent = []
  const out = []
  for (const event of list) {
    const action = String(event.action ?? '').toUpperCase()
    const item = { ...event, action, recoveryAt: null }
    if (action === 'RELEASE') {
      for (const pending of openGeneral) pending.recoveryAt = event._ms
      openGeneral.length = 0
      item.recoveryAt = event._ms
    } else if (action === 'AGENT_RESUME') {
      for (const pending of openAgent) pending.recoveryAt = event._ms
      openAgent.length = 0
      item.recoveryAt = event._ms
    }
    out.push(item)
    if (action === 'AGENT_PAUSE') openAgent.push(item)
    else if (['ACTIVATE', 'AUTO_TRIGGER', 'ESCALATE', 'FLATTEN_REQUEST'].includes(action)) openGeneral.push(item)
  }
  return out.reverse()
}

export function recoveryText(event) {
  const action = String(event?.action ?? '').toUpperCase()
  if (action === 'RELEASE' || action === 'AGENT_RESUME') {
    return { tone: 'ok', label: 'Dipulihkan', detail: formatStamp(event.recoveryAt ?? event._ms) }
  }
  if (action === 'TRIGGERS_UPDATED') {
    return { tone: 'neutral', label: 'Catatan', detail: 'Perubahan ambang, bukan aktivasi' }
  }
  if (event?.recoveryAt) {
    return { tone: 'ok', label: 'Dipulihkan', detail: formatStamp(event.recoveryAt) }
  }
  return { tone: 'warn', label: 'Belum pulih', detail: 'Belum ada pelepasan tercatat' }
}

const UUID_LIKE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function auditAction(action) {
  const key = String(action ?? '').toUpperCase()
  if (AUDIT_ACTION[key]) return AUDIT_ACTION[key]
  const text = humanizeCode(key)
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : 'Aktivitas'
}

// Kolom "Objek": yang dibaca user adalah hal yang disentuh, bukan ID internal.
export function auditObject(row) {
  const details = row?.details && typeof row.details === 'object' ? row.details : {}
  const target = row?.object
  if (typeof target === 'string' && target && !UUID_LIKE.test(target)) {
    return humanizeCode(target).replace(/^./, (c) => c.toUpperCase())
  }
  if (typeof details.revoked === 'number') {
    return `${details.revoked} sesi dicabut`
  }
  if (details.locked === true) return 'Akun dikunci'
  if (details.locked === false) return 'Percobaan login'
  if (details.updates && typeof details.updates === 'object') {
    const count = Object.keys(details.updates).length
    return count === 1 ? '1 pengaturan' : `${count} pengaturan`
  }
  if (details.decision) return `Keputusan ${humanizeCode(details.decision)}`
  if (details.checklist_ack) return 'Checklist recovery'
  return '·'
}

export function auditSource(row) {
  const role = row?.actor_role ? humanizeCode(row.actor_role) : ''
  const ip = typeof row?.ip === 'string' && row.ip ? row.ip : ''
  return [role, ip].filter(Boolean).join(' · ')
}
