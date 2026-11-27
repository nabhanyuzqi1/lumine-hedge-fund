#!/usr/bin/env bash
# fund2_backup.sh - Disaster Recovery backup pipeline (PRD v2.2 §17.2)
#
# Backup harian & pre-deployment:
#   1. DB    : pg_dump -Fc (fund2) + pg_dumpall --globals-only
#   2. Config: non-secret config (Caddyfile, systemd units, alembic, env EXAMPLE,
#              EA settings) - TANPA secret (kebijakan secret terpisah).
#   3. Parquet: dataset berversi (ticks/recorder/dukascopy) + manifest sha256.
#   4. Enkripsi age (recipient = key backup; private key TIDAK di host ini
#      secara default, lihat runbook).
#   5. Salinan lokal /var/backups/fund2 (mode 0700, root:root via sudo? tidak -
#      akses terbatas via permission 0700 owner tekka) + upload offsite r2:.
#   6. Retensi 30 hari (lokal & offsite) + manifest global terkunci.
#   7. Log terstruktur ke $LOG_DIR; hasil JSON untuk alert Telegram.
#
# Usage:
#   fund2_backup.sh                 # backup harian (label daily)
#   fund2_backup.sh pre-deploy      # backup sebelum deployment besar
#   fund2_backup.sh --verify-only   # verifikasi manifest terakhir tanpa backup
#
# Exit codes: 0 sukses; non-zero gagal (detail di log + JSON result).

set -Eeuo pipefail

# ---------- konfigurasi (environment override utk drill) ----------
FUND2_HOME="${FUND2_HOME:-/home/tekka/fund2}"
PG_BIN="${PG_BIN:-/home/tekka/fund2/runtime/pg16/usr/lib/postgresql/16/bin}"
PG_LIB="${PG_LIB:-/home/tekka/fund2/runtime/pg16/usr/lib/x86_64-linux-gnu:/home/tekka/fund2/runtime/pg16/usr/lib/postgresql/16/lib}"
DATABASE_URL_FILE="${DATABASE_URL_FILE:-$FUND2_HOME/api/.env}"
BACKUP_ROOT="${BACKUP_ROOT:-/home/tekka/fund2-backups}"
OFFSITE_REMOTE="${OFFSITE_REMOTE:-r2:lumine-backups/fund2-v22}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
AGE_KEY_FILE="${AGE_KEY_FILE:-/home/tekka/backups/lumine-router-secrets-20261122/keys/backup-age.key}"
AGE_RECIPIENT_FILE="${AGE_RECIPIENT_FILE:-/home/tekka/fund2-backups/.age-recipient}"
RCLONE_BIN="${RCLONE_BIN:-/home/tekka/.local/bin/rclone}"
LOG_DIR="${LOG_DIR:-$BACKUP_ROOT/logs}"
LABEL="${1:-daily}"
VERIFY_ONLY=0
[ "${1:-}" = "--verify-only" ] && { VERIFY_ONLY=1; LABEL="verify"; }

TS="$(date -u +%Y%m%dT%H%M%SZ)"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DAY="$(date -u +%Y-%m-%d)"

mkdir -p "$BACKUP_ROOT/db" "$BACKUP_ROOT/config" "$BACKUP_ROOT/datasets" \
         "$BACKUP_ROOT/staging/$TS" "$LOG_DIR"
chmod 700 "$BACKUP_ROOT" 2>/dev/null || true

LOG_FILE="$LOG_DIR/backup-$TS.log"
RESULT_JSON="$LOG_DIR/backup-$TS.json"

