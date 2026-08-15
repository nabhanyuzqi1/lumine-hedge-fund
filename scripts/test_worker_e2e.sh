#!/bin/bash
# Test end-to-end: worker baru proses command + publish SSE
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
docker exec backend-api-1 python -c "
import asyncio
from lumine.rpc.worker import run_worker
from lumine.api.sse.publisher import SSEPublisher
from lumine.shared.config import Settings
from lumine.data.redis_client import get_redis

async def main():
    pub = SSEPublisher(None)
    s = Settings()
    r = await get_redis()

    # subscribe dulu
    q = await pub.subscribe()

    # trigger command
    cid = \"e2e-test-\" + str(int(asyncio.get_event_loop().time() * 1000))
    await r.xadd(\"rpc:commands\", {\"command_id\": cid, \"command\": \"run_decision_cycle\", \"payload\": \"{\\\"symbol\\\": \\\"XAUUSD\\\", \\\"decision\\\": \\\"hold\\\"}\"})
    print(\"triggered:\", cid)

    # jalankan worker 6s
    task = asyncio.create_task(run_worker(pub, s, consumer=\"e2e-w1\", block_ms=500))
    try:
        # tunggu event SSE
        got = []
        for _ in range(12):
            try:
                ev = await asyncio.wait_for(q.get(), timeout=0.5)
                got.append(ev)
                print(\"SSE EVENT:\", ev.event_type, ev.channel)
            except asyncio.TimeoutError:
                pass
        print(\"total events:\", len(got))
        # cek result di redis
        res = await r.get(\"rpc:result:\" + cid)
        print(\"result:\", res)
    finally:
        task.cancel()
        await pub.unsubscribe(q)

asyncio.run(main())
" 2>&1 | tail -12
'
