#!/bin/bash
# Login dari dalam container 9router (local) + setup provider
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
echo "=== LOGIN dari dalam container (local access) ==="
docker exec 9router node -e "
const BASE = \"http://localhost:20127\";
async function main() {
  // coba port 20127 (internal) atau 20128
  for (const port of [20127, 20128]) {
    try {
      const r = await fetch(\`http://localhost:\${port}/api/auth/login\`, {
        method: \"POST\",
        headers: {\"Content-Type\": \"application/json\"},
        body: JSON.stringify({password: \"123456\"})
      });
      const j = await r.json();
      console.log(\`port \${port}: \`, JSON.stringify(j).slice(0, 200));
      if (j.success) console.log(\"LOGIN OK\");
    } catch (e) { console.log(\`port \${port} err:\`, e.message); }
  }
}
main();
"
echo "=== Auth routes available ==="
docker exec 9router sh -c "ls /app/.next/server/app/api/auth/ 2>/dev/null"
'
