#!/bin/bash
# Test simulate trade endpoint (fallback last close saat market closed)
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 'cd /opt/lumine/backend
KEY="web-frontend"
SEC=$(docker exec backend-redis-1 redis-cli HGET "lumine:api_key:$KEY" secret)
TS=$(date +%s)
PATHREQ="/api/v1/portfolio/default/simulate"
BODY="{\"symbol\":\"XAUUSD\",\"side\":\"buy\",\"volume\":1.0,\"price\":2400.00}"
BH=$(printf "%s" "$BODY" | sha256sum | cut -d" " -f1)
PAYLOAD=$(printf "POST\n%s\n%s\n%s" "$PATHREQ" "$TS" "$BH")
SIG=$(printf "%s" "$PAYLOAD" | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}")
curl -s -X POST -H "Host: lumine.biz.id" \
  -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $TS" -H "X-Lumine-Signature: $SIG" \
  -H "Content-Type: application/json" -d "$BODY" \
  "http://127.0.0.1$PATHREQ" | head -c 500
echo
'
