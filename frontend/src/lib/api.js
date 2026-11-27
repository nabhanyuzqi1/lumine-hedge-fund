// Lapisan API: mode demo (simulator) atau mode real (endpoint fund2-api).
// Endpoint real mengikuti kartu hf-backend t_4169d6d9:
//   POST /auth/login (session cookie) · POST /orders (SL/TP wajib) ·
//   GET /orders · GET /positions · SSE /stream
import { createDemo } from './demo'
import { DEFAULT_SYMBOL, isSymbol, sessionsFor } from './market'

export const DEMO =
  import.meta.env.VITE_DEMO === '1' || new URLSearchParams(window.location.search).has('demo')

/* ---------- toast bus ---------- */
const toastSubs = new Set()
export function onToast(fn) {
  toastSubs.add(fn)
  return () => toastSubs.delete(fn)
}
export function toast(title, body = '', kind = '') {
  toastSubs.forEach((fn) => fn({ id: Math.random().toString(36).slice(2), title, body, kind }))
}

/* ---------- environment label (PRD v2.2 §21.1) ---------- */
// DEV / DEMO / LIVE: sumber = /health (publik, sebelum login) lalu /auth/me
// dan respons login setelahnya. LIVE memicu warning visual khusus di UI.
let env = 'demo'
const envSubs = new Set()
export function getEnv() {
  return env
}
export function onEnv(fn) {
  envSubs.add(fn)
  return () => envSubs.delete(fn)
}
function setEnv(v) {
  if (!v || v === env) return
  env = v
  envSubs.forEach((fn) => fn(v))
}
export async function fetchPublicEnv() {
  if (DEMO) return env
  try {
    const res = await fetch('/health')
    if (res.ok) setEnv((await res.json()).env)
  } catch { /* offline: pertahankan nilai terakhir */ }
  return env
}

/* ---------- real client ---------- */
// Cookie sesi HttpOnly (benar, aman) tidak terbaca document.cookie:
// status auth disimpan di flag ini dan diverifikasi via GET /auth/me.
let authed = false
let csrfToken = ''

function authHeaders(extra = {}) {
  return csrfToken ? { 'x-csrf-token': csrfToken, ...extra } : extra
}

function setAuthed(v) {
  if (authed === v) return
  authed = v
  authSubs.forEach((fn) => fn(v))
}

// Baris /positions dari API: open_price/profit/side uppercase ->
// shape UI (entry/pnl/side lowercase) yang sama dengan mode demo.
function normalizePosition(p) {
  if (!p || typeof p !== 'object') return p
  return {
    ...p,
    orderId: p.orderId ?? p.order_id,
    side: typeof p.side === 'string' ? p.side.toLowerCase() : p.side,
    entry: p.entry ?? p.open_price,
    pnl: p.pnl ?? p.profit,
  }
}

// Catatan event dari payload JSONB order_events ({source,username},
// {risk,reasons}, {ticket,price,...}) -> string yang bisa dibaca.
function noteFromPayload(payload) {
  if (payload == null) return undefined
  if (typeof payload === 'string') return payload || undefined
  if (typeof payload !== 'object') return String(payload)
  for (const k of ['note', 'reason', 'message', 'error', 'detail']) {
    const v = payload[k]
    if (v != null && v !== '') return Array.isArray(v) ? v.join('; ') : String(v)
  }
  const rest = Object.entries(payload).filter(([, v]) => v != null && v !== '')
  if (!rest.length) return undefined
  return rest.map(([k, v]) => `${k}=${Array.isArray(v) ? v.join('; ') : v}`).join(' · ')
}

// Baris order_events dari API ({id,from_status,to_status,payload,created_at})
// -> shape UI ({t,state,note}); event demo (t/state/note) diteruskan apa adanya.
function normalizeEvent(e) {
  if (!e || typeof e !== 'object') return e
  return {
    ...e,
    t: e.t ?? (e.created_at ? new Date(e.created_at).getTime() : undefined),
    state: e.state ?? e.to_status,
    note: e.note ?? noteFromPayload(e.payload),
  }
}

// Baris /orders dari API: side uppercase, price_filled (bukan fill),
// sl/tp bisa null, created_at ISO -> shape UI yang sama dengan mode demo.
function normalizeOrder(o) {
  if (!o || typeof o !== 'object') return o
  return {
    ...o,
    side: typeof o.side === 'string' ? o.side.toLowerCase() : o.side,
    fill: o.fill ?? (o.price_filled != null ? o.price_filled : null),
    sl: o.sl ?? null,
    tp: o.tp ?? null,
    createdMs: o.created_at ? new Date(o.created_at).getTime() : undefined,
    events: Array.isArray(o.events) ? o.events.map(normalizeEvent) : o.events,
  }
}

// detail error API bisa string ATAU objek ({message,recovery_checklist,hint}).
async function errMessage(res, fallback) {
  const body = await res.json().catch(() => ({}))
  const d = body?.detail
  if (typeof d === 'string' && d) return d
  if (d && typeof d === 'object') return d.message || d.hint || JSON.stringify(d)
  return fallback
}

// Error keputusan usulan self-improve (PRD v2.1 P4/§5.9) dengan kode stabil,
// agar UI membedakan tanpa menebak dari teks: AUTH (401 sesi habis),
// TWOFA (403 butuh step-up 2FA), OWNER (403 bukan owner), FORBIDDEN (403
// role/CSRF), CONFLICT (409 sudah diputuskan), NOT_FOUND (404).
async function decisionError(res) {
  const body = await res.json().catch(() => ({}))
  const d = body?.detail
  const detail = typeof d === 'string' ? d : (d?.message || d?.hint || '')
  const code = res.status === 401 ? 'AUTH'
    : res.status === 403 && /2FA/i.test(detail) ? 'TWOFA'
    : res.status === 403 && /owner/i.test(detail) ? 'OWNER'
    : res.status === 403 ? 'FORBIDDEN'
    : res.status === 409 ? 'CONFLICT'
    : res.status === 404 ? 'NOT_FOUND'
    : 'ERROR'
  const fallback = code === 'OWNER'
    ? 'hanya owner yang boleh memutuskan usulan'
    : code === 'CONFLICT'
      ? 'usulan sudah diputuskan sebelumnya'
      : `Keputusan gagal (HTTP ${res.status})`
  return Object.assign(new Error(detail || fallback), { code, status: res.status })
}

