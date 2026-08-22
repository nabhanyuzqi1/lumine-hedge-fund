# syntax=docker/dockerfile:1
# =============================================================================
# Dockerfile — MT5 crypto instance (Exness, BTCUSD streaming 24/7)
#
# Sama seperti instance HFM (scripts/deploy/mt5/Dockerfile) tapi:
#   - WINEPREFIX=/root/.wine-mt5-crypto (volume terpisah)
#   - entrypoint-crypto.sh: install MT5 resmi mql5.com + login Exness
#   - EA seed BTCUSD (bukan XAUUSD) → streaming harga crypto saat forex libur
# =============================================================================
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    WINEPREFIX=/root/.wine-mt5-crypto \
    WINEDLLOVERRIDES="mscoree,mshtml=" \
    DISPLAY=:99 \
    RESOLUTION=1280x768x24 \
    VNC_PASSWORD=lumine2026

# ── Wine + desktop + VNC + noVNC ─────────────────────────────────────────────
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      wine wine64 wine32:i386 \
      xvfb x11vnc \
      xfce4 xfce4-terminal dbus-x11 \
      novnc websockify \
      xdotool wmctrl \
      wget unzip ca-certificates fonts-liberation && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/mt5-crypto

COPY entrypoint.sh /opt/mt5-crypto/entrypoint.sh
RUN chmod +x /opt/mt5-crypto/entrypoint.sh

# LumineEA — bind mount /opt/lumine-ea di compose (sama seperti HFM)
RUN mkdir -p /opt/lumine-ea

EXPOSE 5900 6901
CMD ["/opt/mt5-crypto/entrypoint.sh"]
