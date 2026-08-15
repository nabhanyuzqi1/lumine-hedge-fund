#!/bin/bash
# Setup provider 9router: login dari dalam container → POST /api/providers
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
  const lj = await login.json();
  console.log(\"login:\", JSON.stringify(lj).slice(0, 150));
  // Cookie dari set-cookie
  const cookies = login.headers.getSetCookie ? login.headers.getSetCookie() : [];
  console.log(\"cookies:\", cookies.map(c => c.split(\";\")[0]).join(\" \"));

  // 2. GET providers (cek koneksi existing)
  const pv = await fetch(BASE + \"/api/providers\", {headers: {cookie: cookies.join(\"; \")}});
  console.log(\"providers:\", (await pv.text()).slice(0, 300));
}
main().catch(e => console.log(\"ERR\", e.message));
"
'