const real = {
  isAuthed: () => authed,
  async checkAuth() {
    try {
      const res = await fetch('/auth/me', { credentials: 'include' })
      if (res.ok) {
        const body = await res.json().catch(() => ({}))
        csrfToken = body.csrf_token || ''
        setEnv(body.env)
      }
      setAuthed(res.ok)
    } catch {
      setAuthed(false)
    }
    return authed
  },
  async login(username, password) {
    const res = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username, password }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || 'Login gagal. Periksa username dan password.')
    }
    const body = await res.json()
    csrfToken = body.csrf_token || ''
    setEnv(body.env)
    setAuthed(true)
    return body
  },
  logout() {
    setAuthed(false)
    fetch('/auth/logout', { method: 'POST', credentials: 'include', headers: authHeaders() }).catch(() => {})
  },
  start() {
    if (!authed) {
      // SSE butuh sesi (401 menutup EventSource permanen): tunda sampai auth aktif.
      this._wantStream = true
      return
    }
    // EventSource yang sudah CLOSED (mis. 401 saat sesi belum ada) tidak akan
    // hidup lagi dengan sendirinya: buang lalu buat koneksi baru.
    if (this._es && this._es.readyState === 2) {
      this._es.close()
      this._es = null
    }
    if (this._es) return
    this._wantStream = false
    const es = new EventSource('/stream')
    // Semua event API dikirim sebagai NAMED event (event: tick/order/...):
    // onmessage saja tidak pernah menerima apa pun.
    const handle = (e) => {
      try {
        const msg = JSON.parse(e.data)
        applyReal(msg)
      } catch { /* event non-JSON diabaikan */ }
    }
    es.onmessage = handle
    for (const t of ['tick', 'positions', 'order', 'halt', 'kill_switch', 'orphan', 'flatten', 'strategy_mode']) {
      es.addEventListener(t, handle)
    }
    es.onerror = () => {
      patch({ connection: 'reconnecting' })
      // CLOSED = tidak ada retry bawaan browser (401/stream ditutup server).
      // Coba lagi selama sesi masih diinginkan; backoff 5 detik agar tidak
      // menabrak rate limit bila sesi memang sudah berakhir.
      if (es.readyState === 2 && authed) {
        this._es = null
        clearTimeout(this._retryTimer)
        this._retryTimer = setTimeout(() => {
          if (authed) this.start()
        }, 5000)
      }
    }
    this._es = es
    this.refresh()
    this.refreshKillSwitch()
    // Status EA (ea_last_seen_age_s) dan kill-switch dihitung server-side:
    // polling ringan tiap 10 detik agar badge Dashboard tetap segar.
    this._ksTimer = setInterval(() => this.refreshKillSwitch(), 10000)
  },
  stop() {
    this._wantStream = false
    clearTimeout(this._retryTimer)
    if (this._ksTimer) {
      clearInterval(this._ksTimer)
      this._ksTimer = null
    }
    if (this._es) {
      this._es.close()
      this._es = null
    }
  },
  async refresh() {
    try {
      const [pr, or] = await Promise.all([
        fetch('/positions', { credentials: 'include' }),
        fetch('/orders', { credentials: 'include' }),
      ])
      if (pr.status === 401 || or.status === 401) {
        setAuthed(false)
        patch({ connection: 'offline' })
        return
      }
      const [p, o] = await Promise.all([
        pr.ok ? pr.json() : Promise.resolve([]),
        or.ok ? or.json() : Promise.resolve([]),
      ])
      patch({
        positions: (Array.isArray(p) ? p : []).map(normalizePosition),
        orders: (Array.isArray(o) ? o : []).map(normalizeOrder),
        connection: 'live',
      })
    } catch {
      patch({ connection: 'offline' })
    }
  },
  async refreshKillSwitch() {
    try {
      const res = await fetch('/kill-switch', { credentials: 'include' })
      if (res.status === 401) {
        setAuthed(false)
        return
      }
      if (!res.ok) return
      const body = await res.json()
      patch({ killSwitch: body, halted: !!body?.state?.active })
    } catch { /* offline: pertahankan nilai terakhir */ }
  },
  async loadOrderEvents(id) {
    const res = await fetch(`/orders/${id}`, { credentials: 'include' })
    if (res.status === 401) {
      setAuthed(false)
      throw new Error('Sesi berakhir, login ulang')
    }
    if (!res.ok) throw new Error('Gagal memuat event log order')
    const body = await res.json()
    return Array.isArray(body.events) ? body.events.map(normalizeEvent) : []
  },

  // Riwayat untuk halaman Riwayat (PRD v2.2 §21.3): GET /orders?limit=200
  // agar filter strategi/symbol/reason/tanggal punya cakupan lebih dalam
  // dari jendela SSE (default 50). Signature baru; refresh() tidak diubah.
  async fetchOrders(limit = 200) {
    const res = await fetch(`/orders?limit=${encodeURIComponent(limit)}`, { credentials: 'include' })
    if (res.status === 401) {
      setAuthed(false)
      throw new Error('Sesi berakhir, login ulang')
    }
    if (!res.ok) throw new Error('Gagal memuat riwayat order')
    const body = await res.json()
    return (Array.isArray(body) ? body : []).map(normalizeOrder)
  },
  subscribe(fn) {
    subs.add(fn)
    fn(state)
    return () => subs.delete(fn)
  },
  onTick(fn) {
    tickSubs.add(fn)
    return () => tickSubs.delete(fn)
  },
  // Multipair: ganti simbol aktif (Dashboard menampilkan pemilih simbol).
  // Quotes per simbol tetap terkumpul dari SSE; yang berubah hanya fokus.
  setSymbol(sym) {
    if (isSymbol(sym)) patch({ symbol: sym })
  },
  async placeOrder(payload) {
    const res = await fetch('/orders', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      credentials: 'include',
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || 'Order ditolak API')
    }
    this.refresh()
    return res.json()
  },
  async closePosition(id) {
    const res = await fetch(`/positions/${id}/close`, { method: 'POST', credentials: 'include', headers: authHeaders() })
    if (!res.ok) throw new Error('Endpoint close posisi belum tersedia di API')
    this.refresh()
  },
  async strategies() {
    const res = await fetch('/strategies', { credentials: 'include' })
    if (res.status === 401) {
      setAuthed(false)
      return []
    }
    if (!res.ok) return []
    const list = await res.json()
    const strategies = Array.isArray(list) ? list : []
    patch({ strategies })
    return strategies
  },
  async setStrategyMode(id, mode) {
    const res = await fetch(`/strategies/${id}/mode`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      credentials: 'include',
      body: JSON.stringify({ mode }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || 'Gagal mengubah mode strategi')
    }
    // Optimistik: mode lokal diperbarui segera tanpa menunggu re-fetch;
    // broadcast SSE strategy_mode menyusul untuk menyinkronkan tab lain.
    patch({ strategies: state.strategies.map((s) => (s.id === id ? { ...s, mode } : s)) })
  },
  // Kontrak API P1b: arm = POST /kill-switch {mode,...}; release =
  // POST /kill-switch/release {checklist_ack?} (GLOBAL_HALT wajib ack checklist).
  async setKillSwitch(armed, opts = {}) {
    const res = await fetch(armed ? '/kill-switch' : '/kill-switch/release', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      credentials: 'include',
      body: JSON.stringify(
        armed
          ? { mode: opts.mode || 'STOP_NEW_ORDERS', strategy: opts.strategy, confirm: !!opts.confirm, reason: opts.reason }
          : { checklist_ack: !!opts.checklistAck, strategy: opts.strategy },
      ),
    })
    if (!res.ok) throw new Error(await errMessage(res, 'Kill-switch gagal diubah'))
    const body = await res.json()
    if (body?.state) {
      patch({
        killSwitch: { ...(state.killSwitch || {}), state: body.state },
        halted: !!body.state.active,
      })
    }
    // sinkronkan metrics + paused_strategies + event terbaru
    this.refreshKillSwitch()
    return body
  },

  // ── 2FA step-up (PRD v2.2 §18, §21.6): aksi sensitif (flatten, release,
  // live, perubahan risiko) wajib assertion 2FA yang masih berlaku. ──
  // Status 2FA user (PRD §21.6): dipakai dialog konfirmasi untuk memilih
  // input kode vs pendaftaran inline, agar user tanpa 2FA tidak pernah buntu.
  async twoFaStatus() {
    const res = await fetch('/auth/me', { credentials: 'include', headers: authHeaders() })
    if (!res.ok) throw new Error('Gagal memeriksa status 2FA')
    const body = await res.json()
    return { enabled: !!body.totp_enabled, valid: !!body['2fa_valid'] }
  },
  async twoFaChallenge(code) {
    const res = await fetch('/auth/2fa/challenge', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      credentials: 'include',
      body: JSON.stringify({ code }),
    })
    if (!res.ok) throw new Error(await errMessage(res, 'Kode 2FA ditolak'))
    return res.json()
  },
  async twoFaSetup() {
    const res = await fetch('/auth/2fa/setup', {
      method: 'POST', headers: authHeaders(), credentials: 'include',
    })
    if (!res.ok) throw new Error(await errMessage(res, 'Gagal memulai pendaftaran 2FA'))
    return res.json()
  },
  async twoFaEnable(code) {
    const res = await fetch('/auth/2fa/enable', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      credentials: 'include',
      body: JSON.stringify({ code }),
    })
    if (!res.ok) throw new Error(await errMessage(res, 'Gagal mengaktifkan 2FA'))
    return res.json()
  },

  // Flatten semua posisi (2FA + confirm di API; konsekuensi slippage
  // ditampilkan dialog konfirmasi dua langkah sebelum panggilan ini).
  async flatten() {
    const res = await fetch('/kill-switch/flatten', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      credentials: 'include',
      body: JSON.stringify({ confirm: true }),
    })
    if (!res.ok) throw new Error(await errMessage(res, 'Flatten gagal'))
    this.refresh()
    return res.json()
  },

  // Riwayat audit (admin; PRD §21.5). require_admin di API mencakup
  // require_csrf: GET pun wajib header x-csrf-token. 403 -> pesan role.
  async audit(limit = 50) {
    const res = await fetch(`/audit?limit=${limit}`, { credentials: 'include', headers: authHeaders() })
    if (res.status === 401) {
      setAuthed(false)
      throw new Error('Sesi berakhir, login ulang')
    }
    if (res.status === 403) throw new Error('FORBIDDEN')
    if (!res.ok) throw new Error('Gagal memuat audit log')
    return res.json()
  },

  // DEPRECATED & DICABUT (kartu t_f412fd48): klien UI tidak lagi punya method
  // untuk `PUT /kill-switch/triggers`. Semua halaman menulis auto-trigger lewat
  // `updateRiskSettings({ kill_switch_triggers })` (password + 2FA + rentang +
  // audit). Endpoint lama tetap hidup di server untuk klien luar, tetapi wajib
  // memakai validator yang sama dengan kanal admin (guardrail_ranges.py).

  // ── Usulan self-improve (PRD v2.1 §5.9/P4): daftar + keputusan owner. ──
  // Keputusan owner-only di API: admin + CSRF + 2FA step-up + username ==
  // settings.owner_username. GET hanya butuh sesi login (daftar terlihat
  // semua role; tombol keputusan tetap ditolak API untuk non-owner).
  async proposals() {
    const res = await fetch('/improve/proposals', { credentials: 'include', headers: authHeaders() })
    if (res.status === 401) {
      setAuthed(false)
      throw new Error('Sesi berakhir, login ulang')
    }
    if (!res.ok) throw new Error(await errMessage(res, 'Gagal memuat daftar usulan'))
    return res.json()
  },

  // Keputusan owner (APPROVED langsung deploy). 403 TWOFA dilempar dengan
  // kode stabil agar dialog konfirmasi kembali ke langkah kode 2FA; 403
  // OWNER/FORBIDDEN dan 409 CONFLICT ditangani halaman sebagai pesan tanpa retry.
  async decideProposal(id, decision, rationale) {
    const res = await fetch(`/improve/proposals/${encodeURIComponent(id)}/decision`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      credentials: 'include',
      body: JSON.stringify({ decision, rationale: rationale || null }),
    })
    if (!res.ok) throw await decisionError(res)
    return res.json()
  },

  getState: () => state,
}

