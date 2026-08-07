# Panduan Install VPS Lumine — Stack + Docker + MT5 via Wine

Panduan lengkap menyiapkan VPS untuk seluruh workflow Lumine:

- **Stack Lumine**: FastAPI + Postgres + Redis (Docker Compose)
- **9router / hermes / openclaude**: state dirs + komponen opsional
- **MetaTrader 5 + EA**: berjalan via **Wine di dalam container Docker** (keputusan khusus, lihat Bagian 0)

---

## Bagian 0 — Keputusan Arsitektur & Penyimpangan

> **PENTING**: Arsitektur Phase 8 (`docs/08-trading/mt5-integration.md`) menetapkan MT5
> berjalan di **Windows VPS terpisah**. Keputusan yang dipilih di sini berbeda:
> **MT5 via Wine di dalam container Docker di VPS Linux yang sama**.

Konsekuensi yang harus diterima:

| Aspek | Arsitektur Phase 8 (Windows VPS) | Keputusan ini (Wine in Docker) |
|-------|----------------------------------|--------------------------------|
| Stabilitas terminal | Tinggi (native Windows) | **Rendah** — banyak build MT5 crash di Wine, terutama build ≥ 4000 |
| Latensi Redis bridge | Cross-VPS (network RTT) | Rendah (satu host) — nilai tambah |
| Biaya | 2 VPS | 1 VPS |
| Dukungan broker | Semua fitur | Login broker bisa gagal / fitur tertentu hilang |
| Operasional | Terminal native | Perlu VNC untuk login manual, headless untuk operasi |

**Rekomendasi saat ini**: gunakan panduan ini untuk uji coba / paper trading.
Sebelum masuk produksi penuh, evaluasi kembali pindah MT5 ke Windows VPS.

---

## Bagian 1 — Persyaratan VPS

| Item | Minimum | Rekomendasi |
|------|---------|-------------|
| OS | Ubuntu 22.04 LTS | **Ubuntu 24.04 LTS** (apt-based, didukung bootstrap script) |
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | **8 GB** (Wine + MT5 + Postgres + Redis) |
| Disk | 50 GB SSD | 100 GB SSD |
| Network | Publik IP | Statis; port 22 (SSH) wajib terbuka |

Catatan: **bootstrap-vps.sh dan deploy-stack.sh mengasumsikan apt (Ubuntu/Debian)**.
Jangan pakai CentOS/Alpine di host.

---

## Bagian 2 — Setup Stack Lumine

Semua script sudah ada di paket ini (`scripts/deploy/`). Jalankan dari laptop
(script ini SSH ke VPS) — bukan di VPS.

### 2.1 Siapkan kredensial

```bash
cd scripts/deploy
cp .env.sample .env
$EDITOR .env   # isi: VPS_HOST, DB_PASSWORD, HMAC_SECRET_KEY, LLM_GATEWAY_API_KEY
```

### 2.2 Deploy stack (bootstrap + Docker + compose up)

```bash
./deploy-stack.sh
```

Yang dilakukan script ini:

1. Bootstrap VPS: `apt-get update`, install paket dasar
   (git, curl, gnupg, lsb-release, unzip, zip, jq, htop, screen, ufw, fail2ban)
2. Install **Docker Engine + compose plugin** (jika belum ada)
3. Buat user deploy + state directories `/opt/lumine/state/...`
4. Kirim compose, tulis `.env` produksi via stdin (tidak pernah menyentuh disk secara permanen)
5. `docker compose up -d` + health check

### 2.3 Verifikasi stack

```bash
ssh root@<VPS_IP>
cd /opt/lumine/backend
docker compose ps            # postgres, redis, api → healthy/running
curl -s http://localhost:8000/health   # → {"status":"ok"} (atau semacamnya)
```

### 2.4 State 9router / hermes / openclaude (opsional)

```bash
# Dari laptop, jika ada state lama:
./import-state.sh state-exports/<stamp>.tar.gz
```

---

## Bagian 3 — MT5 via Wine di dalam Docker

MT5 berjalan di container sendiri yang join **network yang sama dengan stack
Lumine**, sehingga EA dapat mengakses Redis (`redis:6379`) langsung — bridge
`mt5:commands` / `mt5:results` tetap sesuai Phase 8.

### 3.1 Struktur folder (sumber di repo)

File konkrit ada di repo, bukan snippet inline:

```
scripts/deploy/mt5/
├── Dockerfile       ubuntu:24.04 + Wine + Xvfb + XFCE4 + x11vnc + noVNC
└── entrypoint.sh    start Xvfb → XFCE4 → x11vnc (password) → noVNC → MT5
```

Di VPS, `deploy-stack.sh` menaruhnya di `/opt/lumine/scripts/deploy/mt5/`.
Compose memakai `context: ../scripts/deploy/mt5` (relatif dari
`/opt/lumine/backend/`) sehingga path konsisten antara repo lokal dan VPS.

