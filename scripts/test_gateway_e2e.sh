#!/bin/bash
# E2E test: RouterClient (Accept fix) → 9router → response
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
docker exec backend-api-1 python -c "
import asyncio, uuid
from lumine.shared.config import Settings
from lumine.llm_gateway.client import RouterClient
from lumine.llm_gateway.types import RouterRequest, ChatMessage

async def main():
    s = Settings()
    print(\"model:\", s.llm_default_model)
    print(\"gateway:\", s.llm_gateway_url)

    client = RouterClient(url=s.llm_gateway_url, api_key=s.llm_gateway_api_key)
    req = RouterRequest(
        model_version_id=uuid.uuid4(),
        role=\"test\",
        tier=\"cost-efficient\",
        lineage_id=uuid.uuid4(),
        prompt_ref=\"test\",
        prompt_hash=\"test\",
        idempotency_key=str(uuid.uuid4()),
        messages=[ChatMessage(role=\"user\", content=\"Balas hanya dengan kata: OK\")],
        model=\"oc/deepseek-v4-flash-free\",
    )
    try:
        resp = await client.complete_async(req)
        print(\"SUCCESS\")
        print(\"model_used:\", resp.model_used)
        print(\"content:\", repr(resp.content[:100]))
    except Exception as e:
        print(\"FAIL:\", type(e).__name__, str(e)[:300])

asyncio.run(main())
" 2>&1 | tail -8
'
