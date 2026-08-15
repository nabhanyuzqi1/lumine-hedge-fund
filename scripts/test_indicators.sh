#!/bin/bash
# Test market indicators (timestamp seconds, unik per request)
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 'cd /opt/lumine/backend
KEY=web-frontend
SEC=$(docker exec backend-redis-1 redis-cli HGET "lumine:api_key:web-frontend" secret)
for P in "/api/v1/market/spread/XAUUSD" "/api/v1/market/session/XAUUSD" "/api/v1/market/features/XAUUSD" "/api/v1/market/correlation?symbols=XAUUSD,EURUSD&window=30" "/api/v1/portfolio/default/equity?limit=3" "/api/v1/portfolio/exposure" "/api/v1/portfolio/summary"; do
  T=$(date +%s)
  E=$(printf "" | sha256sum | cut -d" " -f1)
  SIG=$(printf "GET\n%s\n%s\n%s" "$P" "$T" "$E" | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}")
  echo "=== $P ==="
  curl -s -H "Host: lumine.biz.id" -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $T" -H "X-Lumine-Signature: $SIG" "http://127.0.0.1$P" | head -c 350
  echo
  sleep 2
done
'