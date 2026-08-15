#!/bin/bash
# Test SSE panjang (45s) — analyst-outputs + ic-decisions events
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 'cd /opt/lumine/backend
KEY="web-frontend"
SEC=$(docker exec backend-redis-1 redis-cli HGET "lumine:api_key:$KEY" secret)
TS=$(date +%s)
PATHREQ="/api/v1/streams/ic-decisions"
EMPTY=$(printf "" | sha256sum | cut -d" " -f1)
PAYLOAD=$(printf "GET\n%s\n%s\n%s" "$PATHREQ" "$TS" "$EMPTY")
SIG=$(printf "%s" "$PAYLOAD" | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}")

# 1. Subscribe SSE ic-decisions (50 detik)
( curl -s -N -m 50 -H "Host: lumine.biz.id" \
    -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $TS" -H "X-Lumine-Signature: $SIG" \
    "http://127.0.0.1$PATHREQ" > /tmp/sse_ic2.txt 2>&1 ) &
SSE_PID=$!
sleep 2

# 2. Trigger command
docker exec backend-api-1 python -c "
import asyncio
from lumine.rpc.queue import enqueue_command
async def main():
    cid = await enqueue_command(\"run_decision_cycle\", {\"symbol\": \"XAUUSD\"})
    print(cid)
asyncio.run(main())
"

wait $SSE_PID 2>/dev/null
echo "=== SSE ic-decisions (events non-heartbeat) ==="
grep -v "^: heartbeat" /tmp/sse_ic2.txt | head -c 2000
'
