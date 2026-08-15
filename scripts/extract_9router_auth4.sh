#!/bin/bash
# Extract auth check: cari "9r-cli-auth" dan context token
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 "docker exec 9router node -e '
const s = require(\"fs\").readFileSync(\"/app/.next/server/middleware.js\",\"utf8\");
let idx = s.indexOf(\"9r-cli-auth\");
while (idx !== -1) {
  console.log(\"=== hit\", idx, \"===\");
  console.log(s.slice(Math.max(0,idx-150), idx+200));
  console.log();
  idx = s.indexOf(\"9r-cli-auth\", idx+20);
}
'"
