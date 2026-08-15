#!/bin/bash
# Extract lebih banyak logic CLI token check
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 "docker exec 9router node -e '
const s = require(\"fs\").readFileSync(\"/app/.next/server/middleware.js\",\"utf8\");
// cari semua occurrence cli-secret dan print konteks
let idx = 0;
while ((idx = s.indexOf(\"cli-secret\", idx)) !== -1) {
  console.log(\"=== hit at\", idx, \"===\");
  console.log(s.slice(Math.max(0,idx-100), idx+250));
  console.log();
  idx += 10;
  if (idx > 600000) break;
}
'"