### 3.2 Layer image

| Komponen | Fungsi |
|----------|--------|
| Wine (i386+amd64) | menjalankan `terminal64.exe` MT5 |
| Xvfb | display headless `:99` |
| XFCE4 (minimal) | window manager — taskbar, menu, decor window |
| x11vnc | VNC server port 5900 (password via `VNC_PASSWORD`) |
| noVNC + websockify | akses browser port 6901 |

> **Perubahan dari versi lama**: (1) tambah XFCE4 agar window MT5 punya
> taskbar/menu; (2) hapus `-nopw` — sekarang wajib password; (3) tambah noVNC
> agar bisa akses dari browser tanpa install VNC client.

### 3.3 Variabel environment

| Var | Wajib | Default | Catatan |
|-----|-------|---------|---------|
| `VNC_PASSWORD` | ya | — | minimal 6 char. Set di `/opt/lumine/.env` |
| `RESOLUTION` | tidak | `1280x768x24` | resolusi Xvfb |
| `DISPLAY` | tidak | `:99` | display Xvfb |

### 3.4 Service di compose

Service `mt5` sudah ada di `backend/docker-compose.prod.yml`:

```yaml
  mt5:
    build:
      context: ../scripts/deploy/mt5
      dockerfile: Dockerfile
    container_name: lumine-mt5
    ports:
      - "5900:5900"    # VNC client tradisional
      - "6901:6901"    # noVNC via browser
    environment:
      - VNC_PASSWORD=${VNC_PASSWORD:?VNC_PASSWORD wajib di .env}
      - RESOLUTION=1280x768x24
    volumes:
      - mt5_data:/root/.wine-mt5
    restart: unless-stopped
```

Volume `mt5_data` menyimpan Wine prefix + install MT5 + kredensial broker.
Container recreate/rebuild **tidak** menghapus login.

### 3.5 Build & jalankan pertama kali

```bash
cd /opt/lumine/backend
docker compose -f docker-compose.prod.yml up -d --build mt5
```

### 3.6 Akses desktop MT5

**Opsi A — noVNC via browser (paling mudah):**

```
http://<VPS_IP>:6901/vnc.html
```

Masukkan `VNC_PASSWORD` saat diminta. Desktop XFCE4 + jendela MT5 muncul.

**Opsi B — VNC client (TigerVNC, RealVNC):**

```
<VPS_IP>:5900
```

Password sama (`VNC_PASSWORD`).

### 3.7 Login broker (manual, sekali)

1. Buka desktop via noVNC (3.6 Opsi A).
2. Di terminal MT5: `File → Login to Trade Account`.
3. Isi **login, password, server broker**.
4. Kredensial tersimpan di Wine prefix (volume `mt5_data`).

> **Instalasi MT5 pertama kali**: jika `terminal64.exe` belum ada di prefix,
> download installer resmi dan jalankan dari desktop noVNC, atau:
>
> ```bash
> docker compose -f docker-compose.prod.yml exec mt5 bash
> cd /tmp
> wget https://download.mql5.com/cdn/web/metaquotes.software.com/mt5/mt5setup.exe
> wine /tmp/mt5setup.exe /auto
> ```

### 3.8 Install EA (Lumine EA bridge)

1. Compile EA di MetaEditor (atau gunakan `.ex5` yang sudah dikompilasi).
2. Copy ke Wine prefix:
   ```bash
   docker compose -f docker-compose.prod.yml cp lumine_ea.ex5 mt5:"/root/.wine-mt5/drive_c/Program Files/MetaTrader 5/MQL5/Experts/"
   ```
3. Agar EA otomatis menempel di chart saat terminal start:
   - Simpan chart dengan EA sebagai template: `Chart → Template → Save Template` beri nama `LumineEA.tpl`.
   - Letakkan template di `MQL5/Profiles/Templates/`.
   - Buka chart manual via noVNC sekali dan simpan profile default-nya.

> **EA wajib mengakses Redis** (`REDIS_HOST=redis`, port 6379). Jika EA memakai
> pustaka Redis MQL5, pastikan sudah di-compile ke dalam EA. Bridge memakai:
> - `LPUSH mt5:commands` (dari Python) → EA `BRPOP`
> - EA `PUBLISH mt5:results` → Python subscribe

---

## Bagian 4 — Verifikasi Bridge Redis

```bash
cd /opt/lumine/backend

# 1. Semua service hidup
docker compose ps

# 2. Redis reachable dari container MT5
docker compose exec mt5 bash -c 'apt-get install -y redis-tools >/dev/null 2>&1 && redis-cli -h redis ping'
#   → PONG

# 3. Simulasi command dari Python (masuk ke queue)
docker compose exec redis redis-cli lpush mt5:commands '{"command_id":"test-1","action":"PING"}'

# 4. Cek hasil yang dipublish EA (subscriber)
docker compose exec redis redis-cli subscribe mt5:results
#   → tunggu pesan dari EA; jika EA hidup, akan muncul response
```

