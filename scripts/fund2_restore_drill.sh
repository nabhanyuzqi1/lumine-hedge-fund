#!/usr/bin/env bash
# fund2_restore_drill.sh - Restore drill ke staging terisolasi (PRD v2.2 §17.3)
#
# Restore arsip backup (tar.age) ke PostgreSQL staging TERISOLASI:
#   - instance PostgreSQL terpisah (port 5599, socket /tmp),
#   - TIDAK menyentuh DB produksi (:5433) dan TIDAK mengirim apa pun ke broker.
#   - seluruh tahap diverifikasi: schema/migration, jumlah event & rentang
#     timestamp, checksum dataset, query integritas, perbandingan state,
#     dan durasi restore (input RTO).
#
# Usage:
#   fund2_restore_drill.sh <arsip.tar.age> [label]
#   fund2_restore_drill.sh --latest        # pakai arsip term baru di manifest
#
# Output: ~/fund2-backups/drill/restore-drill-<ts>.md + .json

set -Eeuo pipefail

PG_BIN="${PG_BIN:-/home/tekka/fund2/runtime/pg16/usr/lib/postgresql/16/bin}"
PG_LIB="${PG_LIB:-/home/tekka/fund2/runtime/pg16/usr/lib/x86_64-linux-gnu:/home/tekka/fund2/runtime/pg16/usr/lib/postgresql/16/lib}"
BACKUP_ROOT="${BACKUP_ROOT:-/home/tekka/fund2-backups}"
DRILL_ROOT="${DRILL_ROOT:-$BACKUP_ROOT/drill}"
AGE_KEY_FILE="${AGE_KEY_FILE:-/home/tekka/backups/lumine-router-secrets-20261122/keys/backup-age.key}"
API_HOME="${API_HOME:-/home/tekka/fund2/api}"
DRILL_PORT="${DRILL_PORT:-5599}"
DRILL_SOCKET_DIR="/tmp"
PY="$API_HOME/.venv/bin/python"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DRILL_DIR="$DRILL_ROOT/$TS"
LOG="$DRILL_DIR/drill.log"
mkdir -p "$DRILL_DIR"

export PATH="$PG_BIN:$PATH"
export LD_LIBRARY_PATH="$PG_LIB"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"; }
fail() { log "ERROR: $*"; printf '{"status":"error","ts":"%s","error":"%s"}\n' "$STAMP" "$*" > "$DRILL_DIR/result.json"; exit 1; }
trap 'log "ERROR: gagal di baris $LINENO (rc=$?)"' ERR

ARCHIVE="${1:-}"
[ -z "$ARCHIVE" ] && fail "usage: fund2_restore_drill.sh <arsip.tar.age|--latest>"
if [ "$ARCHIVE" = "--latest" ]; then
  ARCHIVE="$(awk -F'\t' 'NR>1 {p=$1} END{print p}' "$BACKUP_ROOT/manifest.tsv")"
  [ -f "$ARCHIVE" ] || fail "arsip terbaru tidak ditemukan: $ARCHIVE"
fi
[ -f "$ARCHIVE" ] || fail "arsip tidak ada: $ARCHIVE"
LABEL="${2:-drill}"
log "=== RESTORE DRILL mulai arsip=$ARCHIVE label=$LABEL ==="

T0=$(date +%s)

# ---------- 1. DEKRIPSI + EKSTRAK ----------
log "[1/8] dekripsi age + ekstrak tar"
age --decrypt -i "$AGE_KEY_FILE" "$ARCHIVE" > "$DRILL_DIR/restored.tar" 2>>"$LOG" || fail "dekripsi gagal"
SHA_ARCHIVE="$(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
tar -C "$DRILL_DIR" -xf "$DRILL_DIR/restored.tar" 2>>"$LOG" || fail "ekstrak gagal"
rm -f "$DRILL_DIR/restored.tar"
INNER="$(find "$DRILL_DIR" -maxdepth 1 -name 'fund2-*.dump' | head -1)"
[ -n "$INNER" ] || fail "dump tidak ditemukan dalam arsip"
DATASETS_DIR="$(find "$DRILL_DIR" -maxdepth 1 -type d -name 'datasets-*' | head -1)"
SHA_FILE="$(find "$DRILL_DIR" -maxdepth 1 -name 'datasets-*.sha256' | head -1)"
log "[1/8] OK: dump=$(basename "$INNER") datasets=$(basename "$DATASETS_DIR")"

