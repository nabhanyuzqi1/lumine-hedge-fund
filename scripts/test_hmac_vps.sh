#!/bin/bash
# Reproduce verifikasi HMAC di dalam api container (kode yang sama dengan middleware)
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
cd /opt/lumine/backend
KEY="web-frontend"
SEC=$(docker exec backend-redis-1 redis-cli HGET "lumine:api_key:$KEY" secret)
TS=$(date +%s)
PATHREQ="/api/v1/market/quote/XAUUSD"
EMPTY=$(printf "" | sha256sum | cut -d" " -f1)
PAYLOAD=$(printf "GET\n%s\n%s\n%s" "$PATHREQ" "$TS" "$EMPTY")
SIG=$(printf "%s" "$PAYLOAD" | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}")
echo "sig=$SIG"
curl -s -o /tmp/resp.json -w "HTTP %{http_code}\n" \
  -H "Host: lumine.biz.id" \
  -H "X-Lumine-Api-Key: $KEY" \
  -H "X-Lumine-Timestamp: $TS" \
  -H "X-Lumine-Signature: $SIG" \
  "http://127.0.0.1/api/v1/market/quote/XAUUSD"
head -c 300 /tmp/resp.json; echo
'
