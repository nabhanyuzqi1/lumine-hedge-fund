#!/bin/bash
# Cek mt5-bridge logs + Redis stream ticks
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 'docker logs backend-mt5-bridge-1 --since 15m 2>&1 | tail -12; echo "=== REDIS XLEN ==="; R=$(docker ps --format "{{.Names}}" | grep redis | head -1); docker exec $R redis-cli XLEN mt5:ticks; echo "=== STREAM LAST ==="; docker exec $R redis-cli XRANGE mt5:ticks - + COUNT 2'