/* ── UI-D1 (PRD §21.2): fetcher widget audit-review Dashboard. ──
   Fungsi BARU saja; fungsi existing tidak diubah. Semua read-only GET
   dengan session cookie; 401 -> sesi habis (setAuthed(false)). */
export async function fetchRegimeCurrent(symbol) {
  const res = await fetch(`/regime/current?symbol=${encodeURIComponent(symbol)}`, { credentials: 'include' })
  if (res.status === 401) { setAuthed(false); throw new Error('Sesi berakhir, login ulang') }
  if (!res.ok) throw new Error('Gagal memuat regime')
  return res.json()
}

export async function fetchRiskPortfolio() {
  const res = await fetch('/risk/portfolio', { credentials: 'include' })
  if (res.status === 401) { setAuthed(false); throw new Error('Sesi berakhir, login ulang') }
  if (!res.ok) throw new Error('Gagal memuat portfolio risk')
  return res.json()
}

export async function fetchAlertsActive() {
  const res = await fetch('/alerts/active', { credentials: 'include' })
  if (res.status === 401) { setAuthed(false); throw new Error('Sesi berakhir, login ulang') }
  if (!res.ok) throw new Error('Gagal memuat alert aktif')
  return res.json()
}

/* ── Admin Guardrail Risiko (kartu t_2d1f6d33, PRD §14/§18): baca nilai
   efektif + riwayat settings_audit, dan simpan guardrail inti. Semua kanal
   tulis tetap lewat endpoint ber-2FA + konfirmasi password di server; tidak
   ada jalur pintas dari UI. ── */
