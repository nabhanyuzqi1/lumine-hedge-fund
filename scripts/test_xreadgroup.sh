#!/bin/bash
# Cek state rpc_worker_task + test xreadgroup manual
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
docker exec backend-api-1 python -c "
import asyncio
from lumine.data.redis_client import get_redis

async def main():
    r = await get_redis()
    # test xreadgroup manual dengan consumer test-2
    resp = await r.xreadgroup(\"rpc-workers\", \"debug-2\", {\"rpc:commands\": \">\"}, count=8, block=1000)
    if resp:
        for s, msgs in resp:
            for mid, fields in msgs:
                print(\"GOT:\", mid, fields)
    else:
        print(\"NO MESSAGES (stream kosong untuk >)\")
    # cek pending
    pend = await r.xpending(\"rpc:commands\", \"rpc-workers\")
    print(\"pending:\", pend)

asyncio.run(main())
" 2>&1 | tail -6
'
