#!/bin/bash
# Verifikasi OHLCV multi-TF (5m/15m/4h) + quotes + positions via API
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
cd /opt/lumine/backend
KEY="web-frontend"
SEC=$(docker exec backend-redis-1 redis-cli HGET "lumine:api_key:$KEY" secret)
for TF in 5m 15m 1h 4h 1d; do
  TS=$(date +%s)
  PATHREQ="/api/v1/market/ohlcv/XAUUSD?timeframe=$TF&limit=3"
  EMPTY=$(printf "" | sha256sum | cut -d" " -f1)
  PAYLOAD=$(printf "GET\n%s\n%s\n%s" "$PATHREQ" "$TS" "$EMPTY")
  SIG=$(printf "%s" "$PAYLOAD" | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}")
  echo "--- $TF ---"
  curl -s -H "Host: lumine.biz.id" \
    -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $TS" -H "X-Lumine-Signature: $SIG" \
    "http://127.0.0.1$PATHREQ" | python3 -c "
import json,sys
d=json.load(sys.stdin)
items=d.get(\"data\",{}).get(\"items\",[])
print(f\"  bars={len(items)}\", items[0] if items else \"(kosong)\")"
done
'