export async function fetchMe() {
  const res = await fetch('/auth/me', { credentials: 'include', headers: authHeaders() })
  if (res.status === 401) { setAuthed(false); throw new Error('Sesi berakhir, login ulang') }
  if (!res.ok) throw new Error('Gagal memuat profil sesi')
  const body = await res.json()
  setEnv(body.env)
  return body
}

// GET /kill-switch -> {state, triggers, metrics, events,...}; halaman admin
// memakai `triggers` sebagai nilai AKTIF auto-trigger (sumber sama dengan
// yang dievaluasi kill-switch monitor).
export async function fetchKillSwitchStatus() {
  const res = await fetch('/kill-switch', { credentials: 'include' })
  if (res.status === 401) { setAuthed(false); throw new Error('Sesi berakhir, login ulang') }
  if (!res.ok) throw new Error('Gagal memuat status kill-switch')
  return res.json()
}

// GET /admin/risk-settings (require_admin: sesi admin + header CSRF) ->
// {values, defaults, ranges, portfolio_risk, owner_decision}.
export async function fetchGuardrailSettings() {
  const res = await fetch('/admin/risk-settings', { credentials: 'include', headers: authHeaders() })
  if (res.status === 401) { setAuthed(false); throw new Error('Sesi berakhir, login ulang') }
  if (res.status === 403) throw Object.assign(new Error('Halaman ini hanya untuk admin'), { code: 'FORBIDDEN' })
  if (!res.ok) throw new Error('Gagal memuat guardrail risiko')
  return res.json()
}

// GET /admin/settings-audit?limit= -> {keys, rows:[{key,old_value,new_value,
// changed_by,source,changed_at}]}; riwayat append-only dari trigger DB.
export async function fetchSettingsAudit(limit = 20) {
  const res = await fetch(`/admin/settings-audit?limit=${encodeURIComponent(limit)}`, {
    credentials: 'include',
    headers: authHeaders(),
  })
  if (res.status === 401) { setAuthed(false); throw new Error('Sesi berakhir, login ulang') }
  if (res.status === 403) throw Object.assign(new Error('Halaman ini hanya untuk admin'), { code: 'FORBIDDEN' })
  if (!res.ok) throw new Error('Gagal memuat riwayat audit settings')
  return res.json()
}

// PUT /admin/risk-settings {password, ...nilai} (require_2fa: admin + CSRF +
// assertion TOTP aktif). Password salah -> 403 "password salah" tanpa menulis.
export async function updateRiskSettings(payload) {
  const res = await fetch('/admin/risk-settings', {
    method: 'PUT',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    credentials: 'include',
    body: JSON.stringify(payload),
  })
  if (res.status === 401) { setAuthed(false); throw new Error('Sesi berakhir, login ulang') }
  if (!res.ok) throw new Error(await errMessage(res, `Gagal menyimpan guardrail (HTTP ${res.status})`))
  return res.json()
}


/* ── RISK-D (t_a172bb7b): config risk efektif per strategi (panel Strategy
   Lab). Read-only GET sesi login; nilai + sumber (global/override), plus
   usulan yang menunggu keputusan owner. ── */
export async function fetchStrategyRiskConfigs() {
  const res = await fetch('/risk/config/strategies', { credentials: 'include' })
  if (res.status === 401) { setAuthed(false); throw new Error('Sesi berakhir, login ulang') }
  if (!res.ok) throw new Error('Gagal memuat config risk per strategi')
  return res.json()
}

