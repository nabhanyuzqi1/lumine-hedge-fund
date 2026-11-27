"""Calendar blackout gate LLM (t_d9e6b2a3).

Deterministic blackout order baru LLM di sekitar event high-impact USD:
unit test logika window + fail-closed, integration test POST /orders
(FAILED + order_events berisi alasan), dan penetral order manual.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app import db, llm_context_extras, llm_risk, market
from app.main import app

EVENT_T = datetime(2026, 11, 24, 13, 30, tzinfo=timezone.utc)


def _event(t=EVENT_T, impact="High", country="USD", title="Nonfarm Payrolls"):
    ev = {"title": title, "time_utc": t.isoformat(), "impact": impact}
    if country is not None:
        ev["country"] = country
    return ev


def _block(events, status="ok"):
    return {
        "status": status,
        "source": "faireconomy.media",
        "as_of": EVENT_T.isoformat(),
        "events": events,
    }


@pytest.fixture
def cal(monkeypatch):
    """Ganti fetch_calendar dgn fixture (API tidak hit network di test)."""
    holder = {"block": _block([])}

    async def _fake(now_utc=None):
        return holder["block"]

    monkeypatch.setattr(llm_context_extras, "fetch_calendar", _fake)
    return holder


async def _reason(cal_holder=None, settings=None, symbol="XAUUSD", now=None):
    if now is None:
        now = EVENT_T + timedelta(minutes=31)
    return await llm_risk.calendar_blackout_reason(
        settings or {}, symbol, now)


# ---------------------------------------------------------------- unit: window
async def test_window_boundary(cal):
    """Event 13:30, before/after 30: 12:59 lolos (31 mnt, di luar window),
    13:00 & 14:00 tepat di boundary -> tolak, 14:01 lolos."""
    cal["block"] = _block([_event()])
    assert await _reason(now=EVENT_T - timedelta(minutes=31)) is None
    r = await _reason(now=EVENT_T - timedelta(minutes=30))
    assert r and r.startswith("calendar_blackout: USD High")
    r = await _reason(now=EVENT_T + timedelta(minutes=30))
    assert r and r.startswith("calendar_blackout: USD High")
    assert await _reason(now=EVENT_T + timedelta(minutes=31)) is None


async def test_reason_format(cal):
    cal["block"] = _block([_event(title="Nonfarm Payrolls")])
    r = await _reason(now=EVENT_T)
    assert r == (
        "calendar_blackout: USD High 'Nonfarm Payrolls' at "
        "2026-11-24T13:30:00+00:00 within -30/30min window"
    )


async def test_title_truncated_to_60(cal):
    cal["block"] = _block([_event(title="x" * 100)])
    r = await _reason(now=EVENT_T)
    assert "'x' * 60" or True
    assert f"'{'x' * 60}'" in r
    assert "x" * 61 not in r


# ---------------------------------------------------------------- unit: filter
async def test_non_usd_high_not_blackout(cal):
    """Event non-USD High tidak memicu blackout (currencies=[USD])."""
    cal["block"] = _block([_event(country="EUR")])
    assert await _reason(now=EVENT_T) is None


async def test_low_impact_usd_not_blackout(cal):
    """Event USD impact Low tidak memicu blackout."""
    cal["block"] = _block([_event(impact="Low")])
    assert await _reason(now=EVENT_T) is None


async def test_custom_currencies_settings(cal):
    """Merge parsial: currencies diganti EUR -> event USD tidak memicu."""
    cal["block"] = _block([_event(country="USD")])
    settings = {"llm_risk": {"calendar_blackout": {"currencies": ["EUR"]}}}
    assert await _reason(settings=settings, now=EVENT_T) is None
    cal["block"] = _block([_event(country="EUR")])
    r = await _reason(settings=settings, now=EVENT_T)
    assert r and "calendar_blackout: EUR" in r


# ---------------------------------------------------------------- unit: fail-closed
async def test_fail_closed_when_unavailable(cal):
    """Kalender unavailable (>24 jam tanpa data) -> tolak fail-closed."""
    cal["block"] = _block([], status="unavailable")
    r = await _reason(now=EVENT_T)
    assert r and r.startswith("calendar_unavailable")


async def test_stale_still_gates(cal):
    """Data stale (<24 jam) tetap dipakai evaluasi window."""
    cal["block"] = _block([_event()], status="stale")
    r = await _reason(now=EVENT_T)
    assert r and r.startswith("calendar_blackout:")


async def test_enabled_false_passes(cal):
    """Owner mematikan gate via settings -> lolos walau event di window."""
    cal["block"] = _block([_event()])
    settings = {"llm_risk": {"calendar_blackout": {"enabled": False}}}
    assert await _reason(settings=settings, now=EVENT_T) is None


async def test_default_enabled(cal):
    assert llm_risk.get_calendar_blackout({}) == {
        "enabled": True, "before_min": 30, "after_min": 30,
        "currencies": ["USD"],
    }


# ---------------------------------------------------------------- integration
def _order(**kw):
    body = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.01,
            "sl": 1998.0, "tp": 2005.0, "strategy": "llm"}
    body.update(kw)
    return body


async def _tick():
    market.update_tick("XAUUSD", bid=1999.85, ask=2000.15)


@pytest.fixture
async def agent_client(user):
    """Client ter-login sebagai role 'agent' (service fund2-llm-agent)."""
    from app import auth

    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'agent')",
            ("svc-llm-agent", auth.hash_password("agentpass")),
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/auth/login",
                            json={"username": "svc-llm-agent", "password": "agentpass"})
        assert resp.status_code == 200, resp.text
        c.headers["x-csrf-token"] = resp.json()["csrf_token"]
        yield c


async def _failed_reasons(order_id: int) -> list[str]:
    async with db.pool().connection() as conn:
        rows = await conn.execute(
            """
            SELECT payload FROM order_events
            WHERE order_id = %s AND to_status = 'FAILED'
            ORDER BY id DESC LIMIT 1
            """,
            (order_id,),
        )
        row = await rows.fetchone()
    assert row is not None, "order_events FAILED tidak ditemukan"
    payload = row["payload"]
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)
    return payload.get("reasons", [])


async def test_order_rejected_inside_blackout(agent_client, cal):
    """POST /orders LLM di window event High USD -> 422 FAILED + event."""
    await _tick()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    cal["block"] = _block([_event(t=now, title="FOMC Statement")])
    r = await agent_client.post("/orders", json=_order())
    assert r.status_code == 422, r.text
    reasons = r.json()["rejected_reasons"]
    assert any(x.startswith("calendar_blackout:") for x in reasons), reasons
    order_id = r.json()["id"]
    ev_reasons = await _failed_reasons(order_id)
    assert any("calendar_blackout" in x for x in ev_reasons), ev_reasons


async def test_order_ok_outside_window(agent_client, cal):
    """POST /orders LLM di luar window -> 201 normal (gate lain tetap jalan)."""
    await _tick()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    cal["block"] = _block([_event(t=now + timedelta(hours=6))])
    r = await agent_client.post("/orders", json=_order())
    assert r.status_code == 201, r.text


async def test_manual_order_not_gated(client, cal):
    """Order manual (bukan role agent / strategy llm) TIDAK dinilai gate."""
    await _tick()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    cal["block"] = _block([_event(t=now)])
    r = await client.post("/orders", json=_order(strategy="manual"))
    assert r.status_code == 201, r.text
    assert not any(
        "calendar" in x for x in r.json().get("rejected_reasons", []))
