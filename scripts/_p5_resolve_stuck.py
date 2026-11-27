#!/usr/bin/env python3
"""Resolve order STUCK yang posisi targetnya sudah CLOSED di broker.

Dipakai driver latensi P5: close order flatten kadang kehilangan result
EA (synthetic EA stop). Bila positions.ticket terbukti CLOSED (close_price
& close_time terisi), transisikan STUCK -> FILLED dengan bukti penutupan,
paralel dengan jalur /bridge/result yang idempotent.
"""
import json
import re
import sys

import psycopg

ENV_PATH = "/home/tekka/fund2/api/.env"
env = {}
for line in open(ENV_PATH):
    m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
    if m:
        env[m.group(1)] = m.group(2)


def main():
    conn = psycopg.connect(env["DATABASE_URL"], autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT id::text, action, ticket FROM orders WHERE status='STUCK'")
    stuck = cur.fetchall()
    if not stuck:
        print("tidak ada order STUCK")
        return 0
    resolved = 0
    for oid, action, ticket in stuck:
        if action != "CLOSE" or not ticket:
            print(f"SKIP {oid} action={action} ticket={ticket} (bukan close)")
            continue
        cur.execute(
            "SELECT status, close_price, close_time, profit FROM positions WHERE ticket=%s",
            (ticket,))
        row = cur.fetchone()
        if not row or row[0] != "CLOSED" or row[2] is None:
            print(f"SKIP {oid} ticket={ticket} posisi belum CLOSED ({row})")
            continue
        status, close_price, close_time, profit = row
        payload = {
            "source": "qa_recovery", "action": "CLOSE", "ticket": ticket,
            "price": float(close_price) if close_price is not None else None,
            "profit": float(profit) if profit is not None else None,
            "reason": (f"Result EA hilang; posisi {ticket} terbukti CLOSED di broker "
                       f"close_time {close_time} close_price {close_price}; resolusi "
                       "paralel dengan jalur bridge/result yang idempotent"),
        }
        with conn.transaction():
            cur.execute(
                "UPDATE orders SET status='FILLED', price_filled=%s, fail_reason=NULL, "
                "resolved_at=now() WHERE id::text=%s AND status='STUCK'",
                (float(close_price), oid))
            if cur.rowcount:
                cur.execute(
                    "INSERT INTO order_events (order_id, from_status, to_status, payload) "
                    "VALUES (%s, 'STUCK', 'FILLED', %s)", (oid, json.dumps(payload)))
        print(f"RESOLVED {oid} ticket={ticket} -> FILLED")
        resolved += 1
    print(f"selesai: {resolved} dari {len(stuck)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