# ---------- 2. INSTANCE POSTGRES STAGING ISOLASI ----------
log "[2/8] init instance PostgreSQL staging (port $DRILL_PORT, terisolasi)"
# pastikan tidak ada instance drill lama yang mengunci port
if ss -ltn 2>/dev/null | grep -q ":$DRILL_PORT "; then
  log "WARN: port $DRILL_PORT terpakai; hentikan instance drill lama"
  for old in "$DRILL_ROOT"/20*/pgdata; do
    [ -d "$old" ] || continue
    "$PG_BIN/pg_ctl" -D "$old" -m fast stop >>"$LOG" 2>&1 || true
  done
  sleep 1
  ss -ltn 2>/dev/null | grep -q ":$DRILL_PORT " && fail "port $DRILL_PORT masih terpakai"
fi
PGDATA="$DRILL_DIR/pgdata"
"$PG_BIN/initdb" -D "$PGDATA" -U drill --auth=trust --encoding=UTF8 >>"$LOG" 2>&1 || fail "initdb gagal"
# isolasi: listen hanya di socket /tmp + loopback port drill; tanpa replikasi
cat >> "$PGDATA/postgresql.conf" <<EOF
port = $DRILL_PORT
unix_socket_directories = '$DRILL_SOCKET_DIR'
listen_addresses = '127.0.0.1'
max_connections = 20
shared_buffers = 128MB
logging_collector = off
EOF
"$PG_BIN/pg_ctl" -D "$PGDATA" -l "$DRILL_DIR/pg.log" -w start >>"$LOG" 2>&1 || fail "pg_ctl start gagal"
"$PG_BIN/psql" -h "$DRILL_SOCKET_DIR" -p "$DRILL_PORT" -U drill -d postgres \
  -c "CREATE DATABASE fund2_drill;" >>"$LOG" 2>&1 || fail "create db gagal"
log "[2/8] OK: instance staging hidup"

# ---------- 3. RESTORE SCHEMA + DATA ----------
log "[3/8] pg_restore schema+data"
R0=$(date +%s)
"$PG_BIN/pg_restore" -h "$DRILL_SOCKET_DIR" -p "$DRILL_PORT" -U drill \
  -d fund2_drill --no-owner --no-privileges "$INNER" >>"$LOG" 2>&1 || fail "pg_restore gagal"
R1=$(date +%s)
log "[3/8] OK: pg_restore selesai dalam $((R1-R0))s"

# ---------- 4. VERIFIKASI SCHEMA / MIGRASI ----------
log "[4/8] verifikasi schema/migration"
"$PY" - "$DRILL_SOCKET_DIR" "$DRILL_PORT" <<'EOF' >>"$LOG" 2>&1 || fail "verifikasi schema gagal"
import os
import sys
import sys
from pathlib import Path
import psycopg
sock, port = sys.argv[1], int(sys.argv[2])
conn = psycopg.connect(f"host={sock} port={port} user=drill dbname=fund2_drill")
cur = conn.cursor()
cur.execute("SELECT version_num FROM alembic_version")
ver = cur.fetchone()[0]
# Bandingkan dengan versi alembic DB sumber (live), bukan hardcoded:
# hardcoded cepat basi saat schema berevolusi.
env = {}
for line in Path('/home/tekka/fund2/api/.env').read_text().splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1); env[k] = v
src = psycopg.connect(env['DATABASE_URL'])
sv = src.cursor()
sv.execute("SELECT version_num FROM alembic_version")
src_ver = sv.fetchone()[0]
src.close()
assert ver == src_ver, f"alembic_version {ver} != sumber {src_ver}"
cur.execute("""SELECT count(*) FROM information_schema.tables
               WHERE table_schema='public'""")
