#!/bin/bash
# Test positions real dari DB
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 'cd /opt/lumine/backend
KEY="web-frontend"
SEC=$(docker exec backend-redis-1 redis-cli HGET "lumine:api_key:$KEY" secret)
TS=$(date +%s)
PATHREQ="/api/v1/portfolio/positions"
EMPTY=$(printf "" | sha256sum | cut -d" " -f1)
PAYLOAD=$(printf "GET\n%s\n%s\n%s" "$PATHREQ" "$TS" "$EMPTY")
SIG=$(printf "%s" "$PAYLOAD" | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}")
echo "=== positions ==="
curl -s -H "Host: lumine.biz.id" -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $TS" -H "X-Lumine-Signature: $SIG" \
  "http://127.0.0.1$PATHREQ" | python3 -m json.tool 2>/dev/null | head -30
echo "=== summary ==="
TS2=$(date +%s)
PATHREQ2="/api/v1/portfolio/summary"
EMPTY2=$(printf "" | sha256sum | cut -d" " -f1)
PAYLOAD2=$(printf "GET\n%s\n%s\n%s" "$PATHREQ2" "$TS2" "$EMPTY2")
SIG2=$(printf "%s" "$PAYLOAD2" | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}")
curl -s -H "Host: lumine.biz.id" -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $TS2" -H "X-Lumine-Signature: $SIG2" \
  "http://127.0.0.1$PATHREQ2" | python3 -m json.tool 2>/dev/null | head -20
'
