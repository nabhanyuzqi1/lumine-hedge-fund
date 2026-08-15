#!/bin/bash
# POST provider opencode ke 9router
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
docker exec 9router node -e "
const BASE = \"http://localhost:20128\";
async function main() {
  // 1. Login
  const login = await fetch(BASE + \"/api/auth/login\", {
    method: \"POST\",
    headers: {\"Content-Type\": \"application/json\"},
    body: JSON.stringify({password: \"123456\"})
  });
  const cookies = (login.headers.getSetCookie ? login.headers.getSetCookie() : []).map(c => c.split(\";\")[0]).join(\"; \");

  // 2. POST provider opencode (free tier)
  const body = {
    provider: \"opencode\",
    name: \"OpenCode Free\",
    apiKey: \"\"
  };
  const r = await fetch(BASE + \"/api/providers\", {
    method: \"POST\",
    headers: {\"Content-Type\": \"application/json\", cookie: cookies},
    body: JSON.stringify(body)
  });
  const txt = await r.text();
  console.log(\"status:\", r.status);
  console.log(\"resp:\", txt.slice(0, 600));
}
main().catch(e => console.log(\"ERR\", e.message));
"
'