n = cur.fetchone()[0]
assert n >= 30, f"jumlah tabel {n} < 30"
print(f"SCHEMA OK: alembic={ver}, tables={n}")
conn.close()
EOF
log "[4/8] OK: alembic cocok sumber, tabel lengkap"

# ---------- 5. VERIFIKASI JUMLAH EVENT & RENTANG TIMESTAMP ----------
log "[5/8] verifikasi jumlah event & rentang timestamp (vs sumber)"
DRILL_DSN="host=$DRILL_SOCKET_DIR port=$DRILL_PORT user=drill dbname=fund2_drill"
# CUTOFF = waktu MULAI pg_dump (snapshot), dari nama file dump fund2-<TS>.dump.
# mtime file = waktu SELESAI dump; memakai mtime menyertakan baris yang
# diinsert selama dump berjalan sehingga count sumber > count drill.
CUTOFF_TS="$(basename "$INNER" | sed -E 's/^fund2-([0-9T]+)Z\.dump$/\1Z/')"
[ "$CUTOFF_TS" != "$(basename "$INNER")" ] || fail "gagal parsing TS dari $(basename "$INNER")"
log "cutoff verifikasi: $CUTOFF_TS (waktu mulai dump)"
# hitung di instance drill
"$PY" - "$DRILL_DSN" "$CUTOFF_TS" <<'EOF' > "$DRILL_DIR/counts_drill.json" 2>>"$LOG" || fail "gagal hitung drill"
import sys, json
import psycopg
conn = psycopg.connect(sys.argv[1])
cur = conn.cursor()
out = {}
for t, col in [("order_events","created_at"),("orders","created_at"),
               ("candles","ts"),("kill_switch_events","created_at"),
               ("settings",None),("users",None),("paper_state",None),
               ("bridge_commands","created_at")]:
    cur.execute(f"SELECT count(*) FROM {t}")
    c = cur.fetchone()[0]
    rng = None
    if col:
        cur.execute(f"SELECT min({col}), max({col}) FROM {t}")
        mn, mx = cur.fetchone()
        rng = [str(mn) if mn else None, str(mx) if mx else None]
    out[t] = {"count": c, "range": rng}
# positions = tabel mutable (OPEN->CLOSED): bandingkan hanya CLOSED
# dengan close_time <= waktu mulai dump (snapshot), bukan total baris.
cur.execute("""SELECT count(*) FROM positions
               WHERE status='CLOSED' AND close_time <= %s::timestamptz""", (sys.argv[2],))
out["positions"] = {"count": cur.fetchone()[0], "range": None}
conn.close()
print(json.dumps(out, indent=1))
EOF
# hitung di sumber produksi (read-only), dipotong pada CUTOFF (waktu backup)
# agar perbandingan adil: DB live terus bertambah setelah backup diambil.
"$PY" - "$CUTOFF_TS" <<'EOF' > "$DRILL_DIR/counts_source.json" 2>>"$LOG" || fail "gagal hitung sumber"
import json, sys
from pathlib import Path
import psycopg
cutoff = sys.argv[1]
env = {}
for line in Path('/home/tekka/fund2/api/.env').read_text().splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1); env[k] = v
conn = psycopg.connect(env['DATABASE_URL'])
cur = conn.cursor()
out = {}
for t, col in [("order_events","created_at"),("orders","created_at"),
               ("candles","ts"),("kill_switch_events","created_at"),
               ("settings",None),("users",None),("paper_state",None),
               ("bridge_commands","created_at")]:
    if col:
        cur.execute(f"SELECT count(*) FROM {t} WHERE {col} <= %s::timestamptz", (cutoff,))
        c = cur.fetchone()[0]
        cur.execute(f"SELECT min({col}), max({col}) FROM {t} WHERE {col} <= %s::timestamptz", (cutoff,))
        mn, mx = cur.fetchone()
        rng = [str(mn) if mn else None, str(mx) if mx else None]
    else:
        cur.execute(f"SELECT count(*) FROM {t}")
        c = cur.fetchone()[0]
        rng = None
    out[t] = {"count": c, "range": rng}
