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

### 3.1 Struktur folder

Buat di VPS:

```bash
mkdir -p /opt/lumine/mt5
cd /opt/lumine/mt5
```

### 3.2 Dockerfile

```dockerfile
# /opt/lumine/mt5/Dockerfile
FROM ubuntu:24.04

# Wine + tooling headless
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      wine64 wine32:i386 \
      xvfb x11vnc wget unzip ca-certificates && \
    rm -rf /var/lib/apt/lists/*

ENV WINEPREFIX=/root/.wine-mt5 \
    WINEDLLOVERRIDES="mscoree,mshtml=" \
    DISPLAY=:99

WORKDIR /opt/mt5

COPY entrypoint.sh /opt/mt5/entrypoint.sh
RUN chmod +x /opt/mt5/entrypoint.sh

EXPOSE 5900
CMD ["/opt/mt5/entrypoint.sh"]
```

### 3.3 Entrypoint (headless + VNC)

```bash
#!/usr/bin/env bash
# /opt/lumine/mt5/entrypoint.sh
set -e

# Inisialisasi Wine prefix sekali
if [ ! -d "${WINEPREFIX}" ]; then
  wineboot -i
fi

# Display headless
Xvfb :99 -screen 0 1280x768x24 &
sleep 2

# VNC viewer untuk login broker manual
x11vnc -display :99 -forever -nopw -shared -bg -o /var/log/x11vnc.log

# Terminal MT5
MT5_BIN="${WINEPREFIX}/drive_c/Program Files/MetaTrader 5/terminal64.exe"
if [ -f "${MT5_BIN}" ]; then
  wine "${MT5_BIN}" &
  wait
else
  echo "MT5 belum terinstall — jalankan installer dulu (lihat 3.5)."
  sleep infinity
fi
```

### 3.4 Tambahkan service ke compose stack

Edit `/opt/lumine/backend/docker-compose.prod.yml` — tambahkan service ini
(di bawah `api`):

```yaml
  mt5:
    build:
      context: /opt/lumine/mt5
      dockerfile: Dockerfile
    ports:
      - "5900:5900"
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - MT5_LOGIN=
      - MT5_PASSWORD=
      - MT5_SERVER=
    volumes:
      - mt5_data:/root/.wine-mt5
    restart: unless-stopped
```

Lalu tambahkan `mt5_data:` ke blok `volumes:` di bawah:

```yaml
volumes:
  postgres_data:
  redis_data:
  mt5_data:
```

> Kenapa volume `mt5_data`? Wine prefix berisi konfigurasi login broker — kalau
> container di-recreate, login tidak hilang.

### 3.5 Build & jalankan pertama kali

```bash
cd /opt/lumine/backend
docker compose up -d --build mt5
```

### 3.6 Login broker (manual, sekali)

MT5 membutuhkan login interaktif ke server broker. Lakukan via VNC:

1. Di laptop: `open vnc://root@<VPS_IP>:5900` (atau pakai RealVNC/TigerVNC)
2. Di dalam terminal MT5: `File → Login to Trade Account`
3. Isi **login, password, server broker**
4. Setelah masuk, terminal akan menyimpan kredensial di Wine prefix

> **Instalasi MT5 pertama kali**: jika `terminal64.exe` belum ada di prefix,
> download installer resmi dan jalankan sekali:
>
> ```bash
> docker compose exec mt5 bash
> cd /tmp
> wget https://download.mql5.com/cdn/web/metaquotes.software.com/mt5/mt5setup.exe
> wine /tmp/mt5setup.exe /auto
> ```

### 3.7 Install EA (Lumine EA bridge)

1. Compile EA di MetaEditor (atau gunakan `.ex5` yang sudah dikompilasi)
2. Copy ke Wine prefix:
   ```bash
   docker compose cp lumine_ea.ex5 mt5:"/root/.wine-mt5/drive_c/Program Files/MetaTrader 5/MQL5/Experts/"
   ```
3. Agar EA otomatis menempel di chart saat terminal start:
   - Simpan chart dengan EA sebagai template: `Chart → Template → Save Template` beri nama `LumineEA.tpl`
   - Letakkan template di `MQL5/Profiles/Templates/`
   - Entrypoint menjalankan `terminal64.exe` dengan `config` yang memuat template — atau cukup
     buka chart manual via VNC sekali dan simpan profile default-nya.

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
| Login broker gagal | Wine tidak mengizinkan proses tertentu / anti-cheat broker | Periksa log `docker compose logs mt5`; beberapa broker menolak Wine |
| EA tidak dapat akses Redis | EA tidak join network compose | Pastikan service `mt5` di compose file yang sama |
| Layar hitam di VNC | Xvfb mati / display salah | `docker compose logs mt5`; pastikan `Xvfb :99` jalan |
| Postgres / Redis restart | RAM habis (Wine + stack > 4GB) | Naikkan RAM VPS ke 8GB; kurangi MT5 memory |

### Risiko produksi

- **Kegagalan broker**: beberapa broker mendeteksi lingkungan non-native dan
  memblokir login / menandai akun.
- **Eksekusi tidak sinkron**: jika terminal Wine crash, EA berhenti memproses
  `mt5:commands` — Python akan timeout 30 detik dan menandai order FAILED
  (perilaku aman, sesuai Phase 8).
- **Backup**: state Wine prefix (volume `mt5_data`) **tidak tercakup** oleh
  `backup.sh` saat ini — tambahkan `docker compose exec mt5 tar` ke cron backup
  bila login broker tidak boleh hilang.

---

## Lampiran — Checklist Awal

```bash
# Dari laptop, sekali:
cd scripts/deploy
cp .env.sample .env && $EDITOR .env
./deploy-stack.sh                          # stack + docker
./import-state.sh state-exports/<stamp>.tar.gz   # state (opsional)

# Di VPS, sekali:
mkdir -p /opt/lumine/mt5
# (tulis Dockerfile + entrypoint.sh dari Bagian 3.2/3.3)
cd /opt/lumine/backend && $EDITOR docker-compose.prod.yml   # tambah service mt5
docker compose up -d --build mt5
# VNC login broker (Bagian 3.6), install EA (Bagian 3.7)
```
