#!/bin/bash
# Test RPC handler langsung di container + cek SSE publish
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
docker exec backend-api-1 python -c "
import asyncio
from lumine.rpc.worker import _handle_run_decision_cycle
from lumine.api.sse.publisher import SSEPublisher

async def main():
    # publisher dengan redis
    pub = SSEPublisher(None)
    result = await _handle_run_decision_cycle({\"symbol\": \"XAUUSD\", \"decision\": \"hold\"}, pub)
    print(\"handler result:\", result)
    print(\"publisher redis ready:\", pub._redis is not None if hasattr(pub, \"_redis\") else \"?\")

asyncio.run(main())
" 2>&1 | tail -6
echo "=== cek SSE channel setelah publish ==="
docker exec backend-redis-1 redis-cli PUBSUB CHANNELS "*" | head -8
'