export async function fetchStrategyVersions(strategyId) {
  const res = await fetch(`/strategies/${encodeURIComponent(strategyId)}/versions`, { credentials: 'include' })
  if (res.status === 401) { setAuthed(false); throw new Error('Sesi berakhir, login ulang') }
  if (!res.ok) throw new Error('Gagal memuat versi strategi')
  return res.json()
}

/* ── UI-D3b (PRD v2.2 §21.4, §11): Strategy Lab — versi, walk-forward,
   shadow, degradasi, approval, rollback. Fungsi BARU saja; fungsi existing
   tidak diubah. Read GET sesi login; tulis POST owner + 2FA step-up di API
   (header x-csrf-token dari sesi). Error dilempar dengan kode stabil agar
   panel bisa menampilkan pesan tanpa menebak. ── */
async function labGet(url, fallbackLabel) {
  const res = await fetch(url, { credentials: 'include' })
  if (res.status === 401) { setAuthed(false); throw new Error('Sesi berakhir, login ulang') }
  if (!res.ok) {
    // Sertakan detail backend + status agar panel bisa membedakan 403 peran
    // dari kegagalan teknis, tanpa menebak dari teks pesan.
    let detail = ''
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch { /* body kosong / bukan JSON */ }
    const ex = new Error(detail ? `Gagal memuat ${fallbackLabel}: ${detail}` : `Gagal memuat ${fallbackLabel}`)
    ex.status = res.status
    throw ex
  }
  return res.json()
}

async function labPost(url, body, fallbackLabel) {
  const res = await fetch(url, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    credentials: 'include',
    body: JSON.stringify(body),
  })
  if (res.status === 401) { setAuthed(false); throw new Error('Sesi berakhir, login ulang') }
  if (!res.ok) throw new Error(await errMessage(res, fallbackLabel))
  return res.json()
}

// GET /strategies/{id}/versions -> {strategy, versions:[...]} (PRD 11.4)
export function fetchStrategyVersionsDetail(strategyId) {
  return labGet(`/strategies/${encodeURIComponent(strategyId)}/versions`, 'daftar versi')
}

// GET /strategies/{id}/versions/{version} -> row lengkap satu versi
export function fetchStrategyVersion(strategyId, version) {
  return labGet(`/strategies/${encodeURIComponent(strategyId)}/versions/${encodeURIComponent(version)}`, 'detail versi')
}

// GET /strategies/{id}/degradation -> {strategy_id, state, events}
export function fetchDegradation(strategyId) {
  return labGet(`/strategies/${encodeURIComponent(strategyId)}/degradation`, 'status degradasi')
}

// POST /strategies/{id}/degradation/re-enable {review_note} (owner + 2FA)
export function reEnableDegradation(strategyId, reviewNote) {
  return labPost(
    `/strategies/${encodeURIComponent(strategyId)}/degradation/re-enable`,
    { review_note: reviewNote },
    're-enable gagal',
  )
}

// GET /shadow/runs -> {runs:[...]} (read-only, PRD §9)
export function fetchShadowRuns() {
  return labGet('/shadow/runs', 'run shadow')
}

// GET /shadow/runs/{run_id}/signals -> {run_id, is_simulation, signals:[...]}
export function fetchShadowSignals(runId, limit = 100) {
  return labGet(`/shadow/runs/${encodeURIComponent(runId)}/signals?limit=${encodeURIComponent(limit)}`, 'sinyal shadow')
}

// GET /strategies/lifecycle-summary -> {strategies:[...]} (anti N+1)
export function fetchLifecycleSummary() {
  return labGet('/strategies/lifecycle-summary', 'ringkasan lifecycle')
}

// GET /strategies/{id}/approvals -> {approvals:[...]} (append-only desc)
export function fetchStrategyApprovals(strategyId, limit = 50) {
  return labGet(`/strategies/${encodeURIComponent(strategyId)}/approvals?limit=${encodeURIComponent(limit)}`, 'riwayat approval')
}

// POST /strategies/{id}/versions/{version}/activate {mode, reason} (owner+2FA)
export function activateVersion(strategyId, version, mode, reason) {
  return labPost(
    `/strategies/${encodeURIComponent(strategyId)}/versions/${encodeURIComponent(version)}/activate`,
    { mode, reason: reason || null },
    'aktivasi versi gagal',
  )
}

// POST /strategies/{id}/rollback {to_version, reason} (owner+2FA, PRD 11.3)
export function rollbackStrategy(strategyId, toVersion, reason) {
  return labPost(
    `/strategies/${encodeURIComponent(strategyId)}/rollback`,
    { to_version: toVersion, reason },
    'rollback gagal',
  )
}

/* ── UI-D2 (gap API): endpoint yang belum terwakali di frontend. Fungsi
   BARU saja; pola sama dengan labGet/labLabPost di atas: GET read-only
   sesi login, tulis POST dengan CSRF header (authHeaders) — 2FA step-up
   dan role dicek ulang server-side. 401 -> sesi habis (setAuthed(false)). ── */

// GET /strategies/degradation -> {states:[...]} (status semua strategi, PRD §10)
export function fetchDegradationStates() {
  return labGet('/strategies/degradation', 'status degradasi semua strategi')
}

// GET /strategies/supervisor -> {strategies:[...]} (lifecycle + circuit
// breaker semua strategi, PRD v2.2 §5)
export function fetchSupervisorStates() {
  return labGet('/strategies/supervisor', 'status supervisor')
}

// GET /strategies/{id}/supervisor/events -> {strategy_id, events:[...]} (PRD 5.2)
export function fetchSupervisorEvents(strategyId) {
  return labGet(
    `/strategies/${encodeURIComponent(strategyId)}/supervisor/events`,
    'event supervisor',
  )
}

