#!/bin/bash
# Trigger RPC run_decision_cycle → SSE ic-decisions → committee feed
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
echo "=== trigger via redis XADD ==="
docker exec backend-redis-1 redis-cli XADD rpc:commands "*" command_id "test-cycle-$(date +%s)" cmd run_decision_cycle symbol XAUUSD decision hold
echo "=== tunggu 3s ==="
sleep 3
echo "=== cek SSE event di redis pubsub? ==="
docker exec backend-redis-1 redis-cli PUBSUB CHANNELS "*" | head -10
echo "=== cek log api ==="
docker logs backend-api-1 --since 30s 2>&1 | grep -iE "decision|rpc|error" | tail -8
'
