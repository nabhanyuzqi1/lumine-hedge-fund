# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# VITE_API_BASE_URL relatif ("/api/v1") — resolve ke origin halaman
# (https://lumine.biz.id/api/v1 di prod). Tanpa IP/domain hardcode:
# origin server tidak terekspos, zero CORS.
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
# VITE_API_URL kosong → relative path → origin halaman (Caddy proxy).
# Jangan default localhost:8000 (alamat browser user) atau IP HTTP
# (mixed content di HTTPS) — keduanya bikin "Network request failed".
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL
# HMAC credentials (getHmacCredentials) — wajib di-declare + ENV agar Vite
# meng-inline import.meta.env.VITE_LUMINE_* saat build.
ARG VITE_LUMINE_API_KEY=
ENV VITE_LUMINE_API_KEY=$VITE_LUMINE_API_KEY
ARG VITE_LUMINE_API_SECRET=
ENV VITE_LUMINE_API_SECRET=$VITE_LUMINE_API_SECRET
RUN npm run build

# ── Stage 2: Static serve ─────────────────────────────────────────────────────
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