// POST /strategies/{id}/lifecycle {to_status, reason} (admin; transisi yang
// menaikkan privilege trading wajib 2FA di API, PRD 5.3)
export function transitionLifecycle(strategyId, toStatus, reason) {
  return labPost(
    `/strategies/${encodeURIComponent(strategyId)}/lifecycle`,
    { to_status: toStatus, reason: reason || null },
    'transisi lifecycle gagal',
  )
}

// GET /llm-agent/status (require_csrf: GET pun wajib header x-csrf-token)
export async function fetchLlmStatus() {
  const res = await fetch('/llm-agent/status', { credentials: 'include', headers: authHeaders() })
  if (res.status === 401) { setAuthed(false); throw new Error('Sesi berakhir, login ulang') }
  if (!res.ok) throw new Error('Gagal memuat status LLM agent')
  return res.json()
}

// POST /llm-agent/resume (owner+2FA: require_2fa = admin + CSRF + assertion
// 2FA yang masih berlaku; step-up dikirim UI via ConfirmDialog requires2fa).
export async function resumeLlmAgent() {
  const res = await fetch('/llm-agent/resume', { method: 'POST', credentials: 'include', headers: authHeaders() })
  if (res.status === 401) { setAuthed(false); throw new Error('Sesi berakhir, login ulang') }
  if (res.status === 403) throw new Error('Resume hanya owner dengan 2FA yang valid')
  if (!res.ok) throw new Error(await errMessage(res, 'Gagal resume agent LLM'))
  return res.json()
}

// GET /research/reports?limit= (laporan riset; role research/admin — owner login sebagai admin)
export function fetchResearchReports(limit = 20) {
  return labGet(`/research/reports?limit=${encodeURIComponent(limit)}`, 'laporan riset')
}

// GET /research/tools -> {tools:[...]} (allowlist tool riset + skema, PRD 12.4)
export function fetchResearchTools() {
  return labGet('/research/tools', 'daftar tool riset')
}

// GET /research/proposals?limit= (usulan riset Hermes, PRD §12)
export function fetchResearchProposals(limit = 20) {
  return labGet(`/research/proposals?limit=${encodeURIComponent(limit)}`, 'usulan riset')
}

// POST /research/proposals/{id}/decision {decision, rationale} (owner+2FA)
export function decideResearchProposal(id, decision, rationale) {
  return labPost(
    `/research/proposals/${encodeURIComponent(id)}/decision`,
    { decision, rationale: rationale || null },
    'keputusan usulan riset gagal',
  )
}

// POST /research/proposals/{id}/deployed {strategy_version_id, note} (owner+2FA)
export function markProposalDeployed(id, strategyVersionId, note) {
  return labPost(
    `/research/proposals/${encodeURIComponent(id)}/deployed`,
    { strategy_version_id: strategyVersionId, note: note || null },
    'penandaan deployed gagal',
  )
}

// GET /auth/sessions -> daftar sesi user aktif (session hygiene)
export function fetchAuthSessions() {
  return labGet('/auth/sessions', 'daftar sesi')
}

// POST /auth/sessions/revoke-all (cabut semua sesi kecuali sesi saat ini)
export function revokeAllSessions() {
  return labPost('/auth/sessions/revoke-all', {}, 'pencabutan sesi gagal')
}

// POST /strategies/{id}/versions/{version}/submit {evidence} (admin+CSRF+2FA)
export function submitVersion(strategyId, version, evidence) {
  return labPost(
    `/strategies/${encodeURIComponent(strategyId)}/versions/${encodeURIComponent(version)}/submit`,
    { evidence: evidence || null },
    'submit versi gagal',
  )
}

// POST /strategies/{id}/versions/{version}/review {stage, decision, rationale}
// (stage owner wajib username owner; 2FA step-up di API)
export function reviewVersion(strategyId, version, stage, decision, rationale) {
  return labPost(
    `/strategies/${encodeURIComponent(strategyId)}/versions/${encodeURIComponent(version)}/review`,
    { stage, decision, rationale: rationale || null },
    'review versi gagal',
  )
}

/* ---------- real-mode state ---------- */
let state = {
  symbol: DEFAULT_SYMBOL,
  quotes: {}, // symbol -> {price,bid,ask,spread,sessions,ticks}
  positions: [], orders: [],
  equity: null, halted: false, killSwitch: null, strategies: [], connection: 'connecting',
}
const subs = new Set()
const tickSubs = new Set()

function patch(p) {
  state = { ...state, ...p }
  subs.forEach((fn) => fn(state))
}