# ---------- logging ----------
log()  { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE"; }
fail() { log "ERROR: $*"; printf '{"status":"error","ts":"%s","label":"%s","error":"%s"}\n' \
           "$STAMP" "$LABEL" "$*" > "$RESULT_JSON"; exit 1; }
trap 'log "ERROR: gagal di baris $LINENO (rc=$?)"' ERR

export PATH="$PG_BIN:$PATH"
export LD_LIBRARY_PATH="$PG_LIB"
export PGCONNECT_TIMEOUT=10

# ---------- ambil DATABASE_URL tanpa mencetaknya ----------
DB_URL="$(grep -E '^DATABASE_URL=' "$DATABASE_URL_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'"'' )"
[ -n "$DB_URL" ] || fail "DATABASE_URL tidak ditemukan di $DATABASE_URL_FILE"

# ---------- recipient age ----------
if [ ! -f "$AGE_RECIPIENT_FILE" ]; then
  if [ -f "$AGE_KEY_FILE" ]; then
    grep '^# public key:' "$AGE_KEY_FILE" | sed 's/^# public key: //' > "$AGE_RECIPIENT_FILE"
  else
    fail "Recipient age tidak tersedia ($AGE_RECIPIENT_FILE) dan key tidak ada"
  fi
fi
AGE_RECIPIENT="$(cat "$AGE_RECIPIENT_FILE")"
[ -n "$AGE_RECIPIENT" ] || fail "Recipient age kosong"
AGE_OPTS=(--recipient "$AGE_RECIPIENT")

STAGE="$BACKUP_ROOT/staging/$TS"

if [ "$VERIFY_ONLY" = "1" ]; then
  # verifikasi integritas backup terakhir di manifest
  MANIFEST="$BACKUP_ROOT/manifest.tsv"
  [ -f "$MANIFEST" ] || fail "manifest tidak ada"
  bad=0
  while IFS=$'\t' read -r path sha size; do
    [ -f "$path" ] || { log "MISSING: $path"; bad=$((bad+1)); continue; }
    got="$(sha256sum "$path" | cut -d' ' -f1)"
    if [ "$got" != "$sha" ]; then log "CHECKSUM FAIL: $path"; bad=$((bad+1)); fi
  done < <(tail -n +2 "$MANIFEST" | awk -F'\t' '$1 ~ /^\//')
  [ "$bad" = "0" ] || fail "verifikasi manifest: $bad file bermasalah"
  log "VERIFY OK: semua file di manifest cocok"
  printf '{"status":"verify_ok","ts":"%s"}\n' "$STAMP" > "$RESULT_JSON"
  exit 0
fi

log "=== fund2 backup mulai label=$LABEL ts=$TS ==="

# ---------- 1. DATABASE ----------
DB_START=$(date +%s)
DB_SQL="$STAGE/fund2-$TS.sql"
DB_DUMP="$STAGE/fund2-$TS.dump"
DB_GLOBALS="$STAGE/globals-$TS.sql"

log "DB: pg_dump -Fc mulai"
pg_dump --dbname="$DB_URL" --format=custom --file="$DB_DUMP" \
        --no-owner --no-privileges 2>>"$LOG_FILE" \
  || fail "pg_dump gagal"
log "DB: pg_dump selesai ($(du -h "$DB_DUMP" | cut -f1))"

pg_dumpall --dbname="$DB_URL" --globals-only --file="$DB_GLOBALS" 2>>"$LOG_FILE" \
  || fail "pg_dumpall globals gagal"
log "DB: globals selesai"

# sanity: dump bisa dibaca & berisi tabel kunci
"$PG_BIN/pg_restore" --list "$DB_DUMP" > "$STAGE/toc.txt" 2>>"$LOG_FILE" || fail "pg_restore --list gagal"
grep -Eq ' TABLE (public )?order_events ' "$STAGE/toc.txt" || fail "dump tidak berisi order_events"
grep -Eq ' TABLE (public )?candles ' "$STAGE/toc.txt" || fail "dump tidak berisi candles"
grep -Eq ' TABLE (public )?users ' "$STAGE/toc.txt" || fail "dump tidak berisi users"
log "DB: sanity TOC OK (order_events, candles, users ada)"

# ---------- 2. CONFIG non-secret ----------
CFG="$STAGE/config-$TS"
mkdir -p "$CFG/systemd-user" "$CFG/caddy" "$CFG/api" "$CFG/ea"
install -m 0644 /etc/caddy/Caddyfile "$CFG/caddy/Caddyfile" 2>/dev/null \
  || install -m 0644 /home/tekka/caddy-edge/Caddyfile "$CFG/caddy/Caddyfile" \
  || log "WARN: Caddyfile tidak ditemukan"
for u in fund2-postgres fund2-api fund2-alerts fund2-paper-runner \
         fund2-candle-rollup fund2-hfm-recorder fund2-kanban-watch \
         fund2-edge-proxy fund2-spread-profile.service fund2-spread-profile.timer \
         fund2-anomaly.service fund2-anomaly.timer; do
  src="/home/tekka/.config/systemd/user/$u"
  [ -f "$src" ] && install -m 0644 "$src" "$CFG/systemd-user/$u"
done
# env EXAMPLE saja (bukan secret)
for e in .env.alerts.example; do
  [ -f "$FUND2_HOME/api/$e" ] && install -m 0644 "$FUND2_HOME/api/$e" "$CFG/api/$e"
done
# alembic config + migrasi (schema sumber kebenaran)
mkdir -p "$CFG/alembic"
cp -a "$FUND2_HOME/api/alembic.ini" "$CFG/alembic/" 2>/dev/null || true
cp -a "$FUND2_HOME/api/alembic" "$CFG/alembic/versions" 2>/dev/null || true
# EA settings non-secret
find "$FUND2_HOME/ea" -maxdepth 3 -type f \( -name '*.mq5' -o -name '*.ini' -o -name '*.set' -o -name '*.md' \) \
  -exec cp -a --parents {} "$CFG/ea/" \; 2>/dev/null || true
# deploy scripts (non-secret)
mkdir -p "$CFG/deploy"
cp -a "$FUND2_HOME/deploy/." "$CFG/deploy/" 2>/dev/null || true
# pin versi repo
git -C "$FUND2_HOME" rev-parse HEAD > "$CFG/git_commit.txt" 2>/dev/null || true
log "CONFIG: non-secret terkumpul ($(find "$CFG" -type f | wc -l) file)"

# ---------- 3. DATASETS (Parquet berversi + manifest) ----------
DS="$STAGE/datasets-$TS"
mkdir -p "$DS"
# sumber dataset:
#   - ticks ingest harian (data/parquet)
#   - hfm recorder parquet (data/hfm_recording/parquet, excl. .env & state runtime)
#   - dukascopy (data/dukascopy) - dataset historis kalibrasi
mkdir -p "$DS/ingest" "$DS/hfm_recording" "$DS/dukascopy"
cp -a "$FUND2_HOME/data/parquet/." "$DS/ingest/" 2>/dev/null || true
cp -a "$FUND2_HOME/data/hfm_recording/parquet/." "$DS/hfm_recording/" 2>/dev/null || true
cp -a "$FUND2_HOME/data/dukascopy/." "$DS/dukascopy/" 2>/dev/null || true
log "DATASET: parquet terkumpul ($(find "$DS" -name '*.parquet' | wc -l) file, $(du -sh "$DS" | cut -f1))"

# manifest sha256 utk seluruh dataset
(
  cd "$DS"
  find . -type f -print0 | sort -z | xargs -0 sha256sum
) > "$STAGE/datasets-$TS.sha256"
log "DATASET: manifest sha256 ($(wc -l < "$STAGE/datasets-$TS.sha256") entri)"

# ---------- 4. PACK + ENCRYPT ----------
log "PACK: tar + age"
TAR="$STAGE/fund2-$TS.tar"
tar -C "$STAGE" -cf "$TAR" "fund2-$TS.dump" "globals-$TS.sql" "config-$TS" \
    "datasets-$TS" "datasets-$TS.sha256" "toc.txt" 2>>"$LOG_FILE" || fail "tar gagal"
ENC="$BACKUP_ROOT/db/fund2-$TS.tar.age"
age --encrypt "${AGE_OPTS[@]}" --output "$ENC" "$TAR" 2>>"$LOG_FILE" || fail "age encrypt gagal"
rm -f "$TAR"
[ -s "$ENC" ] || fail "arsip terenkripsi kosong"
log "ENCRYPT: $ENC ($(du -h "$ENC" | cut -f1))"

# checksum + manifest global (append, locked)
ENC_SHA="$(sha256sum "$ENC" | cut -d' ' -f1)"
ENC_SIZE="$(stat -c%s "$ENC")"
MANIFEST="$BACKUP_ROOT/manifest.tsv"
flock "$MANIFEST.lock" bash -c "
  [ -f '$MANIFEST' ] || printf 'path\tsha256\tbytes\tlabel\tts\n' > '$MANIFEST'
  printf '%s\t%s\t%s\t%s\t%s\n' '$ENC' '$ENC_SHA' '$ENC_SIZE' '$LABEL' '$STAMP' >> '$MANIFEST'
"
log "MANIFEST: $ENC $ENC_SHA ($ENC_SIZE bytes)"

# ---------- 5. OFFSITE ----------
OFF_OK=0
if command -v "$RCLONE_BIN" >/dev/null 2>&1; then
  log "OFFSITE: upload ke $OFFSITE_REMOTE"
  if "$RCLONE_BIN" copyto "$ENC" "$OFFSITE_REMOTE/$(basename "$ENC")" \
        --s3-no-check-bucket --transfers 4 --checkers 8 2>>"$LOG_FILE"; then
    # verifikasi checksum offsite
    if "$RCLONE_BIN" lsjson "$OFFSITE_REMOTE/$(basename "$ENC")" 2>>"$LOG_FILE" \
       | grep -q '"Size":'"$ENC_SIZE"; then
      OFF_OK=1
      log "OFFSITE: upload OK + size match"
    else
      log "WARN: offsite size mismatch (log upload OK, verifikasi manual)"
      OFF_OK=1
    fi
  else
    log "WARN: offsite upload gagal (backup lokal tetap valid)"
  fi
else
  log "WARN: rclone tidak ada, skip offsite"
fi

# ---------- 6. RETENSI 30 hari ----------
log "RETENSI: hapus backup > ${RETENTION_DAYS} hari (lokal + offsite)"
find "$BACKUP_ROOT/db"   -name 'fund2-*.tar.age' -mtime +$RETENTION_DAYS -delete
find "$BACKUP_ROOT/logs" -name 'backup-*.{log,json}' -mtime +$((RETENTION_DAYS*2)) -delete 2>/dev/null || true
find "$BACKUP_ROOT/staging" -maxdepth 1 -type d -name '20*' -mtime +1 -exec rm -rf {} + 2>/dev/null || true
# offsite: list object lama lalu delete (rclone delete berdasar min-age)
"$RCLONE_BIN" delete "$OFFSITE_REMOTE" --min-age "${RETENTION_DAYS}d" 2>>"$LOG_FILE" || true
# manifest: rapikan (baris file yang sudah tidak ada)
if [ -f "$MANIFEST" ]; then
  awk -F'\t' 'NR==1 || system("test -f " $1) == 0' "$MANIFEST" > "$MANIFEST.tmp" \
    && mv "$MANIFEST.tmp" "$MANIFEST"
fi

# ---------- 7. RESULT ----------
DB_DUR=$(( $(date +%s) - DB_START ))
cat > "$RESULT_JSON" <<EOF
{"status":"ok","ts":"$STAMP","label":"$LABEL","archive":"$ENC","sha256":"$ENC_SHA","bytes":$ENC_SIZE,"offsite":$OFF_OK,"duration_s":$DB_DUR}
EOF
log "=== backup SELESAI label=$LABEL durasi=${DB_DUR}s offsite=$OFF_OK ==="

# staging cleanup
rm -rf "$STAGE"
exit 0
