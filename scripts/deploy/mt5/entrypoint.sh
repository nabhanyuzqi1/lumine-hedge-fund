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
