#!/bin/bash
# Test E2E: SSE subscribe ic-decisions + analyst-outputs, trigger LLM cycle
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 'cd /opt/lumine/backend
KEY="web-frontend"
SEC=$(docker exec backend-redis-1 redis-cli HGET "lumine:api_key:$KEY" secret)
TS=$(date +%s)
PATHREQ="/api/v1/streams/ic-decisions"
EMPTY=$(printf "" | sha256sum | cut -d" " -f1)
PAYLOAD=$(printf "GET\n%s\n%s\n%s" "$PATHREQ" "$TS" "$EMPTY")
SIG=$(printf "%s" "$PAYLOAD" | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}")

# 1. Subscribe SSE ic-decisions (25 detik)
( curl -s -N -m 25 -H "Host: lumine.biz.id" \
    -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $TS" -H "X-Lumine-Signature: $SIG" \
    "http://127.0.0.1$PATHREQ" > /tmp/sse_ic.txt 2>&1 ) &
SSE_PID=$!
sleep 2

# 2. Trigger command via API
CID=$(docker exec backend-api-1 python -c "
import asyncio
from lumine.rpc.queue import enqueue_command
async def main():
    cid = await enqueue_command(\"run_decision_cycle\", {\"symbol\": \"XAUUSD\"})
    print(cid)
asyncio.run(main())
")
echo "cid: $CID"

wait $SSE_PID 2>/dev/null
echo "=== SSE ic-decisions OUTPUT ==="
grep -v "^: heartbeat" /tmp/sse_ic.txt | head -c 1500
echo
echo "=== RESULT ==="
docker exec backend-redis-1 redis-cli GET "rpc:results:$CID" | python3 -m json.tool 2>/dev/null | head -25
'
