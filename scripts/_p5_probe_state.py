#!/usr/bin/env python3
"""Probe state DB fund2 untuk QA P5 (read-only)."""
import os
import re

env = {}
for line in open("/home/tekka/fund2/api/.env"):
    m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
    if m:
        env[m.group(1)] = m.group(2)

import psycopg

conn = psycopg.connect(env["DATABASE_URL"], autocommit=True)
cur = conn.cursor()

queries = [
    ("v7 orders", "SELECT count(*) FROM orders WHERE label LIKE 'p5-latency-gate-v7%'"),
    ("v7 by status", "SELECT status, count(*) FROM orders WHERE label LIKE 'p5-latency-gate-v7%' GROUP BY status"),
    ("v7 latency events",
     "SELECT count(*) FROM order_events oe JOIN orders o ON o.id=oe.order_id "
     "WHERE o.label LIKE 'p5-latency-gate-v7%' AND oe.payload ? 'latency'"),
    ("positions", "SELECT status, count(*) FROM positions GROUP BY status"),
    ("pending", "SELECT count(*) FROM orders WHERE status IN "
                "('RECEIVED','RISK_PASS','SENT','STUCK','PARTIALLY_FILLED')"),
    ("ks tables", "SELECT table_name FROM information_schema.tables "
                  "WHERE table_schema='public' AND table_name ~* 'kill|state|halt'"),
    ("ks recent", "SELECT id, reason, source, active, activated_at FROM kill_switch_events "
                  "ORDER BY id DESC LIMIT 3"),
]
for name, q in queries:
    try:
        cur.execute(q)
        print(f"{name}: {cur.fetchall()}")
    except Exception as e:
        conn.rollback()
        print(f"{name}: ERR {e}")