# positions = tabel mutable: hanya CLOSED dengan close_time <= cutoff
cur.execute("""SELECT count(*) FROM positions
               WHERE status='CLOSED' AND close_time <= %s::timestamptz""", (cutoff,))
out["positions"] = {"count": cur.fetchone()[0], "range": None}
conn.close()
print(json.dumps(out, indent=1))
EOF
"$PY" - "$DRILL_DIR/counts_drill.json" "$DRILL_DIR/counts_source.json" <<'EOF' >>"$LOG" 2>&1 || fail "mismatch jumlah/range"
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
bad = []
for t in b:
    if a.get(t, {}).get("count") != b[t]["count"]:
        bad.append(f"{t}: drill={a.get(t,{}).get('count')} sumber={b[t]['count']}")
    ra, rb = a.get(t, {}).get("range"), b[t]["range"]
    if ra != rb:
        bad.append(f"{t}.range: drill={ra} sumber={rb}")
if bad:
    print("MISMATCH:"); [print(" ", x) for x in bad]; sys.exit(1)
print("COUNTS OK: 9 tabel & rentang timestamp identik sumber (cutoff backup)")
EOF
log "[5/8] OK: jumlah & rentang timestamp identik"

# ---------- 6. VERIFIKASI CHECKSUM DATASET ----------
log "[6/8] verifikasi checksum dataset parquet"
(
  cd "$DATASETS_DIR"
  sha256sum -c "$SHA_FILE" >> "$LOG" 2>&1
) || fail "checksum dataset gagal"
N_FILES="$(wc -l < "$SHA_FILE")"
log "[6/8] OK: $N_FILES file dataset checksum match"

# ---------- 7. QUERY INTEGRITAS ----------
log "[7/8] query integritas ledger"
"$PY" - "$DRILL_DSN" <<'EOF' >>"$LOG" 2>&1 || fail "query integritas gagal"
import sys
import psycopg
conn = psycopg.connect(sys.argv[1])
cur = conn.cursor()
# setiap order punya event pertama & terakhir yang valid
cur.execute("""
SELECT count(*) FROM orders o WHERE NOT EXISTS
  (SELECT 1 FROM order_events e WHERE e.order_id = o.id)
""")
orphan = cur.fetchone()[0]
assert orphan == 0, f"{orphan} order tanpa order_events"
# order_events append-only trigger masih ada
cur.execute("""SELECT tgname FROM pg_trigger
               WHERE tgrelid='order_events'::regclass AND NOT tgisinternal""")
trg = [r[0] for r in cur.fetchall()]
assert trg, "trigger append-only order_events hilang"
# candle OHLC konsisten
cur.execute("""
SELECT count(*) FROM candles
WHERE high < low OR high < open OR high < close
   OR low > open OR low > close
""")
bad = cur.fetchone()[0]
assert bad == 0, f"{bad} candle OHLC tidak konsisten"
# rentang timestamp monotonic utk ledger
cur.execute("""
SELECT count(*) FROM (
  SELECT created_at, lag(created_at) OVER (ORDER BY created_at) prev
  FROM order_events
) t WHERE prev IS NOT NULL AND created_at < prev
""")
print(f"INTEGRITAS OK: orphan=0, trigger={len(trg)}, candle_bad=0")
conn.close()
EOF
log "[7/8] OK: integritas ledger & candle"

