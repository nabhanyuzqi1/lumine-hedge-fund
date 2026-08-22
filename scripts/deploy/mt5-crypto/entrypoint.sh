#!/usr/bin/env bash
# =============================================================================
# entrypoint-crypto.sh — MT5 Exness + XFCE4 + x11vnc + noVNC
# Instance crypto (BTCUSD) untuk streaming harga 24/7 saat forex libur.
#
# Perbedaan dari entrypoint HFM:
#   - WINEPREFIX=/root/.wine-mt5-crypto (volume terpisah)
#   - Install MT5 resmi dari mql5.com (bukan branded HFM)
#   - Login Exness-MT5Trial17 (akun 463852058)
#   - EA LumineEA di-attach ke chart BTCUSD
#   - Proxy via /mt5-proxy-crypto (Caddy set header X-Instance: crypto)
# =============================================================================
set -euo pipefail

MT5_INSTALLER_URL="https://download.mql5.com/cdn/web/metaquotes.ltd/mt5/mt5setup.exe"
MT5_BIN="${WINEPREFIX}/drive_c/Program Files/MetaTrader 5/terminal64.exe"
EA_SYMBOL="BTCUSD"
EXNESS_LOGIN="463852058"
EXNESS_PASS="@Yuzqi07070"
EXNESS_SERVER="Exness-MT5Trial17"

# ── Graceful shutdown ──
graceful_shutdown() {
  echo "==> Graceful shutdown: WM_CLOSE ke MT5 crypto..." >&2
  xdotool search --name "Exness" windowclose 2>/dev/null || true
  xdotool search --class "terminal64" windowclose 2>/dev/null || true
  sleep 4
  xdotool key Return 2>/dev/null || true
  sleep 6
  wineserver -k >/dev/null 2>&1 || true
  sleep 8
  echo "==> Shutdown selesai." >&2
  exit 0
}
trap graceful_shutdown TERM INT

# ── 0. Validasi ──
if [[ -z "${VNC_PASSWORD:-}" ]]; then
  echo "ERROR: VNC_PASSWORD wajib di-set. Keluar." >&2
  exit 1
fi

# ── 1. Bersih ──
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
wineserver -k >/dev/null 2>&1 || true

# ── 2. Xvfb ──
echo "==> Start Xvfb :99 (${RESOLUTION})"
Xvfb :99 -screen 0 "${RESOLUTION}" -ac +extension RANDR &
sleep 2

# ── 3. XFCE4 ──
echo "==> Start XFCE4 session"
dbus-launch --exit-with-session startxfce4 >/var/log/xfce4-crypto.log 2>&1 &
sleep 3

# ── 4. x11vnc ──
echo "==> Start x11vnc port 5900"
mkdir -p /root/.vnc
x11vnc -storepasswd "${VNC_PASSWORD}" /root/.vnc/passwd
chmod 600 /root/.vnc/passwd
x11vnc -display :99 \
  -rfbauth /root/.vnc/passwd \
  -forever -shared -noxdamage -noxrecord -xkb \
  -bg -o /var/log/x11vnc-crypto.log
sleep 1

# ── 5. noVNC ──
echo "==> Start noVNC port 6901"
websockify --web=/usr/share/novnc 0.0.0.0:6901 localhost:5900 \
  >/var/log/websockify-crypto.log 2>&1 &
sleep 1

# ── 6. Wine prefix init ──
if [[ ! -d "${WINEPREFIX}/drive_c" ]]; then
  echo "==> Inisialisasi Wine prefix ..."
  wineboot -i || { echo "ERROR: wineboot GAGAL"; exit 1; }
fi

# ── 7. Install MT5 (sekali) ──
if [[ ! -f "${MT5_BIN}" ]]; then
  echo "==> Download MT5 installer dari mql5.com ..."
  wget -q -O /tmp/mt5setup.exe "${MT5_INSTALLER_URL}" || {
    echo "ERROR: download MT5 installer gagal"; exit 1;
  }
  echo "==> Install MT5 (silent) ..."
  # PITFALL (22 Aug 2026): InnoSetup /S di wine BISA hang menunggu dialog
  # (update check) — jalankan dengan timeout 120s, jangan block forever.
  # Kalau timeout, MT5_BIN biasanya sudah terinstall (silent install cepat),
  # kill sisa proses lalu lanjut.
  timeout 120 wine /tmp/mt5setup.exe /S || {
    echo "WARN: installer timeout/silent — cek MT5_BIN manual, lanjut"
    pkill -f mt5setup.exe 2>/dev/null || true
    pkill -f start.exe 2>/dev/null || true
  }
  sleep 5
  wineserver -k 2>/dev/null || true
  sleep 3
