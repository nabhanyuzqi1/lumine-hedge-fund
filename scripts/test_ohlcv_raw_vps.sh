#!/bin/bash
# Raw response OHLCV untuk debug
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
cd /opt/lumine/backend
KEY="web-frontend"
SEC=$(docker exec backend-redis-1 redis-cli HGET "lumine:api_key:$KEY" secret)
for TF in 5m 15m 4h; do
  TS=$(date +%s)
  PATHREQ="/api/v1/market/ohlcv/XAUUSD?timeframe=$TF&limit=3"
  EMPTY=$(printf "" | sha256sum | cut -d" " -f1)
  PAYLOAD=$(printf "GET\n%s\n%s\n%s" "$PATHREQ" "$TS" "$EMPTY")
  SIG=$(printf "%s" "$PAYLOAD" | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}")
  echo "--- $TF RAW ---"
  curl -s -H "Host: lumine.biz.id" \
    -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $TS" -H "X-Lumine-Signature: $SIG" \
    "http://127.0.0.1$PATHREQ" | head -c 400
  echo
done
echo "=== DB bars_5m ==="
docker exec backend-postgres-1 psql -U lumine -d lumine -t -c "SELECT COUNT(*) FROM bars_5m;"
echo "=== DB bars_4h ==="
docker exec backend-postgres-1 psql -U lumine -d lumine -t -c "SELECT COUNT(*) FROM bars_4h;"
'
