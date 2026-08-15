#!/bin/bash
# Probes health endpoint tiap API
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
cd /opt/lumine/backend
KEY="web-frontend"
SEC=$(docker exec backend-redis-1 redis-cli HGET "lumine:api_key:$KEY" secret)
for P in \
  "/api/v1/health" \
  "/api/v1/market/quotes" \
  "/api/v1/portfolio/summary" \
  "/api/v1/portfolio/positions" \
  "/api/v1/workflows" \
  "/api/v1/journal/entries" \
  "/api/v1/market/symbols"; do
  TS=$(date +%s)
  PATHREQ="$P"
  EMPTY=$(printf "" | sha256sum | cut -d" " -f1)
  PAYLOAD=$(printf "GET\n%s\n%s\n%s" "$PATHREQ" "$TS" "$EMPTY")
  SIG=$(printf "%s" "$PAYLOAD" | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}")
  CODE=$(curl -s -o /tmp/r.json -w "%{http_code}" -H "Host: lumine.biz.id" \
    -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $TS" -H "X-Lumine-Signature: $SIG" \
    "http://127.0.0.1$PATHREQ")
  MSG=$(head -c 120 /tmp/r.json | tr -d "\n")
  echo "$CODE $P → $MSG"
  sleep 2
done
'