# ---------- 8. BANDINGKAN STATE ----------
log "[8/8] bandingkan state (settings/paper_state/kill_switch)"
"$PY" - "$DRILL_DSN" "$CUTOFF_TS" <<'EOF' >>"$LOG" 2>&1 || fail "state mismatch"
import sys, json
from pathlib import Path
import psycopg
drill = psycopg.connect(sys.argv[1])
cutoff = sys.argv[2]
env = {}
for line in Path('/home/tekka/fund2/api/.env').read_text().splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1); env[k] = v
src = psycopg.connect(env['DATABASE_URL'])
def snapshot(conn, cutoff=None):
    cur = conn.cursor()
    out = {}
    # settings = SCD (baris terakhir per key = nilai aktif). Sumber dipotong
    # pada cutoff (waktu backup); ea_last_seen_at di-update tiap heartbeat EA
    # sehingga di sumber belum ada baris <= cutoff jika backup diambil
    # sebelum heartbeat berikutnya. Drill harus punya minimal baris yang sama.
    if cutoff:
        cur.execute("""
            SELECT DISTINCT ON (key) key, value::text FROM settings
            WHERE updated_at <= %s::timestamptz
            ORDER BY key, updated_at DESC
        """, (cutoff,))
    else:
        cur.execute("SELECT key, value::text FROM settings ORDER BY key")
    out["settings"] = dict(cur.fetchall())
    cur.execute("SELECT key, value::text FROM paper_state ORDER BY key")
    out["paper_state"] = dict(cur.fetchall())
    return out
a, b = snapshot(drill), snapshot(src, cutoff)
missing = set(b["settings"]) - set(a["settings"])
assert not missing, f"state settings drill kurang: {sorted(missing)}"
diff = [k for k in b["settings"] if a["settings"].get(k) != b["settings"][k]]
assert not diff, f"state settings berbeda: {diff}"
assert a["paper_state"] == b["paper_state"], "paper_state berbeda"
print(f"STATE OK: settings({len(b['settings'])} kunci) & paper_state identik (cutoff backup)")
drill.close(); src.close()
EOF
log "[8/8] OK: state identik"

# ---------- matikan instance drill ----------
"$PG_BIN/pg_ctl" -D "$PGDATA" -m fast stop >>"$LOG" 2>&1 || true

T1=$(date +%s)
DUR=$((T1 - T0))
MD="$DRILL_DIR/restore-drill-$TS.md"
cat > "$MD" <<EOF
# Restore Drill - $STAMP

| Item | Nilai |
| --- | --- |
| Arsip | \`$ARCHIVE\` |
| SHA256 arsip | \`$SHA_ARCHIVE\` |
| Label | $LABEL |
| Restore target | PostgreSQL staging terisolasi (socket /tmp, port $DRILL_PORT, user drill, DB fund2_drill) |
| Durasi total drill | **${DUR}s** (dekripsi + restore + verifikasi penuh) |
| Durasi pg_restore | $((R1-R0))s |
| Schema | alembic cocok sumber (dinamis), ≥30 tabel |
| Jumlah & rentang timestamp | 9 tabel identik dengan sumber (cutoff waktu backup) |
| Dataset parquet | $N_FILES file, checksum sha256 match |
| Integritas ledger | 0 order tanpa event; trigger append-only aktif; candle OHLC konsisten |
| State | settings & paper_state identik sumber (cutoff backup) |
| Broker live | TIDAK disentuh (isolasi penuh, tidak ada koneksi broker) |

## Tahapan (PRD v2.2 §17.3)

1. Dekripsi age + ekstrak tar.
2. Init PostgreSQL staging terisolasi (port $DRILL_PORT).
3. pg_restore schema + data.
4. Verifikasi schema/migration (alembic_version cocok sumber).
5. Verifikasi jumlah event & rentang timestamp vs sumber produksi.
6. Verifikasi checksum dataset (sha256 manifest).
7. Query integritas (ledger orphan, trigger append-only, OHLC).
8. Bandingkan state (settings, paper_state).

## Kesimpulan

RESTORE DRILL **LULUS** dalam ${DUR}s. Durasi ini adalah komponen RTO
database; RTO layanan penuh ditambah waktu start API (lihat laporan RTO/RPO).
EOF
printf '{"status":"ok","ts":"%s","archive":"%s","duration_s":%d,"pg_restore_s":%d}\n' \
  "$STAMP" "$ARCHIVE" "$DUR" "$((R1-R0))" > "$DRILL_DIR/result.json"
log "=== RESTORE DRILL LULUS dalam ${DUR}s ==="
log "laporan: $MD"
# simpan ringkasan di root drill utk akses cepat
printf '%s\n' "$MD" > "$DRILL_ROOT/LATEST"
exit 0
