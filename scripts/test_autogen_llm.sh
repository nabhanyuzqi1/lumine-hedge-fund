#!/bin/bash
# Test LLM call dari dalam container api (path nyata yang dipakai AutoGen)
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
docker exec backend-api-1 python -c "
import asyncio, os
from lumine.shared.config import Settings

async def main():
    s = Settings()
    print(\"model:\", s.llm_default_model)
    print(\"url:\", s.llm_gateway_url)
    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            s.llm_gateway_url + \"/v1/chat/completions\",
            headers={\"Authorization\": f\"Bearer {s.llm_gateway_api_key}\"},
            json={
                \"model\": s.llm_default_model,
                \"messages\": [{\"role\": \"user\", \"content\": \"Balas hanya dengan kata: OK\"}],
                \"max_tokens\": 50,
            },
        )
        print(\"status:\", r.status_code)
        j = r.json()
        if \"choices\" in j and j[\"choices\"]:
            msg = j[\"choices\"][0][\"message\"]
            print(\"content:\", (msg.get(\"content\") or \"\")[:100])
            print(\"reasoning:\", (msg.get(\"reasoning_content\") or \"\")[:100])
        else:
            print(\"resp:\", str(j)[:300])

asyncio.run(main())
" 2>&1 | tail -8
'
