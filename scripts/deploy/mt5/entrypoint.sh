#!/usr/bin/env bash
# =============================================================================
# entrypoint.sh — MT5 + XFCE4 + x11vnc + noVNC
#
# Urutan start:
#   1. Xvfb            display headless :99
#   2. XFCE4           window manager (taskbar, menu, decor window)
#   3. x11vnc          VNC server port 5900 (password)
#   4. websockify      noVNC browser port 6901
#   5. MT5 (wine)      terminal64.exe
#
# Semua proses di-background; container di-tahan dengan `wait`.
# =============================================================================
set -euo pipefail

# ── Graceful shutdown: simpan workspace MT5 (EA attach persist) ─────────
# Docker stop/restart kirim SIGTERM ke PID 1 (entrypoint). Trap ini
# menjalankan shutdown GRACEFUL sehingga MT5 SAVE workspace (chart + EA
# attachment) sebelum exit:
#   1. xdotool WM_CLOSE (windowclose) → MT5 tampilkan dialog "save?"
#   2. xdotool key Return → klik tombol default (Save) pada dialog
#   3. wineserver -k → fallback cleanup
# Tanpa ini, MT5 di-kill paksa → workspace tidak tersimpan → restart
# berikutnya restore profile lama (EA attach hilang).
graceful_shutdown() {
  echo "==> Graceful shutdown: WM_CLOSE ke MT5 + save workspace..." >&2
  # PITFALL: window title MT5 = "<acc> - <broker>..." (contoh "235158357 -
  # HFMarketsGlobal-Demo4: ...") — TIDAK mengandung "MetaTrader"! Pattern
  # yang stabil: nama broker (HFMarkets) atau WM_CLASS terminal64.
  xdotool search --name "HFMarkets" windowclose 2>/dev/null || true
  xdotool search --class "terminal64" windowclose 2>/dev/null || true
  sleep 4
  # Dialog "Do you want to save..." (jika muncul) menjadi window aktif →
  # Enter menekan tombol default (Save). Tanpa --window = kirim ke fokus.
  xdotool key Return 2>/dev/null || true
  sleep 6
  wineserver -k >/dev/null 2>&1 || true
  sleep 8
  echo "==> Shutdown selesai. Exit." >&2
  exit 0
}
trap graceful_shutdown TERM INT

# ── 0. Validasi ──────────────────────────────────────────────────────────────
if [[ -z "${VNC_PASSWORD:-}" ]]; then
  echo "ERROR: VNC_PASSWORD wajib di-set (env compose). Keluar." >&2
  exit 1
