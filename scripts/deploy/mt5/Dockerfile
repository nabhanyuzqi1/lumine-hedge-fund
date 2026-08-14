# syntax=docker/dockerfile:1
# =============================================================================
# Dockerfile — MT5 via Wine + XFCE4 desktop + x11vnc + noVNC (browser access)
#
# Layer:
#   ubuntu:24.04
#     + Wine (i386 + amd64)   -> MT5 (Windows .exe)
#     + Xvfb                  -> display headless :99
#     + XFCE4 (minimal)       -> window manager + taskbar + menu
#     + x11vnc                -> VNC server (password, port 5900)
#     + noVNC + websockify    -> browser access (port 6901)
#
# Port:
#   5900  VNC (untuk VNC client tradisional)
#   6901  noVNC via browser (http://VPS:6901/?password=...)
#
# Env (di-override via compose):
#   VNC_PASSWORD     wajib, minimal 6 char. Jangan pakai default di produksi.
#   DISPLAY          default :99
#   RESOLUTION       default 1280x768x24
# =============================================================================
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    WINEPREFIX=/root/.wine-mt5 \
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

WORKDIR /opt/mt5

COPY entrypoint.sh /opt/mt5/entrypoint.sh
RUN chmod +x /opt/mt5/entrypoint.sh

# LumineEA (Redis bridge agent) — di-copy ke data folder MT5 oleh entrypoint
# dan di-compile via MetaEditor64.exe (headless) saat container start.
RUN mkdir -p /opt/lumine-ea
COPY LumineEA.mq5 /opt/lumine-ea/LumineEA.mq5

EXPOSE 5900 6901
CMD ["/opt/mt5/entrypoint.sh"]
