"""POST /orders validation + risk-gate integration."""


async def _csrf(client) -> str:
    return (await client.get("/auth/me")).json()["csrf_token"]


def _body(**overrides):
    body = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "sl": 1998.0, "tp": 2005.0}
    body.update(overrides)
    return body


async def test_order_success_risk_pass(client, tick_2000):
    resp = await client.post("/orders", json=_body(), headers={"x-csrf-token": await _csrf(client)})
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["status"] == "RISK_PASS"
    assert order["command_id"]  # exposed for bridge tests


async def test_order_missing_sl_rejected_422(client, tick_2000):
    body = _body()
    del body["sl"]
    resp = await client.post("/orders", json=body, headers={"x-csrf-token": await _csrf(client)})
    assert resp.status_code == 422


async def test_order_missing_tp_rejected_422(client, tick_2000):
    body = _body()
    del body["tp"]
    resp = await client.post("/orders", json=body, headers={"x-csrf-token": await _csrf(client)})
    assert resp.status_code == 422


async def test_order_bad_side(client, tick_2000):
    resp = await client.post("/orders", json=_body(side="UP"),
                             headers={"x-csrf-token": await _csrf(client)})
    assert resp.status_code == 422


async def test_order_bad_symbol(client, tick_2000):
    resp = await client.post("/orders", json=_body(symbol="EURUSD"),
                             headers={"x-csrf-token": await _csrf(client)})
    assert resp.status_code == 422


async def test_order_negative_volume(client, tick_2000):
    resp = await client.post("/orders", json=_body(volume=-0.1),
                             headers={"x-csrf-token": await _csrf(client)})
    assert resp.status_code == 422


async def test_order_risk_reject_recorded_as_failed(client):
    """No tick posted -> spread filter fails -> order FAILED but fully recorded."""
    resp = await client.post("/orders", json=_body(),
                             headers={"x-csrf-token": await _csrf(client)})
    assert resp.status_code == 422
    order = resp.json()
    assert order["status"] == "FAILED"
    assert order["rejected_reasons"]

    detail = await client.get(f"/orders/{order['id']}")
    events = detail.json()["events"]
    assert [e["to_status"] for e in events] == ["RECEIVED", "FAILED"]
    assert events[1]["payload"]["risk"] == "rejected"


async def test_order_volume_over_max_rejected(client, tick_2000):
    resp = await client.post("/orders", json=_body(volume=5.0),
                             headers={"x-csrf-token": await _csrf(client)})
    assert resp.status_code == 422
    assert resp.json()["status"] == "FAILED"


async def test_orders_list_and_detail(client, tick_2000):
    await client.post("/orders", json=_body(), headers={"x-csrf-token": await _csrf(client)})
    lst = await client.get("/orders")
    assert lst.status_code == 200
    assert len(lst.json()) == 1
    # Event log per order ikut di list (PRD P1b hari 9-10, Riwayat UI).
    listed = lst.json()[0]
    assert [e["to_status"] for e in listed["events"]] == ["RECEIVED", "RISK_PASS"]
    assert listed["events"][0]["payload"]["source"] == "api"
    detail = await client.get(f"/orders/{listed['id']}")
    assert detail.status_code == 200
    assert [e["to_status"] for e in detail.json()["events"]] == ["RECEIVED", "RISK_PASS"]


async def test_404_unknown_order(client):
    resp = await client.get("/orders/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# ------------------------------------------------------ multipair (F1)

def _btc_body(**overrides):
    body = {"symbol": "BTCUSD", "side": "BUY", "volume": 0.01,
            "sl": 58700.0, "tp": 60100.0}  # jarak 400 dari ask 59100
    body.update(overrides)
    return body


async def _allow_btc():
    from app import db
    await db.set_setting("allowed_symbols", ["XAUUSD", "BTCUSD"])


async def test_btc_order_risk_pass_with_own_spec(client, tick_2000):
    """BTCUSD: SL jarak 400 & spread 20 lolos dengan spec per-simbolnya."""
    from app import market
    await _allow_btc()
    market.update_tick("BTCUSD", bid=59080.0, ask=59100.0)  # spread 20 < 100
    resp = await client.post("/orders", json=_btc_body())
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "RISK_PASS"


async def test_btc_sl_too_close_rejected_per_symbol(client, tick_2000):
    from app import market
    await _allow_btc()
    market.update_tick("BTCUSD", bid=59080.0, ask=59100.0)
    # jarak 5.00 < sl_min 10.00 BTCUSD
    resp = await client.post("/orders", json=_btc_body(sl=59095.0, tp=60100.0))
    assert resp.status_code == 422
    order = resp.json()
    assert order["status"] == "FAILED"
    assert any("below min" in r for r in order["rejected_reasons"])


async def test_btc_spread_over_per_symbol_max_rejected(client, tick_2000):
    from app import market
    await _allow_btc()
    market.update_tick("BTCUSD", bid=59000.0, ask=59120.0)  # spread 120 > 100
    resp = await client.post("/orders", json=_btc_body())
    assert resp.status_code == 422
    assert any("spread" in r for r in resp.json()["rejected_reasons"])


async def test_xau_volume_above_locked_a3_rejected(client, tick_2000):
    """XAUUSD 0.50 lot kini ditolak A3 (0.10) meski di bawah legacy max 1.0."""
    resp = await client.post("/orders", json=_body(volume=0.5))
    assert resp.status_code == 422
    assert any("exceeds max 0.1" in r for r in resp.json()["rejected_reasons"])


async def test_aggregate_exposure_cross_symbol_rejected(client, tick_2000):
    """A4: posisi XAUUSD terbuka + order BTCUSD melewati cap notional -> tolak."""
    from app import db, market
    await _allow_btc()
    market.update_tick("BTCUSD", bid=59080.0, ask=59100.0)
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO positions (ticket, symbol, side, volume, open_price, sl, status) "
            "VALUES (900001, 'XAUUSD', 'BUY', 0.20, 2000.00, 1999.00, 'OPEN')")  # 40.000 USD
    await db.set_setting("exposure_max_usd", 45000.0)
    # order BTC 0.10 lot = 5.910 -> total 45.910 > 45.000
    resp = await client.post("/orders", json=_btc_body(volume=0.10))
    assert resp.status_code == 422
    order = resp.json()
    assert order["status"] == "FAILED"
    assert any("open exposure" in r for r in order["rejected_reasons"])


async def test_aggregate_exposure_cross_symbol_within_cap_passes(client, tick_2000):
    from app import db, market
    await _allow_btc()
    market.update_tick("BTCUSD", bid=59080.0, ask=59100.0)
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO positions (ticket, symbol, side, volume, open_price, sl, status) "
            "VALUES (900002, 'XAUUSD', 'BUY', 0.20, 2000.00, 1999.00, 'OPEN')")  # 40.000 USD
    await db.set_setting("exposure_max_usd", 50000.0)
    # order BTC 0.01 lot = 591 -> total 40.591 <= 50.000
    resp = await client.post("/orders", json=_btc_body(volume=0.01))
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "RISK_PASS"
