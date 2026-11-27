"""Snapshot state DB fund2 sebelum/sesudah pentest: bukti tidak ada efek samping."""
import json
import sys
from pathlib import Path

import psycopg

ENV = {}
for line in Path("/home/tekka/fund2/api/.env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        ENV[k.strip()] = v.strip()

url = ENV["DATABASE_URL"]
_, rest = url.split("://", 1)
userpass, hostpart = rest.rsplit("@", 1)
user, pwd = userpass.split(":", 1)
host, port_db = hostpart.split(":", 1)
port, dbname = port_db.rsplit("/", 1)

KEYS = ["kill_switch", "kill_switch_triggers", "paused_strategies", "halted",
        "strategy_mode_london_breakout", "strategy_mode_mean_reversion",
        "strategy_mode_btc_range_breakout", "bridge_token"]

conn = psycopg.connect(user=user, password=pwd, host=host, port=int(port),
                       dbname=dbname, connect_timeout=8)
with conn.cursor() as cur:
    cur.execute("SELECT key, value FROM settings WHERE key = ANY(%s) ORDER BY key", (KEYS,))
    settings = {k: v for k, v in cur.fetchall()}
    cur.execute("SELECT COUNT(*) FROM orders")
    n_orders = cur.fetchone()[0]
    cur.execute("SELECT to_char(created_at, 'YYYY-MM-DD HH24:MI:SS') FROM orders "
                "ORDER BY created_at DESC LIMIT 1")
    r = cur.fetchone()
    last_order = r[0] if r else None
    cur.execute("SELECT COUNT(*) FROM sessions")
    n_sessions = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM kill_switch_events")
    n_ks_events = cur.fetchone()[0]
    cur.execute("SELECT id, username FROM users ORDER BY id")
    users = [{"id": i, "username": u} for i, u in cur.fetchall()]
    cur.execute("SELECT value FROM settings WHERE key='bridge_token'")
    r = cur.fetchone()
    bridge_present = bool(r and r[0])
conn.close()

out = {
    "settings": settings,
    "bridge_token_present": bridge_present,
    "orders_count": n_orders,
    "last_order_created_at": last_order,
    "sessions_count": n_sessions,
    "kill_switch_events_count": n_ks_events,
    "users": users,
}
Path(sys.argv[1]).write_text(json.dumps(out, ensure_ascii=False, indent=1))
print("SNAPSHOT_OK")
print("users:", users)
print("orders_count:", n_orders, "last_order:", last_order)
print("sessions_count:", n_sessions, "ks_events:", n_ks_events)
print("bridge_token_present:", bridge_present)
for k in ("kill_switch", "kill_switch_triggers", "paused_strategies", "halted",
          "strategy_mode_london_breakout", "strategy_mode_mean_reversion",
          "strategy_mode_btc_range_breakout"):
    print(f"{k} = {settings.get(k)}")
