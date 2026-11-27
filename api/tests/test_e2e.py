"""End-to-end: login -> tick -> order -> worker claim -> EA poll -> result FILLED.

Mirrors the P1 done criterion: one order fully recorded in order_events.
"""
import time

from app import db, market
from app.worker import claim_one_order
from app.state_machine import fetchall


def _auth(token):
    return {"Authorization": "Bearer " + token}


async def test_full_order_lifecycle_e2e(client, bridge_token):
    # 1. EA posts a fresh tick
    r = await client.post(
        "/bridge/tick",
        json={"symbol": "XAUUSD", "bid": 1999.85, "ask": 2000.15},
        headers=_auth(bridge_token),
    )
    assert r.status_code == 200

    # 2. user places an order (SL/TP mandatory)
    csrf = (await client.get("/auth/me")).json()["csrf_token"]
    t0 = time.perf_counter()
    r = await client.post(
        "/orders",
        json={"symbol": "XAUUSD", "side": "BUY", "volume": 0.1,
              "sl": 1998.0, "tp": 2005.0},
        headers={"x-csrf-token": csrf},
    )
    api_ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["status"] == "RISK_PASS"
    assert api_ms < 300, f"order API took {api_ms:.0f}ms"

    # 3. worker claims it (RISK_PASS -> SENT)
    t0 = time.perf_counter()
    claimed = None
    while time.perf_counter() - t0 < 2:
        claimed = await claim_one_order()
        if claimed:
            break
    assert claimed is not None, "worker did not claim the order"

    # 4. EA long-poll picks it up
    r = await client.get("/bridge/poll?timeout_s=2", headers=_auth(bridge_token))
    assert r.status_code == 200
    cmd = r.json()
    assert cmd["command_id"] == order["command_id"]
    assert cmd["sl"] == 1998.0 and cmd["tp"] == 2005.0

    # 5. EA reports execution
    r = await client.post(
        "/bridge/result",
        json={"command_id": cmd["command_id"], "status": "FILLED",
              "ticket": 987654, "price": 2000.17},
        headers=_auth(bridge_token),
    )
    assert r.status_code == 200

    # 6. full event log recorded
    detail = await client.get(f"/orders/{order['id']}")
    events = detail.json()["events"]
    assert [e["to_status"] for e in events] == ["RECEIVED", "RISK_PASS", "SENT", "FILLED"]

    detail = detail.json()
    assert detail["ticket"] == 987654
    assert float(detail["price_filled"]) == 2000.17


async def test_order_rejected_by_risk_gate_still_logged(client, bridge_token):
    """Spread filter breach -> FAILED, but the full attempt is in the event log."""
    r = await client.post(
        "/bridge/tick",
        json={"symbol": "XAUUSD", "bid": 1999.00, "ask": 2000.90},  # spread 1.90 > 0.50
        headers=_auth(bridge_token),
    )
    assert r.status_code == 200
    csrf = (await client.get("/auth/me")).json()["csrf_token"]
    r = await client.post(
        "/orders",
        json={"symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "sl": 1998.0, "tp": 2005.0},
        headers={"x-csrf-token": csrf},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["status"] == "FAILED"
    assert any("spread" in rsn for rsn in body["rejected_reasons"])

    detail = await client.get(f"/orders/{body['id']}")
    assert [e["to_status"] for e in detail.json()["events"]] == ["RECEIVED", "FAILED"]
