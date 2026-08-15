#!/bin/bash
# Debug: apakah run_worker task start di api container asli
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
echo "=== container start ==="
docker inspect backend-api-1 --format "{{.State.StartedAt}}"
echo "=== cek task via _app_state ==="
docker exec backend-api-1 python -c "
import asyncio
from lumine.api.app import _app_state

async def main():
    t = _app_state.get(\"rpc_worker_task\")
    print(\"rpc_worker_task:\", t)
    if t:
        print(\"done:\", t.done())
        if t.done():
            try: t.result()
            except Exception as e: print(\"EXC:\", type(e).__name__, str(e)[:300])

asyncio.run(main())
" 2>&1 | tail -6
'
