#!/bin/bash
# Audit gap: equity, journal, correlation, signals (signature includes query)
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 'cd /opt/lumine/backend
KEY="web-frontend"
SEC=$(docker exec backend-redis-1 redis-cli HGET "lumine:api_key:$KEY" secret)
curl_h() {
  local FULL=$1
  local T=$(date +%s)
  local E=$(printf "" | sha256sum | cut -d" " -f1)
  local PL=$(printf "GET\n%s\n%s\n%s" "$FULL" "$T" "$E")
  local SIG=$(printf "%s" "$PL" | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}")
  curl -s -H "Host: lumine.biz.id" -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $T" -H "X-Lumine-Signature: $SIG" \
    "http://127.0.0.1$FULL"
}
echo "=== equity (limit=3) ==="
curl_h "/api/v1/portfolio/default/equity?limit=3" | head -c 400
echo; echo "=== journal (limit=3) ==="
curl_h "/api/v1/journal?limit=3" | head -c 400
echo; echo "=== signals XAUUSD ==="
curl_h "/api/v1/market/signals/XAUUSD?limit=3" | head -c 400
echo; echo "=== correlation ==="
curl_h "/api/v1/market/correlation?symbols=XAUUSD,EURUSD&window=30" | head -c 400
echo; echo "=== DB table counts ==="
docker exec backend-postgres-1 psql -U lumine -d lumine -t -c "SELECT tablename FROM pg_tables WHERE schemaname='"'"'public'"'"' AND tablename LIKE '"'"'%equity%'"'"' OR tablename LIKE '"'"'%journal%'"'"' OR tablename LIKE '"'"'%signal%'"'"' OR tablename LIKE '"'"'%correlat%'"'"';" 2>&1 | head -10
'
