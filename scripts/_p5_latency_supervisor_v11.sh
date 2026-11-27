#!/bin/bash
# Supervisor driver latensi P5 v11: restart driver bila mati mendadak.
# Berhenti bila status file menunjukkan phase=done, atau 15 percobaan.
cd /home/tekka/fund2
PY=./api/.venv/bin/python
LOG=scripts/p5_latency_v11.log
STATUS=scripts/p5_latency_v11_status.json
attempts=0
while [ "$attempts" -lt 15 ]; do
  "$PY" scripts/_p5_latency_driver_v11.py >> "$LOG" 2>&1
  rc=$?
  echo "[supervisor] driver exit rc=$rc pada $(date +%H:%M:%S), attempt $((attempts+1))" >> "$LOG"
  if grep -q '"phase": "done"' "$STATUS" 2>/dev/null; then
    echo "[supervisor] selesai: phase=done" >> "$LOG"
    break
  fi
  if grep -q '"phase": "preflight_failed"' "$STATUS" 2>/dev/null; then
    echo "[supervisor] preflight gagal; hentikan supervisor" >> "$LOG"
    break
  fi
  attempts=$((attempts+1))
  sleep 15
done
echo "[supervisor] keluar pada $(date +%H:%M:%S) setelah $attempts restart" >> "$LOG"