fi

if [[ ! -f "${MT5_BIN}" ]]; then
  echo "ERROR: MT5 tidak terinstall di ${MT5_BIN}"
  ls "${WINEPREFIX}/drive_c/Program Files/" 2>/dev/null
  exit 1
fi

# ── 8. Setup EA ──
MT5_DATA_DIR=$(find "${WINEPREFIX}/drive_c" -type d -name "MQL5" 2>/dev/null | head -1)
if [[ -z "${MT5_DATA_DIR}" ]]; then
  # Cari di lokasi lain
  MT5_DATA_DIR=$(find "${WINEPREFIX}/drive_c/users" -type d -name "MQL5" 2>/dev/null | head -1)
fi
if [[ -z "${MT5_DATA_DIR}" ]]; then
  echo "ERROR: MQL5 folder tidak ditemukan"
  MT5_DATA_DIR="${WINEPREFIX}/drive_c/users/root/AppData/Roaming/MetaQuotes/Terminal/Common/MQL5"
  mkdir -p "${MT5_DATA_DIR}/Experts"
fi
echo "==> MT5 data dir: ${MT5_DATA_DIR}"

mkdir -p "${MT5_DATA_DIR}/Experts"
cp -f /opt/lumine-ea/LumineEA.mq5 "${MT5_DATA_DIR}/Experts/LumineEA.mq5"

# Patch terminal.ini — whitelist proxy
TERMINAL_INI="${MT5_DATA_DIR}/terminal.ini"
if [[ -f "${TERMINAL_INI}" ]]; then
  # Tambah AllowWebRequest jika belum ada
  if ! grep -q "AllowWebRequest" "${TERMINAL_INI}" 2>/dev/null; then
    cat >> "${TERMINAL_INI}" <<'EOF'

[Experts]
AllowWebRequest=http://lumine.biz.id/mt5-proxy-crypto
EOF
  fi
fi

# ── 9. Compile EA ──
METAEDITOR="${MT5_BIN%/terminal64.exe}/MetaEditor64.exe"
if [[ -f "${METAEDITOR}" ]]; then
  echo "==> Compile LumineEA (crypto instance)..."
  # copy EA source
  wine "${METAEDITOR}" /compile:"${MT5_DATA_DIR}/Experts/LumineEA.mq5" /log:"${MT5_DATA_DIR}/Experts/compile-crypto.log" 2>/dev/null || true
  sleep 2
  if [[ -f "${MT5_DATA_DIR}/Experts/LumineEA.ex5" ]]; then
    echo "==> Compile OK: LumineEA.ex5"
  else
    echo "WARN: compile mungkin gagal — cek log"
    cat "${MT5_DATA_DIR}/Experts/compile-crypto.log" 2>/dev/null | tail -10
  fi
fi

# ── 10. Login Exness + attach EA ──
# Pertama: login dulu (MT5 auto-save credentials setelah login sukses)
echo "==> Login Exness account ${EXNESS_LOGIN} ..."
wine "${MT5_BIN}" /login:"${EXNESS_LOGIN}" /password:"${EXNESS_PASS}" /server:"${EXNESS_SERVER}" &
sleep 15

# Login akan menyimpan kredensial; selanjutnya terminal bisa jalan normal
# Restore workspace (chart BTCUSD + EA) dari backup jika ada
WORKSPACE_BACKUP="${WINEPREFIX}/lumine-workspace-crypto-backup"
if [[ -d "${WORKSPACE_BACKUP}" ]]; then
  echo "==> Restore workspace crypto (EA attach BTCUSD)"
  mkdir -p "${MT5_DATA_DIR}/Profiles/Charts/Default"
  cp -r "${WORKSPACE_BACKUP}"/* "${MT5_DATA_DIR}/Profiles/Charts/Default/" 2>/dev/null || true
  # Restart MT5 agar workspace termuat
  wineserver -k 2>/dev/null || true
  sleep 3
  wine "${MT5_BIN}" /login:"${EXNESS_LOGIN}" /password:"${EXNESS_PASS}" /server:"${EXNESS_SERVER}" &
  sleep 8
  echo "==> Workspace restored (EA attached to ${EA_SYMBOL})"
else
  echo "==> No workspace backup — jalankan MT5 manual via VNC untuk setup"
  echo "    Setup: buka chart ${EA_SYMBOL}, attach EA LumineEA,"
  echo "    set InpProxyURL=http://lumine.biz.id/mt5-proxy-crypto,"
  echo "    set InpSeedSymbols=BTCUSD,"
  echo "    save profile Default, backup folder: ${WORKSPACE_BACKUP}"
fi

# ── 11. Hold ──
echo "==> Container crypto ready — hold"
wait