Jika langkah 4 tidak menerima apa pun dalam 30 detik, periksa:

- `docker compose logs mt5` — terminal crash di Wine? (build MT5 ≥ 4000 rentan)
- EA menempel di chart? (buka VNC dan cek chart)
- EA bisa connect ke Redis? (periksa log EA di `Experts` tab)

---

## Bagian 5 — Troubleshooting & Risiko Terkait Wine

| Gejala | Kemungkinan Penyebab | Solusi |
|--------|----------------------|--------|
| MT5 crash saat start | Build MT5 ≥ 4000 tidak kompatibel dengan Wine | Coba Wine staging (`wine-staging`), atau downgrade build terminal |
| MT5 crash saat running → container restart otomatis | Watchdog di entrypoint mendeteksi `terminal64.exe`/Xvfb/x11vnc mati → exit container → `restart: unless-stopped` bangun ulang | Tidak perlu intervensi. Cek `docker compose logs mt5 --tail 50` baris `WATCHDOG:`. Login broker tetap (volume `mt5_data`) |
| `docker compose ps` mt5 = `(unhealthy)` | Healthcheck gagal — salah satu Xvfb/x11vnc/terminal64.exe tidak jalan | `docker compose logs mt5`; jika watchdog belum exit, tunggu restart policy; jika stuck, `docker compose restart mt5` |
| Login broker gagal | Wine tidak mengizinkan proses tertentu / anti-cheat broker | Periksa log `docker compose logs mt5`; beberapa broker menolak Wine |
| EA tidak dapat akses Redis | EA tidak join network compose | Pastikan service `mt5` di compose file yang sama |
| Layar hitam di VNC / noVNC | Xvfb mati / display salah | `docker compose logs mt5`; pastikan baris `==> Start Xvfb :99` muncul |
| noVNC: `Connection refused` di browser | websockify belum start atau port 6901 ditutup firewall | `curl -sI http://localhost:6901/vnc.html` harus 200; cek `ufw allow 6901` |
| noVNC: minta password terus-menerus | `VNC_PASSWORD` beda antara `.env` dan yang dipakai saat container pertama dibangun | `docker compose -f docker-compose.prod.yml up -d --force-recreate mt5` setelah perbaiki `.env` |
| noVNC: `Server disconnected` (1006) | x11vnc mati setelah MT5 crash | `docker compose logs mt5 --tail 50`; jika `MT5 PID` hilang, terminal crash — restart container |
| VNC client (5900): auth gagal | Password di client ≠ `VNC_PASSWORD` di `.env` | Re-verify `VNC_PASSWORD` di `/opt/lumine/.env`; recreate container |
| `err:toolbar:ToolbarWindowProc unknown msg 0465` di log | Noise Wine MT5 (bukan error) | Abaikan — terminal tetap berjalan selama PID aktif |
| Postgres / Redis restart | RAM habis (Wine + stack > 4GB) | Naikkan RAM VPS ke 8GB; kurangi MT5 memory |

### Risiko produksi

- **Kegagalan broker**: beberapa broker mendeteksi lingkungan non-native dan
  memblokir login / menandai akun.
- **Eksekusi tidak sinkron**: jika terminal Wine crash, EA berhenti memproses
  `mt5:commands` — Python akan timeout 30 detik dan menandai order FAILED
  (perilaku aman, sesuai Phase 8). Container MT5 kini auto-restore: watchdog di
  entrypoint meng-exit container saat `terminal64.exe`/Xvfb/x11vnc mati, lalu
  `restart: unless-stopped` membangkitkan ulang. Window downtime ±15-60 detik
  (tergantung kecepatan Wine init + MT5 start). Login broker tetap karena
  volume `mt5_data` persist.
- **Backup**: state Wine prefix (volume `mt5_data`) **tidak tercakup** oleh
  `backup.sh` saat ini — tambahkan `docker compose exec mt5 tar` ke cron backup
  bila login broker tidak boleh hilang.

---

## Lampiran — Checklist Awal

```bash
# Dari laptop, sekali:
cd scripts/deploy
cp .env.sample .env && $EDITOR .env        # isi VPS_HOST, DB_PASSWORD, HMAC_SECRET_KEY, VNC_PASSWORD
./deploy-stack.sh                          # stack + docker + mt5 service (file sudah di repo)

# Di VPS, sekali (jika MT5 belum terinstall di volume):
cd /opt/lumine/backend
docker compose -f docker-compose.prod.yml up -d --build mt5
# Buka http://<VPS_HOST>:6901/vnc.html → install MT5 via wine (Bagian 3.7)
# Login broker (Bagian 3.7), install EA (Bagian 3.8)
```
