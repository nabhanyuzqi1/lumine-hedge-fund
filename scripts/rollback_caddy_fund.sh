#!/usr/bin/env bash
# P5 cutover rollback: arahkan fund.lumine.biz.id kembali ke v1 (atau balik ke v2).
# Mekanisme sama dengan deploy-edge.sh: validate -> graceful reload (zero-downtime).
#
# Pemakaian:
#   rollback_caddy_fund.sh v1   # fund block -> v1 native (frontend 3106, API 3107)
#   rollback_caddy_fund.sh v2   # fund block -> v2 (fund2-edge-proxy 3110) = kondisi cutover
set -euo pipefail

HOST_DIR="/home/tekka/caddy-edge"
CONTAINER="caddy-edge"
URL="https://fund.lumine.biz.id/"
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

VARIANT="${1:?pemakaian: rollback_caddy_fund.sh v1|v2}"
case "$VARIANT" in
  v1) SRC="$HOST_DIR/Caddyfile.v1-rollback" ;;
  v2) SRC="$HOST_DIR/Caddyfile.v2-cutover" ;;
  *) echo "variant harus v1 atau v2"; exit 1 ;;
esac
[ -f "$SRC" ] || { echo "snapshot tidak ada: $SRC"; exit 1; }

T0=$(date +%s)
echo "== 1/3 pasang varian $VARIANT =="
cp "$SRC" "$HOST_DIR/Caddyfile"

echo "== 2/3 validate =="
docker run --rm \
  -v "$HOST_DIR/Caddyfile":/etc/caddy/Caddyfile:ro \
  -v tekka_caddy-config:/config \
  -v tekka_caddy-data:/data \
  caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

HOST_MD5=$(md5sum "$HOST_DIR/Caddyfile" | cut -d' ' -f1)
if docker exec "$CONTAINER" md5sum /etc/caddy/Caddyfile 2>/dev/null | grep -q "$HOST_MD5"; then
  echo "== 2/3 graceful reload (bind mount current) =="
  docker exec "$CONTAINER" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
else
  echo "== 2/3 graceful reload (stale inode: inject copy) =="
  docker cp "$HOST_DIR/Caddyfile" "$CONTAINER":/tmp/Caddyfile.deploy
  docker exec "$CONTAINER" caddy reload --config /tmp/Caddyfile.deploy --adapter caddyfile
  echo "WARNING: inode swap; recreate container caddy-edge di maintenance window berikutnya."
fi

echo "== 3/3 post-deploy check =="
sleep 1
CODE=$(curl -s -o /dev/null -w '%{http_code}' -A "$UA" "$URL")
T1=$(date +%s)
echo "fund.lumine.biz.id -> HTTP $CODE (varian $VARIANT), elapsed $((T1-T0))s"
echo "selesai"
