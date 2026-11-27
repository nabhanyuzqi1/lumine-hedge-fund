#!/bin/bash
# Koreografi run latensi P5 bersih (dipicu cron one-shot 00:02 WIB, 26 Nov 2026).
# Urutan: bersihkan state (EA real masih hidup) -> stop MT5 -> rotasi token ->
# launch driver v9 (daemon) + finalizer daemon. Semua terlog.
set -u
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"
cd /home/tekka/fund2
PY=/home/tekka/fund2/api/.venv/bin/python
LOG=scripts/p5_overnight.log

{
echo "=== overnight start $(date '+%F %T %z') ==="
"$PY" scripts/_p5_clean_state.py
rc=$?
echo "clean_state rc=$rc"
if [ "$rc" -ne 0 ]; then
  echo "ABORT: state tidak bersih; MT5 tidak distop, token tidak dirotasi"
  exit 1
fi
systemctl --user stop lumine-hedge-fund-mt5.service
sleep 8
echo "mt5: $(systemctl --user is-active lumine-hedge-fund-mt5.service)"
"$PY" scripts/_p5_bridge_token.py rotate
rm -f scripts/p5_latency_v10_status.json
"$PY" scripts/_p5_launch_daemon.py
"$PY" scripts/_p5_launch_finalize_daemon.py
sleep 10
ps aux | grep -E "[_]p5_latency" | awk '{print $2, $12, $13}'
echo "=== overnight start selesai $(date '+%T') ==="
} >> "$LOG" 2>&1