fi
if [[ ${#VNC_PASSWORD} -lt 6 ]]; then
  echo "ERROR: VNC_PASSWORD minimal 6 karakter. Keluar." >&2
  exit 1
fi

# ── 1. Bersih-bersih state lama ──────────────────────────────────────────────
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
wineserver -k >/dev/null 2>&1 || true

# ── 2. Xvfb (display headless) ───────────────────────────────────────────────
echo "==> Start Xvfb :99 (${RESOLUTION})"
Xvfb :99 -screen 0 "${RESOLUTION}" -ac +extension RANDR &
sleep 2

# ── 3. XFCE4 (window manager) ────────────────────────────────────────────────
echo "==> Start XFCE4 session"
# dbus-launch diperlukan agar XFCE4 tidak crash karena missing session bus.
dbus-launch --exit-with-session startxfce4 >/var/log/xfce4.log 2>&1 &
sleep 3

# ── 4. x11vnc (VNC server, password) ─────────────────────────────────────────
echo "==> Start x11vnc port 5900"
# Simpan password hash ke file (rfbauth) — lebih aman dari -passwd yang
# muncul di `ps aux`.
mkdir -p /root/.vnc
x11vnc -storepasswd "${VNC_PASSWORD}" /root/.vnc/passwd
chmod 600 /root/.vnc/passwd

x11vnc -display :99 \
  -rfbauth /root/.vnc/passwd \
  -forever -shared -noxdamage -noxrecord -xkb \
  -bg -o /var/log/x11vnc.log
sleep 1

# ── 5. noVNC via websockify (port 6901) ──────────────────────────────────────
echo "==> Start noVNC (websockify) port 6901"
websockify --web=/usr/share/novnc 0.0.0.0:6901 localhost:5900 \
  >/var/log/websockify.log 2>&1 &
sleep 1

# ── 6. Wine prefix init (sekali) ─────────────────────────────────────────────
if [[ ! -d "${WINEPREFIX}/drive_c" ]]; then
  echo "==> Inisialisasi Wine prefix ..."
  wineboot -i || { echo "ERROR: wineboot GAGAL"; exit 1; }
fi

# ── 7. MT5 terminal ──────────────────────────────────────────────────────────
# Prioritas: HFM (broker) → MetaQuotes generic.
MT5_BIN="${WINEPREFIX}/drive_c/Program Files/HFM Metatrader 5/terminal64.exe"
if [[ ! -f "${MT5_BIN}" ]]; then
  MT5_BIN="${WINEPREFIX}/drive_c/Program Files/MetaTrader 5/terminal64.exe"
fi

if [[ -f "${MT5_BIN}" ]]; then
  # ── Install + compile LumineEA (Redis bridge agent) ──────────────────────
  # Data folder MT5: mode portable → <MT5_DIR>/MQL5 (bukan AppData/MetaQuotes)
  MT5_DATA_DIR=$(find "${WINEPREFIX}/drive_c" -type d -name "MQL5" 2>/dev/null | head -1)
  if [[ -n "${MT5_DATA_DIR}" ]]; then
    echo "==> MT5 data dir: ${MT5_DATA_DIR}"
    mkdir -p "${MT5_DATA_DIR}/Experts"
    cp -f /opt/lumine-ea/LumineEA.mq5 "${MT5_DATA_DIR}/Experts/LumineEA.mq5"

    # ── Patch terminal.ini: auto-whitelist WebRequest URL ─────────────────
    # MT5 menyimpan whitelist di terminal.ini [Experts]\AllowWebRequest=...
    # PITFALL: sed/echo menulis ASCII ke file UTF-16LE → mojibake (key tidak
    # terbaca MT5). WAJIB decode → modify → encode ulang UTF-16LE via python.
    MT5_INI="${MT5_DATA_DIR}/../Config/terminal.ini"
    if [[ -f "${MT5_INI}" ]]; then
      echo "==> Patch terminal.ini: auto-whitelist http://lumine.biz.id + RestoreLast=1"
      python3 - "${MT5_INI}" <<'PYEOF'
import sys
path = sys.argv[1]
with open(path, "rb") as f:
    raw = f.read()
# Normalisasi: hapus BOM jika ada, decode UTF-16LE
if raw[:2] == b"\xff\xfe" or raw[:2] == b"\xfe\xff":
    raw = raw[2:]
text = raw.decode("utf-16-le")
# CRLF explicit (hindari literal newline dalam heredoc)
CRLF = chr(13) + chr(10)
lines = text.split(CRLF)
# Hapus entry lama (idempotent)
lines = [l for l in lines if not l.strip().startswith(("AllowWebRequest=", "RestoreLast="))]
# Pastikan section [Experts] dengan AllowWebRequest
def ensure_section(lines, section, keyvals):
    sec_idx = None
    for i, l in enumerate(lines):
        if l.strip() == section:
            sec_idx = i
            break
    if sec_idx is None:
        lines.append("")
        lines.append(section)
        sec_idx = len(lines) - 1
    insert_at = sec_idx + 1
    for kv in reversed(keyvals):
        lines.insert(insert_at, kv)
    return lines

lines = ensure_section(lines, "[Experts]", ["AllowWebRequest=http://lumine.biz.id"])
lines = ensure_section(lines, "[Common]", ["RestoreLast=1"])
new_text = CRLF.join(lines)
# Tulis ulang dengan BOM + CRLF (format Windows)
with open(path, "wb") as f:
    f.write(b"\xff\xfe" + new_text.encode("utf-16-le"))
print("    -> terminal.ini patched OK")
PYEOF
    else
      echo "==> terminal.ini tidak ditemukan (first boot?) — whitelist persist setelah manual setup pertama kali"
    fi

    METAEDITOR="${MT5_BIN%/terminal64.exe}/MetaEditor64.exe"
    if [[ -f "${METAEDITOR}" ]]; then
      echo "==> Compile LumineEA via MetaEditor (headless)..."
      # Retry ×3 dengan wineserver reset: compile pertama bisa hang karena
      # state wineserver dari proses yang di-kill (SIGKILL → lock stale).
      for attempt in 1 2 3; do
        # || true: pkill tanpa match return 1 → set -e langsung exit!
        pkill -9 wineserver 2>/dev/null || true
        pkill -9 wine64-preloader 2>/dev/null || true
        sleep 1
        # -k 10: wine bisa abaikan SIGTERM → paksa SIGKILL setelah 10s grace.
        timeout -k 10 90 wine "${METAEDITOR}" /compile:"${MT5_DATA_DIR}/Experts/LumineEA.mq5" /log:"${MT5_DATA_DIR}/Experts/lumineea_compile.log" >/dev/null 2>&1 || true
        pkill -9 wineserver 2>/dev/null || true
        pkill -9 wine64-preloader 2>/dev/null || true
        sleep 2
        if [[ -f "${MT5_DATA_DIR}/Experts/LumineEA.ex5" ]]; then
          echo "==> LumineEA.ex5 COMPILED OK (attempt ${attempt})"
          break
        fi
        echo "==> attempt ${attempt}: ex5 belum ada — retry"
      done
      if [[ ! -f "${MT5_DATA_DIR}/Experts/LumineEA.ex5" ]]; then
        echo "==> WARNING: LumineEA compile gagal — cek ${MT5_DATA_DIR}/Experts/lumineea_compile.log" >&2
      fi
    else
      echo "==> WARNING: MetaEditor64.exe tidak ditemukan — attach manual dari VNC"
    fi
  else
    echo "==> WARNING: MQL5 data dir belum ada (terminal belum pernah jalan) — install EA setelah login"
  fi

  echo "==> Jalankan MT5: ${MT5_BIN}"
  wine "${MT5_BIN}" &
  MT_PID=$!
  echo "==> MT5 PID: ${MT_PID}"
  echo "==> Akses desktop: http://<VPS_HOST>:6901/vnc.html  (password VNC_PASSWORD)"

  # ── Watchdog foreground polling ────────────────────────────────────────────
  # restart: unless-stopped (compose) akan membangkitkan ulang container.
  # Named volume mt5_data tetap utuh lintas recreate — login broker tidak hilang.
  #
  # Catatan implementasi: JANGAN pakai background subshell (`fn &`) dengan
  # `exit 1` di dalamnya — `exit` hanya membunuh subshell, bukan parent yang
  # blocked di `wait`. Container tetap Up walau proses kritis mati. Polling
  # loop di foreground ini meng-exit entrypoint langsung saat kondisi gagal.
  echo "==> Watchdog aktif (polling 5s)"
  while true; do
    # MT5 mati? (wine wrapper PID atau terminal64.exe hilang)
    if ! kill -0 "${MT_PID}" 2>/dev/null \
        && ! pgrep -f 'terminal64\.exe' >/dev/null 2>&1; then
      echo "==> WATCHDOG: MT5 (terminal64.exe) mati. Exit container untuk auto-restore." >&2
      exit 1
    fi
    # Xvfb display :99 mati?
    if ! pgrep -x Xvfb >/dev/null 2>&1; then
      echo "==> WATCHDOG: Xvfb mati. Exit container untuk auto-restore." >&2
      exit 1
    fi
    # x11vnc server mati?
    if ! pgrep -x x11vnc >/dev/null 2>&1; then
      echo "==> WATCHDOG: x11vnc mati. Exit container untuk auto-restore." >&2
      exit 1
    fi
    sleep 5
  done
  # Tidak tercapai — loop di atas exit saat salah satu kondisi gagal.
  # Container exit → restart: unless-stopped → rebuild + volume persist.
else
  echo "==> MT5 belum terinstall. Akses via noVNC untuk installer manual."
  echo "    Browser: http://<VPS_HOST>:6901/vnc.html"
  # Tetap hidup agar user bisa install MT5 via noVNC. Tidak ada watchdog:
  # MT5 belum ada untuk dipantau.
  sleep infinity
fi
