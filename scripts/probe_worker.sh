#!/bin/bash
# Cek apakah rpc_worker_task masih berjalan di proses api
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
docker exec backend-api-1 python -c "
import asyncio, sys

async def main():
    # cek task via signal — langsung panggil run_worker dalam loop singkat
    from lumine.rpc.worker import run_worker
    from lumine.api.sse.publisher import SSEPublisher
    from lumine.shared.config import Settings

    pub = SSEPublisher(None)
    s = Settings()
    print(\"starting run_worker test...\")
    # jalankan 5 detik, lihat apakah ada error
    task = asyncio.create_task(run_worker(pub, s, consumer=\"probe-w1\", block_ms=500))
    try:
        await asyncio.sleep(5)
        print(\"worker still running after 5s:\", not task.done())
        if task.done():
            try:
                task.result()
            except Exception as e:
                print(\"worker EXC:\", type(e).__name__, str(e)[:300])
    finally:
        task.cancel()

asyncio.run(main())
" 2>&1 | tail -8
'
