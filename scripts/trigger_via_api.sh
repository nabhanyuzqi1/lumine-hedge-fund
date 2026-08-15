#!/bin/bash
# Trigger command via API resmi (enqueue_command) + subscribe SSE untuk verifikasi
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
docker exec backend-api-1 python -c "
import asyncio
from lumine.rpc.queue import enqueue_command, get_result
from lumine.api.sse.publisher import SSEPublisher
from lumine.data.redis_client import get_redis

async def main():
    pub = SSEPublisher(None)
    r = await get_redis()
    q = await pub.subscribe()
    cid = await enqueue_command(\"run_decision_cycle\", {\"symbol\": \"XAUUSD\", \"decision\": \"hold\"})
    print(\"enqueued:\", cid)

    # tunggu result + SSE event (worker di container api harus proses dalam 2s)
    res = None
    for _ in range(20):
        res = await get_result(cid)
        if res: break
        await asyncio.sleep(0.5)
    print(\"result:\", res)

    # cek SSE event
    evs = []
    for _ in range(10):
        try:
            ev = await asyncio.wait_for(q.get(), timeout=0.4)
            evs.append((ev.event_type, ev.channel))
        except asyncio.TimeoutError:
            break
    print(\"SSE events:\", evs)
    await pub.unsubscribe(q)

asyncio.run(main())
" 2>&1 | tail -8
'