function applyReal(msg) {
  if (msg.type === 'tick') {
    // F-UI-3 (multipair): EA v5 multi-simbol mengirim tick XAUUSD dan BTCUSD
    // dalam stream SSE yang sama, tiap event membawa symbol. Tick disimpan
    // per simbol (quotes[symbol]) agar headline, chart, dan form tidak
    // tercampur harga antar simbol (XAU ~3.5k vs BTC ~97k). Tick tanpa field
    // symbol (kontrak lama) dianggap milik simbol yang sedang dipilih; tick
    // simbol di luar kontrak UI diabaikan.
    if (msg.symbol && !isSymbol(msg.symbol)) return
    const sym = msg.symbol || state.symbol
    const prev = state.quotes[sym] || {}
    // SATU snapshot tick untuk semua komponen harga simbol tersebut. price =
    // mid ((bid+ask)/2) dipakai headline ticker, dash-symbol, dan chart; form
    // order memakai ask (beli) / bid (jual) dari tick yang sama. Dashboard
    // menampilkan BID/ASK eksplisit agar selisih mid vs ask (= spread/2)
    // jelask basis datanya — tidak ada sumber tick kedua (REST tidak
    // menyediakan tick; SSE satu-satunya sumber).
    const price = msg.bid != null ? (msg.bid + msg.ask) / 2 : msg.price
    patch({
      quotes: {
        ...state.quotes,
        [sym]: {
          price,
          bid: msg.bid,
          ask: msg.ask,
          spread: msg.ask != null && msg.bid != null ? +(msg.ask - msg.bid).toFixed(2) : prev.spread,
          sessions: msg.sessions ?? sessionsFor(sym),
          ticks: [...(prev.ticks || []).slice(-320), price],
        },
      },
      connection: 'live',
    })
    tickSubs.forEach((fn) => fn({ symbol: sym, price, bid: msg.bid, ask: msg.ask, ts: msg.ts }))
  } else if (msg.type === 'positions') {
    // Event SSE positions hanya membawa hitungan (open/closed), bukan baris:
    // ambil ulang daftar posisi dari API.
    real.refresh()
  } else if (msg.type === 'order') {
    // Event order SSE hanya membawa {order_id, status}, bukan objek order:
    // ambil ulang daftar agar Riwayat mengikuti transisi terbaru.
    real.refresh()
    if (msg.status === 'FILLED') toast('Order terisi', msg.order_id || '', 'up')
    else if (msg.status === 'FAILED' || msg.status === 'RISK_FAIL' || msg.status === 'STUCK')
      toast(`Order ${msg.status}`, msg.order_id || '', 'down')
  } else if (msg.type === 'halt') {
    // Auto-trigger (risk gate) publish {reason} tanpa armed; ambil ulang
    // state kill-switch agar mode/aktif selalu akurat.
    if (msg.armed != null) patch({ halted: !!msg.armed })
    real.refreshKillSwitch()
  } else if (msg.type === 'strategy_mode') {
    // Broadcast toggle Paper/Live (payload hanya {strategy_id, mode}):
    // ambil ulang daftar strategi agar mode di semua tab langsung mengikuti.
    real.strategies()
  }
}

/* ---------- facade ---------- */
const impl = DEMO ? createDemo() : real

export const auth = {
  isAuthed: () => impl.isAuthed(),
  checkAuth: () => (impl.checkAuth ? impl.checkAuth() : Promise.resolve(impl.isAuthed())),
  login: (u, p) => impl.login(u, p),
  logout: () => impl.logout(),
  onAuth: (fn) => {
    authSubs.add(fn)
    return () => authSubs.delete(fn)
  },
  onTick: (fn) => impl.onTick(fn),
}
const authSubs = new Set()

export const desk = {
  subscribe: (fn) => impl.subscribe(fn),
  placeOrder: (p) => impl.placeOrder(p),
  closePosition: (id) => impl.closePosition(id),
  setStrategyMode: (id, m) => impl.setStrategyMode(id, m),
  setSymbol: (s) => impl.setSymbol(s),
  setKillSwitch: (a, opts) => impl.setKillSwitch(a, opts),
  loadOrderEvents: (id) => impl.loadOrderEvents ? impl.loadOrderEvents(id) : Promise.resolve([]),
  fetchOrders: (limit) => impl.fetchOrders ? impl.fetchOrders(limit) : Promise.reject(new Error('DEMO')),
  loadStrategies: () => impl.strategies?.() ?? Promise.resolve(impl.getState().strategies),
  // Aksi operasional (PRD §21.5-21.6). Mode demo: tidak ada aksi nyata —
  // caller menampilkan penjelasan, bukan simulasi aksi berisiko.
  flatten: () => impl.flatten ? impl.flatten() : Promise.reject(new Error('DEMO')),
  audit: (limit) => impl.audit ? impl.audit(limit) : Promise.reject(new Error('DEMO')),
  twoFaChallenge: (code) => impl.twoFaChallenge ? impl.twoFaChallenge(code) : Promise.reject(new Error('DEMO')),
  twoFaStatus: () => impl.twoFaStatus ? impl.twoFaStatus() : Promise.reject(new Error('DEMO')),
  twoFaSetup: () => impl.twoFaSetup ? impl.twoFaSetup() : Promise.reject(new Error('DEMO')),
  twoFaEnable: (code) => impl.twoFaEnable ? impl.twoFaEnable(code) : Promise.reject(new Error('DEMO')),
  // Usulan self-improve (PRD v2.1 P4). Mode demo: tidak ada data/aksi nyata.
  proposals: () => impl.proposals ? impl.proposals() : Promise.reject(new Error('DEMO')),
  decideProposal: (id, decision, rationale) => impl.decideProposal ? impl.decideProposal(id, decision, rationale) : Promise.reject(new Error('DEMO')),
}

export function startDesk() {
  impl.start()
}

// wrap logout supaya listener auth ikut diberi tahu
const _logout = auth.logout
auth.logout = () => {
  _logout()
  authSubs.forEach((fn) => fn(false))
}
const _login = auth.login
auth.login = async (u, p) => {
  const r = await _login(u, p)
  authSubs.forEach((fn) => fn(true))
  return r
}

// SSE hidup-mati mengikuti status auth: sambungkan saat login, tutup saat logout.
authSubs.add((v) => {
  if (v) {
    if (real._wantStream) real.start()
  } else {
    real.stop()
  }
})

/* ══ FUND2-LLM-F1 (rencana t_2a751a6c, B1 t_9f36a70a + B2 t_aaf7498f) ══
   Helper BARU untuk halaman /agent dan /settings. Fungsi existing tidak
   diubah satu baris pun.

   Catatan kontrak backend (app/llm_introspection.py + app/llm_agent.py):
   - GET /llm-agent/config, /decisions, /introspection memakai require_csrf:
     header `x-csrf-token` WAJIB walau method GET (tanpa itu 403 senyap).
   - POST /llm-agent/introspect = require_2fa (admin + CSRF + jendela 2FA);
     role lain 403 dan UI menyembunyikan tombolnya, bukan menampilkan error.
   - Error dilempar dengan kode stabil (AUTH/TWOFA/FORBIDDEN/NOT_FOUND/
     INVALID/UNAVAILABLE) supaya halaman tidak menebak dari teks.
   - Mode demo (`?demo=1`) TIDAK memanggil jaringan: error berkode DEMO,
     halaman memakai data contoh yang dilabeli DEMO. */

