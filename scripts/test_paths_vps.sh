#!/bin/bash
# Cek path yang benar: health, quotes, journal
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
cd /opt/lumine/backend
KEY="web-frontend"
SEC=$(docker exec backend-redis-1 redis-cli HGET "lumine:api_key:$KEY" secret)
req() {
  local PATHREQ="$1"
  local TS=$(date +%s)
  local EMPTY=$(printf "" | sha256sum | cut -d" " -f1)
  local PAYLOAD=$(printf "GET\n%s\n%s\n%s" "$PATHREQ" "$TS" "$EMPTY")
  local SIG=$(printf "%s" "$PAYLOAD" | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}")
  local CODE=$(curl -s -o /tmp/r.json -w "%{http_code}" -H "Host: lumine.biz.id" \
    -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $TS" -H "X-Lumine-Signature: $SIG" \
    "http://127.0.0.1$PATHREQ")
  echo "$CODE $PATHREQ → $(head -c 200 /tmp/r.json | tr -d "\n")"
  sleep 2
}
req "/health"
req "/api/health"
req "/api/v1/market/quotes?symbols=XAUUSD"
req "/api/v1/journal"
req "/api/v1/journal/entries?limit=5"
req "/api/v1/admin/health"
'
