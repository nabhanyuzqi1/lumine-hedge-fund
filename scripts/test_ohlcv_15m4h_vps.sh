#!/bin/bash
# Test 15m/4h dengan delay >60s antar request (hindari replay cache)
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
cd /opt/lumine/backend
KEY="web-frontend"
SEC=$(docker exec backend-redis-1 redis-cli HGET "lumine:api_key:$KEY" secret)
for TF in 15m 4h; do
  TS=$(date +%s)
  PATHREQ="/api/v1/market/ohlcv/XAUUSD?timeframe=$TF&limit=3"
  EMPTY=$(printf "" | sha256sum | cut -d" " -f1)
  PAYLOAD=$(printf "GET\n%s\n%s\n%s" "$PATHREQ" "$TS" "$EMPTY")
  SIG=$(printf "%s" "$PAYLOAD" | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}")
  echo "--- $TF ---"
  curl -s -H "Host: lumine.biz.id" \
    -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $TS" -H "X-Lumine-Signature: $SIG" \
    "http://127.0.0.1$PATHREQ" | head -c 350
  echo
  sleep 65
done
'
