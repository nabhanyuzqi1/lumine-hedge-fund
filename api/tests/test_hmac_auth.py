"""HMAC bridge auth (PRD 7, kontrak EA v5 — ea/HMAC_CONTRACT.md).

Vektor uji: string_to_sign = ts \\n nonce \\n METHOD \\n path \\n sha256_hex(body);
header X-Fund2-Timestamp/-Nonce/-Signature; toleransi ±5 dtk; nonce replay
ditolak. Bearer tetap diterima (kontrak lama: harness/test).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

from app import config

SECRET = "unit-test-hmac-secret-0123456789abcdef"


def _sign(method: str, path_with_query: str, body: bytes, secret: str = SECRET,
          ts: str | None = None, nonce: str | None = None) -> dict:
    ts = ts or str(int(time.time()))
    nonce = nonce or uuid.uuid4().hex
    sts = "\n".join([ts, nonce, method, path_with_query,
                     hashlib.sha256(body).hexdigest()]).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), sts, hashlib.sha256).hexdigest()
    return {"Content-Type": "application/json",
            "X-Fund2-Timestamp": ts, "X-Fund2-Nonce": nonce,
            "X-Fund2-Signature": sig}


async def _post_signed(client, path: str, payload: dict, **kw):
    body = json.dumps(payload).encode("utf-8")
    headers = _sign("POST", path, body, **kw)
    return await client.post(path, content=body, headers=headers)


async def _get_signed(client, path: str, **kw):
    headers = _sign("GET", path, b"", **kw)
    return await client.get(path, headers=headers)


async def test_hmac_tick_ok(client, monkeypatch):
    monkeypatch.setattr(config, "FUND2_HMAC_SECRET", SECRET)
    resp = await _post_signed(
        client, "/bridge/tick",
        {"symbol": "XAUUSD",
         "ticks": [{"ts": 1795260000000, "bid": 2000.0, "ask": 2000.3}]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ticks"] == 1


async def test_hmac_poll_ok(client, monkeypatch):
    monkeypatch.setattr(config, "FUND2_HMAC_SECRET", SECRET)
    resp = await _get_signed(client, "/bridge/poll?timeout_s=0")
    assert resp.status_code == 200  # null body = tidak ada command


async def test_hmac_missing_headers(client, monkeypatch):
    monkeypatch.setattr(config, "FUND2_HMAC_SECRET", SECRET)
    resp = await client.post("/bridge/tick", json={"symbol": "XAUUSD",
                                                   "ticks": []})
    assert resp.status_code == 401


async def test_hmac_bad_signature(client, monkeypatch):
    monkeypatch.setattr(config, "FUND2_HMAC_SECRET", SECRET)
    body = json.dumps({"symbol": "XAUUSD",
                       "ticks": [{"ts": 1795260000000, "bid": 2000.0, "ask": 2000.3}]}).encode("utf-8")
    headers = _sign("POST", "/bridge/tick", body)
    headers["X-Fund2-Signature"] = "0" * 64
    resp = await client.post("/bridge/tick", content=body, headers=headers)
    assert resp.status_code == 401


async def test_hmac_wrong_secret(client, monkeypatch):
    monkeypatch.setattr(config, "FUND2_HMAC_SECRET", SECRET)
    resp = await _post_signed(
        client, "/bridge/tick",
        {"symbol": "XAUUSD",
         "ticks": [{"ts": 1795260000000, "bid": 2000.0, "ask": 2000.3}]},
        secret="secret-lain-0123456789abcdef")
    assert resp.status_code == 401


async def test_hmac_stale_timestamp(client, monkeypatch):
    monkeypatch.setattr(config, "FUND2_HMAC_SECRET", SECRET)
    stale = str(int(time.time()) - 60)
    resp = await _post_signed(
        client, "/bridge/tick",
        {"symbol": "XAUUSD",
         "ticks": [{"ts": 1795260000000, "bid": 2000.0, "ask": 2000.3}]},
        ts=stale)
    assert resp.status_code == 401


async def test_hmac_replayed_nonce(client, monkeypatch):
    monkeypatch.setattr(config, "FUND2_HMAC_SECRET", SECRET)
    nonce = "deadbeefdeadbeef"
    payload = {"symbol": "XAUUSD",
               "ticks": [{"ts": 1795260000000, "bid": 2000.0, "ask": 2000.3}]}
    r1 = await _post_signed(client, "/bridge/tick", payload, nonce=nonce)
    r2 = await _post_signed(client, "/bridge/tick", payload, nonce=nonce)
    assert r1.status_code == 200
    assert r2.status_code == 401  # nonce dipakai sekali


async def test_hmac_heartbeat_ok(client, monkeypatch):
    monkeypatch.setattr(config, "FUND2_HMAC_SECRET", SECRET)
    resp = await _post_signed(
        client, "/bridge/heartbeat",
        {"ts": int(time.time()), "symbol": "XAUUSD", "bid": 2000.0,
         "ask": 2000.3, "spread": 0.3, "ea": "v5"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True


async def test_heartbeat_requires_auth(client):
    resp = await client.post("/bridge/heartbeat", json={"ts": 1})
    assert resp.status_code == 401


async def test_bearer_still_works(client, bridge_token):
    resp = await client.get("/bridge/poll?timeout_s=0",
                            headers={"Authorization": "Bearer " + bridge_token})
    assert resp.status_code == 200
