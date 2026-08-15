#!/bin/bash
# Debug: kenapa rpc_worker_task None — cek seed/tick worker juga
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
docker exec backend-api-1 python -c "
import asyncio
from lumine.api.app import _app_state

async def main():
    for k in [\"seed_worker\", \"tick_worker\", \"rpc_worker_task\", \"mt5_bridge\", \"sse_publisher\"]:
        v = _app_state.get(k)
        print(f\"{k}: {v}\")

asyncio.run(main())
" 2>&1 | tail -8
'
