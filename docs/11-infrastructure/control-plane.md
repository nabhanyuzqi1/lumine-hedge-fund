# Control Plane — Caddy + Authelia + Homepage + Uptime Kuma

> **ADR:** [ADR-0069](../adr/0069-control-plane-caddy-authelia-homepage-kuma.md)
> **Keputusan:** [D11-7](decisions.md#d11-7--control-plane-caddy--authelia--homepage--uptime-kuma)

Dokumen ini menjelaskan arsitektur control plane yang ter-deploy di VPS
`166.88.227.177` (2026-08-07; routing & landing diperbarui 2026-08-09):
satu entrypoint publik Caddy, login terpusat Authelia, portal hub
Homepage, dan health dashboard Uptime Kuma.
Semua service di belakangnya loopback-bound.

## Arsitektur

```
Internet :80/:443          (+ pengecualian :20128 — 9router, lihat bawah)
  └─ Caddy 2 (host network, `tls internal`)
       ├─ /           → landing page nginx CONTAINER 127.0.0.1:8080  (PUBLIK — marketing)
       ├─ /site*      → alias landing page 127.0.0.1:8080  (PUBLIK — legacy)
       ├─ /auth*      → Authelia 127.0.0.1:9091   (tidak kena auth)
       ├─ /portal*    → Homepage hub 127.0.0.1:3000 (auth dulu, strip /portal — route{})
       ├─ /hermes*    → Hermes dashboard 127.0.0.1:9119
       ├─ /mt5/*      → noVNC lumine-mt5 127.0.0.1:6901
       ├─ /websockify* → noVNC websockify lumine-mt5 127.0.0.1:6901 (path
       │     absolut yang dipakai client noVNC — bukan /mt5/websockify)
       ├─ /backend*   → Lumine API 127.0.0.1:8000
       ├─ /status*   → Uptime Kuma 127.0.0.1:3001 (auth SEBELUM strip — route{})
       ├─ /dashboard* → Uptime Kuma 127.0.0.1:3001 (redirect root Kuma, TANPA strip)
       ├─ /assets*, /socket.io → Uptime Kuma 127.0.0.1:3001
       ├─ /api/badge*, /api/entry-page*, /api/push*, /api/status-page*
       │     → Uptime Kuma 127.0.0.1:3001
       ├─ /api* lainnya → Homepage 127.0.0.1:3000
       ├─ /_next* → Homepage 127.0.0.1:3000 (asset Next.js: JS/CSS portal
       │     — wajib, tanpa route ini portal tampil tanpa CSS)
       ├─ @landing → landing 127.0.0.1:8080 (PUBLIK — /assets/*, /favicon.svg
       │     + Referer dari halaman / atau /site/; split via named matcher)
       ├─ @hermes → Hermes 127.0.0.1:9119 (/assets/*, /api/*, /socket.io/*,
       │     /favicon.ico + Referer dari halaman /hermes/)
       └─ catch-all → 404 "Not Found"
  Semua route selain /auth* (endpoint login), / dan /site* (halaman
  publik marketing) → forward_auth → Authelia (login + TOTP)
```

### Stack (satu compose: `/srv/control-plane/docker-compose.yml`)

| Service | Image | Port bind | Volume |
|---|---|---|---|
| Caddy | `caddy:2` | host `:80 :443` | `caddy_data` (certs), `caddy_config` |
| Authelia | `authelia/authelia` | `127.0.0.1:9091` | `authelia_data` (users, TOTP) |
| Homepage | `gethomepage/homepage` | `127.0.0.1:3000` | config dir + docker.sock |
| Uptime Kuma | `louislam/uptime-kuma` | `127.0.0.1:3001` | `kuma_data` (SQLite) |
| Landing | `nginx:alpine` | `127.0.0.1:8080:80` (bridge, bukan host network) | `/var/www/lumine` (ro) |

Kuma dijalankan dengan `disableAuth=1` (setting di `kuma_data` DB) —
auth internalnya dimatikan, **satu login Authelia untuk semua** (dipilih
pengguna: tidak mau password beda per dashboard).

Semua `restart: unless-stopped`. Caddy & Authelia `network_mode: host`
karena upstream Hermes/backend juga host-network — bridge tidak bisa
menjangkau `127.0.0.1:<port>` mereka. Landing justru memakai bridge +
publish `127.0.0.1:8080:80` — kalau ikut host network, port 80-nya
tabrakan dengan Caddy (`network_mode: host` mengabaikan `ports:`)
(2026-08-09).

### Catatan routing penting

- Route dengan strip prefix (`/portal*`, `/hermes*`, `/mt5*`,
  `/backend*`, `/status*`) pakai `handle @x { route { forward_auth…;
  uri strip_prefix …; reverse_proxy … } }` — `route{}` adalah raw
  routing tanpa reorder; `handle_path`/`handle` biasa meng-reorder
  strip SEBELUM forward_auth → `rd=` Authelia kehilangan prefix
  (insiden 2026-08-09: login /hermes/, /mt5/, /backend/ mendarat di
  `/`). `handle` untuk yang tidak distrip
  (`/auth*`, `/socket.io`, `/api*`, `/_next*`, `/assets*`,
  `/dashboard*`, `/websockify*`). Kuma butuh
  `/api*` dan `/assets*` TANPA strip — frontend-nya memanggil path
  absolut (`/assets/index-*.js`, `/api/...`). Kegagalan: `/assets*`
  pernah distrip → dashboard Kuma tampil tanpa JS/CSS.
- **`/websockify*` → 6901 (noVNC websocket):** client noVNC membangun
  URL websocket sebagai path ABSOLUT `wss://IP/websockify` (default
  `websockify`, BUKAN relatif `/mt5/websockify`). Tanpa route ini
  koneksi jatuh ke catch-all → "failed connect" (insiden 2026-08-08).
  Route `handle` biasa (tidak strip prefix).
- **Split Hermes via Referer (penting):** frontend Hermes memanggil
  path absolut `/assets/*`, `/api/*`, `/socket.io/*`, `/favicon.ico`
  TANPA prefix `/hermes` — path yang sama di-klaim route Kuma/Homepage
  → dashboard blank (insiden 2026-08-08). Dipisahkan dengan named
  matcher `@hermes { path /assets/* /api/* /socket.io/* /favicon.ico;
  header_regexp Referer ^https?://[^/]*/hermes(/|$) }` → 9119, ditaruh
  SEBELUM handle Kuma/Homepage (first-match). Catatan: matcher butuh
  Referer browser; WebSocket handshake browser mengirim Referer.
- **Split asset landing via Referer (2026-08-09):** landing page
  memakai path absolut `/assets/*` + `/favicon.svg` — path yang sama
  di-klaim route Kuma. Dipisahkan dengan named matcher `@landing {
  path /assets/* /favicon.svg; header_regexp Referer
  ^https?://[^/]*/(site/)?$ }` → 8080, ditaruh SEBELUM handle
  `/assets*` Kuma (first-match). Tanpa ini asset landing kena auth →
  landing tanpa CSS (insiden 2026-08-09).
- **`/status*` & `/dashboard*` (penting, insiden 2026-08-08):** Kuma
  me-redirect root "/" → `/dashboard` (302 Location tunggal).
  - **JANGAN override Location.** Dulu `header @kuma_root Location
    /status/dashboard` MENAMBAH Location kedua → Safari/WebKit menolak
    redirect dengan 2 Location → "can't reach server, or busy"
    (diverifikasi via access log: 12× request `/status/`, 0 follow-up).
  - **Browser harus mendarat di `/dashboard`** — route Vue asli Kuma.
    URL lain seperti `/status/dashboard` di-match route
    `/status/:slug` → status page kosong = dashboard "blank" (gejala
    awal). Route `/dashboard*` → 3001 **TANPA strip**: kalau strip →
    upstream "/" → Kuma 302 lagi → infinite loop.
  - **`/status*` wajib `route { }`** (raw routing tanpa reorder):
    adapter Caddy meng-reorder `uri strip_prefix` SEBELUM
    `forward_auth` dalam handle block (diverifikasi via `caddy adapt`)
    → `rd=` Authelia kehilangan prefix `/status` (login mendarat di
    path salah). Urutan di dalam `route{}`: `forward_auth` →
    `uri strip_prefix /status` → `reverse_proxy`.
- **Split `/api*` (penting):** frontend Kuma hanya memanggil 4 path
  `/api` absolut (`/api/badge*`, `/api/entry-page*`, `/api/push*`,
  `/api/status-page*` — diverifikasi via grep bundle `index-*.js`) —
  itu yang dirouting ke Kuma `3001`. Sisa `/api*` milik Homepage
  (`/api/services`, `/api/widgets`, `/api/resources`, `/api/containers`,
  `/api/settings`, `/api/search`) → `3000`. Urutan `handle` Caddy
  first-match: path spesifik harus mendahului catch-all `/api*`.
- `/_next*` → Homepage: app Next.js memuat JS/CSS dari path absolut
  `/_next/static/*`. Tanpa route ini semua asset 404 → portal tampil
  sebagai "plain HTML" tanpa CSS (insiden 2026-08-08, sudah diperbaiki).
- `/status/` → auth → strip → upstream "/" → Kuma 302 alami ke
  `/dashboard` (tanpa override header).
- Hermes butuh `header_up Host 127.0.0.1:9119` — host header asli tidak
  dikenali dashbordnya.
- Authelia `server.address: tcp://127.0.0.1:9091/auth` — komponen path =
  basepath; `forward_auth` uri `/auth/api/authz/forward-auth`.
- access_control Authelia melihat path yang SUDAH distrip → pakai
  catch-all `"^/.*"` `two_factor` (semua route butuh TOTP; `/auth/*`
  bebas auth karena itu endpoint login).

## Klasifikasi VNC per service

| Service | VNC? | Alasan |
|---|---|---|
| MT5 (`lumine-mt5`) | **Ya** | Windows GUI via Wine; noVNC `:6901` di balik Authelia |
| Hermes dashboard | Tidak | Web-native; proxy + auth cukup |
| Lumine backend | Tidak | Web-native (FastAPI) |
| Browser agent (Playwright) | Opsional, slot | Berguna melihat bot browsing real-time |
| AutoGen / runner | Tidak | Headless orchestration |
| Obsidian | Opsional, slot | Desktop app — container GUI Wine/VNC tersendiri, "nanti" |

## Menambah service GUI baru (browser, obsidian, dll.)

1. Jalankan container GUI dengan noVNC sendiri; publish port HANYA ke
   `127.0.0.1:<port>`.
2. Tambah route di `Caddyfile` (blok `handle_path` + `forward_auth`),
   `caddy reload --config` (atau restart container — `admin off` aktif).
3. Daftarkan di `homepage/services.yaml` (icon + href `https://IP/path/`
   + widget `type: docker`).
4. Tambah monitor di Uptime Kuma (socket.io `add` event) untuk endpoint
   baru.
5. Catat di tabel klasifikasi VNC di atas.

## Pengecualian: 9router `:20128` publik

`9router` sengaja tetap `0.0.0.0:20128`. Agent eksternal (termasuk agent
AI) menghubungi gateway langsung via IP; menutup port ini membuat semua
agent down (insiden 2026-08-07 — langsung dipulihkan). Kompensasi:
monitor Kuma aktif untuk `:20128`. **Jangan ubah bind-nya.** Tindak
lanjut: mTLS atau IP allowlist saat domain tersedia (ADR-0069).

## TLS

`tls internal` = self-signed otomatis (tanpa certbot), browser tampil
warning sekali. Saat domain diarahkan: ganti `tls internal` → `tls
{email ...}` (1 baris), Let's Encrypt otomatis. HTTP polos ditolak —
password tidak boleh lewat plaintext.

## Keamanan

- UFW default-deny; `80/tcp` dan `443/tcp` diizinkan. Karena 9router
  `:20128` harus tetap terjangkau agent eksternal, pastikan aturan UFW
  untuknya juga ada (`ufw allow 20128/tcp`) atau UFW dinonaktifkan —
  periksa dengan `ufw status` dan jaga port lain tetap tertutup.
- Upstream loopback: `8000` (Lumine API), `5900`/`6901` (MT5 VNC/noVNC,
  docker-proxy), `9119` (Hermes), `9091` (Authelia app-level), `8080`
  (nginx container `control-landing` — nginx:alpine, bridge network,
  ro-mount `/var/www/lumine`; host nginx dinonaktifkan 2026-08-09 —
  semua service di jalur publik kini container, 11/11), `3000`
  (Homepage), `3001` (Uptime Kuma). UFW
  `3000/tcp` dan `3001/tcp` tetap DENY sebagai defense-in-depth. UFW
  `8080` TIDAK dibuka — landing page hanya lewat Caddy `/`.
- Authelia: user admin + password kuat + TOTP wajib untuk `/auth/` paths.
- Restart policy `unless-stopped` di semua container.

## Verifikasi

1. `ss -tlnp` di VPS: hanya `:80/:443` (dan `:20128` 9router) yang bind
   publik; sisanya `127.0.0.1` (termasuk container landing `8080`,
   Homepage `3000`, Kuma `3001`).
2. `curl -I https://IP/` dan `https://IP/site/` → 200 TANPA auth
   (landing publik); `/portal/`, `/hermes/`, `/backend/`, `/mt5/`,
   `/status/`, `/dashboard/` → 302 redirect ke `/auth`.
3. Login Authelia → `/portal/` (hub), `/hermes/`, `/mt5/vnc.html`,
   `/backend/health`, `/dashboard/` semua 200 tanpa SSH tunnel.
4. `https://IP/` → landing page marketing; `https://IP/portal/` →
   Homepage grid + status hijau; `https://IP/status/` → Kuma dashboard
   interaktif.
5. `https://IP/assets/*.js` dengan Referer `https://IP/` → 200 publik
   (asset landing); tanpa Referer → 302 (milik Kuma, kena auth).
6. `http://IP:8080/`, `:3000/`, `:3001/` dari internet → timeout/refused
   (port tertutup).
7. `docker ps` di VPS: hanya container Caddy yang publish port publik;
   `control-landing` jalan di compose control-plane (11/11 container).
8. Tombol Logout di header portal → `/auth/logout?rd=…` → 200 (session
   Authelia berakhir).
9. Login Authelia → buka `/status/`: dashboard Kuma langsung tampil,
   TIDAK ada form login Kuma (auth internal mati via `disableAuth`).