function f1DemoError() {
  return Object.assign(new Error('DEMO: tidak ada panggilan API di mode demo'), { code: 'DEMO' })
}

async function f1Error(res, label) {
  const body = await res.json().catch(() => ({}))
  const d = body?.detail
  const detail = typeof d === 'string' ? d : (d?.message || d?.hint || '')
  const code = res.status === 401 ? 'AUTH'
    : res.status === 403 && /2FA/i.test(detail) ? 'TWOFA'
    : res.status === 403 ? 'FORBIDDEN'
    : res.status === 404 ? 'NOT_FOUND'
    : res.status === 422 ? 'INVALID'
    : res.status === 503 ? 'UNAVAILABLE'
      : 'ERROR'
  return Object.assign(
    new Error(detail || `Gagal memuat ${label} (HTTP ${res.status})`),
    { code, status: res.status },
  )
}

async function f1Get(url, label) {
  if (DEMO) throw f1DemoError()
  const send = () => fetch(url, { credentials: 'include', headers: authHeaders() })
  let res = await send()
  if (res.status === 403) {
    // require_csrf: GET pun wajib token. Sesudah reload penuh checkAuth() bisa
    // belum selesai saat halaman mount; segarkan token lalu ulangi SEKALI
    // (403 karena role tetap 403 dan tampil sebagai FORBIDDEN, bukan loop).
    await real.checkAuth()
    res = await send()
  }
  if (res.status === 401) {
    setAuthed(false)
    throw Object.assign(new Error('Sesi berakhir, login ulang'), { code: 'AUTH', status: 401 })
  }
  if (!res.ok) throw await f1Error(res, label)
  return res.json()
}

// GET /llm-agent/config -> {system_prompt, prompt_version, model, interval_s,
// llm_risk, calendar:{blackout_active, blackout_reason, data}, pause,
// kill_switch, halted, halted_mirror}. Respons field-per-field: tidak ada
// kredensial LLM di dalamnya (dijaga server).
export function getAgentConfig() {
  return f1Get('/llm-agent/config', 'konfigurasi agent')
}

// GET /version -> {running_prompt_version, disk_prompt_version, stale_code,
// commit, uptime_s}. Dipakai banner "proses API basi" di shell aplikasi:
// prompt yang di-import saat start dibandingkan dengan file di disk.
export function fetchVersion() {
  return f1Get('/version', 'versi kode')
}

// GET /llm-agent/models -> {catalog:[id model], effective:{specialist,synth,
// fallback,parallel,roles}, roles_saved:{peran:model}, role_keys:[...],
// role_defaults:{peran:model}, last_cycle:{cycle_id,at,symbol,roles:{peran:
// {model,state,latency_ms}}}|null, env_model} (t_2a1fbf01, t_0ff73490).
// Katalog diambil server dari endpoint LLM, `roles_saved` hanya override owner,
// `last_cycle` dari evidence AGENT_EVIDENCE (model yang benar-benar dipakai).
export function getAgentModels() {
  return f1Get('/llm-agent/models', 'katalog model agent')
}

// PUT /llm-agent/models {specialist,synth,fallback,parallel,roles} (owner +
// 2FA). `roles` = dict peran -> nama model; string kosong menghapus override
// peran itu (kembali ke bawaan sistem / model specialist global).
export async function putAgentModels(payload) {
  if (DEMO) throw f1DemoError()
  const res = await fetch('/llm-agent/models', {
    method: 'PUT',
    credentials: 'include',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  })
  if (res.status === 401) {
    setAuthed(false)
    throw Object.assign(new Error('Sesi berakhir, login ulang'), { code: 'AUTH', status: 401 })
  }
  if (res.status === 403) {
    throw Object.assign(new Error('Perlu 2FA aktif: verifikasi kode dulu'), { code: 'TWOFA', status: 403 })
  }
  if (!res.ok) throw await f1Error(res, 'simpan pilihan model')
  return res.json()
}

// GET /llm-agent/decisions?limit=&symbol= -> {decisions:[{id, order_id,
// to_status, decision:{kind,symbol,reasoning,confidence,model,prompt_version,
// cycle_id,prompt_tokens,completion_tokens,latency_ms,error,...}, created_at}],
// count}. Terbaru dulu; limit 1..200.
export function getAgentDecisions({ limit = 50, symbol = '' } = {}) {
  const q = new URLSearchParams({ limit: String(limit) })
  if (symbol) q.set('symbol', symbol)
  return f1Get(`/llm-agent/decisions?${q.toString()}`, 'riwayat keputusan agent')
}

// GET /llm-agent/introspection?scope=trade|daily&limit=&date= -> {introspections:
// [{id, scope, ref_key, evidence, narasi, model, prompt_version, created_at}],
// count}. scope=daily + date memfilter ref_key tanggal UTC persis.
export function getAgentIntrospection({ scope = 'trade', limit = 50, date = '' } = {}) {
  const q = new URLSearchParams({ scope, limit: String(limit) })
  if (date) q.set('date', date)
  return f1Get(`/llm-agent/introspection?${q.toString()}`, 'hasil introspeksi')
}

// POST /llm-agent/introspect {scope, ref_key} — admin + 2FA. scope trade:
// ref_key = order_id/ticket posisi CLOSED; scope daily: ref_key = YYYY-MM-DD
// (kosong = hari ini UTC). Idempoten: scope+ref_key yang sama tidak menimpa
// narasi lama.
export async function requestIntrospection({ scope, refKey = '' }) {
  if (DEMO) throw f1DemoError()
  const res = await fetch('/llm-agent/introspect', {
    method: 'POST',
    credentials: 'include',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ scope, ref_key: refKey || null }),
  })
  if (res.status === 401) {
    setAuthed(false)
    throw Object.assign(new Error('Sesi berakhir, login ulang'), { code: 'AUTH', status: 401 })
  }
  if (!res.ok) throw await f1Error(res, 'introspeksi on-demand')
  return res.json()
}
