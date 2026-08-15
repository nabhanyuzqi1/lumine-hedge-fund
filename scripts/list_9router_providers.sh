#!/bin/bash
# Cari daftar provider valid 9router (AI_PROVIDERS) + suggested-models
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
docker exec 9router node -e "
const BASE = \"http://localhost:20128\";
async function main() {
  const login = await fetch(BASE + \"/api/auth/login\", {
    method: \"POST\", headers: {\"Content-Type\": \"application/json\"},
    body: JSON.stringify({password: \"123456\"})
  });
  const cookies = (login.headers.getSetCookie ? login.headers.getSetCookie() : []).map(c => c.split(\";\")[0]).join(\"; \");
  // suggested models
  const r = await fetch(BASE + \"/api/providers/suggested-models\", {headers: {cookie: cookies}});
  const j = await r.json();
  const data = j.providers || j.data || j;
  if (Array.isArray(data)) {
    console.log(\"providers:\", data.length);
    for (const p of data.slice(0, 50)) console.log(\" \", p.id || p.name || p);
  } else {
    console.log(JSON.stringify(j).slice(0, 2000));
  }
}
main().catch(e => console.log(\"ERR\", e.message));
"
'
