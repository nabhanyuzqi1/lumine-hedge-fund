"""Test introspeksi agent LLM (FUND2-LLM-B2, t_aaf7498f; rencana t_2a751a6c).

Cakupan:
- engine: evidence trade (order_events/orders/positions/candle -> MFE/MAE),
  evidence daily, narasi wajib menyebut data (bukan opini kosong), simpan
  idempoten ke llm_introspections (append-only + UNIQUE scope+ref_key).
- endpoint: GET config (tanpa secret), GET decisions, GET introspection,
  POST introspect (admin+2FA).
- trigger loop: posisi llm CLOSED -> introspeksi per trade, pergantian
  tanggal UTC -> harian, gagal introspeksi tidak menghentikan siklus
  (audit system_events), wiring terpasang di agent_loop.

Fixture conftest existing dipakai apa adanya (conftest.py TIDAK diubah).
llm_introspections tidak di-TRUNCATE oleh _clean_db -> fixture lokal
membersihkannya (bypass trigger append-only dengan session_replication_role,
pola test migrasi l012).
"""
from __future__ import annotations

import asyncio
import inspect
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app import db, llm_context_extras, llm_introspection
from app.llm_agent_loop import PROMPT_VERSION, SYSTEM_PROMPT, agent_loop
from app.llm_introspection import (
    IntrospectionInvalid,
    collect_daily_evidence,
    collect_trade_evidence,
    reset_tick_state,
    run_daily_introspection,
    run_introspection_tick,
    run_trade_introspection,
    validate_narasi,
)
from app.main import app

TRADE_ORDER_DAY = datetime(2026, 11, 24, 1, 0, tzinfo=timezone.utc)
TRADE_CLOSE_DAY = datetime(2026, 11, 24, 1, 10, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _mock_calendar(monkeypatch):
    """Kalender fakery ok/tanpa event (pola test_llm_agent_v2) supaya
    GET /llm-agent/config tidak memukul feed kalender live."""

    async def _fake_calendar(now_utc=None):
        return {"status": "ok", "source": "test", "as_of": None, "events": []}

    monkeypatch.setattr(llm_context_extras, "fetch_calendar", _fake_calendar)


@pytest.fixture(autouse=True)
async def _clean_introspections(_clean_db):
    """llm_introspections di luar daftar TRUNCATE conftest (file B1 dilarang
    disentuh): bersihkan per test + reset state trigger in-memory."""
    reset_tick_state()
    yield
    reset_tick_state()
    async with db.pool().connection() as conn:
        await conn.execute("SET session_replication_role = replica")
        await conn.execute("TRUNCATE llm_introspections RESTART IDENTITY")
        await conn.execute("RESET session_replication_role")


def _fake_llm_post(narasi: str, calls: list | None = None, status_code: int = 200):
    """Pengganti httpx.AsyncClient.post: /chat/completions -> JSON {narasi}."""

    async def fake_post(self, url, **kwargs):
        if calls is not None:
            calls.append({"url": url, "json": kwargs.get("json")})
        if url.endswith("/chat/completions"):
            content = json.dumps({"narasi": narasi})
            return httpx.Response(
                status_code,
                json={"model": "test-model",
                      "choices": [{"message": {"content": content}}],
                      "usage": {"prompt_tokens": 10, "completion_tokens": 5}},
                request=httpx.Request("POST", url),
            )
        return httpx.Response(200, json={"ok": True},
                              request=httpx.Request("POST", url))

    return fake_post


def _set_llm_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test")
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-a-real-credential")
    monkeypatch.setenv("LLM_MODEL", "test-model")


async def _insert_closed_llm_position(*, ticket=770301, side="BUY", volume=0.10,
                                      entry=2000.0, close_price=1995.0, profit=-50.0,
                                      sl=1999.0, tp=2010.0,
                                      open_time=TRADE_ORDER_DAY,
                                      close_time=TRADE_CLOSE_DAY,
                                      with_decision=True, with_candles=True):
    """Order strategy 'llm' FILLED + posisi CLOSED + keputusan entry agent."""
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "INSERT INTO orders (symbol, side, volume, sl, tp, strategy, status, created_at) "
            "VALUES ('XAUUSD', %s, %s, %s, %s, 'llm', 'FILLED', %s) RETURNING id",
            (side, volume, sl, tp, open_time))).fetchone()
        order_id = str(row["id"])
        await conn.execute(
            "INSERT INTO positions (ticket, order_id, symbol, side, volume, "
            "open_price, open_time, close_price, close_time, sl, tp, profit, status) "
            "VALUES (%s, %s, 'XAUUSD', %s, %s, %s, %s, %s, %s, %s, %s, %s, 'CLOSED')",
            (ticket, row["id"], side, volume, entry, open_time, close_price,
             close_time, sl, tp, profit))
        if with_decision:
            decision = {
                "kind": "order", "symbol": "XAUUSD",
                "reasoning": "breakout M5 di atas resistance 1998 dengan volume naik",
                "confidence": 0.72, "model": "test-model",
                "prompt_version": "2.0.0", "cycle_id": "cycle-abc-123",
                "prompt_tokens": 1200, "completion_tokens": 300, "latency_ms": 900,
            }
            await conn.execute(
                "INSERT INTO order_events (order_id, from_status, to_status, "
                "payload, decision) VALUES (%s, NULL, 'AGENT_ORDER', %s, %s)",
                (order_id, json.dumps({"source": "llm_agent"}),
                 json.dumps(decision)))
        await conn.execute(
            "INSERT INTO order_events (order_id, from_status, to_status, payload) "
            "VALUES (%s, 'FILLED', 'FILLED_THEN_CLOSED', %s)",
            (order_id, json.dumps({"source": "test", "reason": "sl"})))
        if with_candles and open_time and close_time:
            for i, (high, low) in enumerate([(2002.0, 1998.0), (2001.0, 1994.0)]):
                ts = open_time + timedelta(minutes=5 * i)
                await conn.execute(
                    "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close) "
                    "VALUES ('XAUUSD', 'M5', %s, %s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (ts, (high + low) / 2, high, low, (high + low) / 2))
        return order_id


async def _insert_decision_event(symbol: str, reasoning: str, to_status="AGENT_HOLD"):
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "INSERT INTO order_events (order_id, from_status, to_status, payload, decision) "
            "VALUES (NULL, NULL, %s, %s, %s) RETURNING id",
            (to_status, json.dumps({"source": "llm_agent"}),
             json.dumps({"kind": "hold", "symbol": symbol, "reasoning": reasoning,
                         "confidence": 0.5, "model": "test-model",
                         "prompt_version": "2.0.0", "cycle_id": "cycle-xyz-001"})))
        ).fetchone()
    return row["id"]


async def _rows(sql: str, params: tuple = ()) -> list[dict]:
    async with db.pool().connection() as conn:
        cur = await conn.execute(sql, params)
        return await cur.fetchall()


# ------------------------------------------------------- narasi (unit murni)
TRADE_EVIDENCE_MIN = {"scope": "trade", "symbol": "XAUUSD", "entry_price": 2000.0,
                      "close_price": 1995.0, "sl": 1999.0, "tp": 2010.0,
                      "profit": -50.0, "volume": 0.1, "mfe": 2.0, "mae": 6.0,
                      "decision": {"confidence": 0.72}}


def test_validate_narasi_trade_accepts_data_specific():
    validate_narasi(
        "XAUUSD entry 2000.0 ditutup 1995.0 dengan loss -50.0 setelah SL 1999.0 "
        "kena; MFE 2.0 lawan MAE 6.0, confidence 0.72 terlalu agresif.",
        TRADE_EVIDENCE_MIN)


def test_validate_narasi_trade_rejects_empty_opinion():
    with pytest.raises(IntrospectionInvalid, match="angka evidence"):
        validate_narasi(
            "XAUUSD bergerak tidak menentu sehingga keputusan ini sulit dinilai "
            "dan sebaiknya lebih berhati-hati pada siklus berikutnya.",
            TRADE_EVIDENCE_MIN)
    with pytest.raises(IntrospectionInvalid, match="symbol"):
        validate_narasi("Harga 2000.0 berbalik dan loss -50.0 terasa menyakitkan.",
                        TRADE_EVIDENCE_MIN)


def test_validate_narasi_daily_requires_summary_numbers():
    evidence = {"scope": "daily",
                "summary": {"positions_closed": 2, "win_count": 1, "loss_count": 1,
                            "total_profit": 12.5, "orders_created": 3,
                            "orders_failed": 1},
                "positions_closed": [{"profit": -50.0, "entry_price": 2000.0,
                                      "close_price": 1995.0}]}
    validate_narasi(
        "Hari ini 2 posisi close dengan total profit 12.5 (1 win, 1 loss) "
        "dari 3 order dan 1 order gagal.", evidence)
    with pytest.raises(IntrospectionInvalid, match="angka ringkasan"):
        validate_narasi(
            "Hari berjalan cukup tenang tanpa banyak kejadian berarti bagi "
            "portofolio maupun strategi.", evidence)


# ------------------------------------------------------------------ evidence
async def test_collect_trade_evidence_from_data(client):
    order_id = await _insert_closed_llm_position()
    async with db.pool().connection() as conn:
        ev = await collect_trade_evidence(conn, order_id=order_id)
    assert ev["symbol"] == "XAUUSD" and ev["outcome"] == "loss"
    assert ev["entry_price"] == 2000.0 and ev["close_price"] == 1995.0
    assert ev["profit"] == -50.0 and ev["volume"] == 0.1
    assert ev["sl"] == 1999.0 and ev["tp"] == 2010.0
    assert ev["holding_minutes"] == 10.0
    assert ev["decision"]["reasoning"].startswith("breakout M5")
    assert ev["decision"]["confidence"] == 0.72
    assert ev["decision"]["prompt_tokens"] == 1200
    # MFE/MAE dari candle M5 selama holding: high 2002, low 1994, entry 2000.
    assert ev["mfe"] == 2.0 and ev["mae"] == 6.0
    assert ev["candles_m5_count"] == 2
    assert ev["closed_at_sl"] is True and ev["closed_at_tp"] is False
    assert [e["to_status"] for e in ev["event_timeline"]] == [
        "AGENT_ORDER", "FILLED_THEN_CLOSED"]
    # ticket juga bisa jadi ref_key.
    async with db.pool().connection() as conn:
        ev2 = await collect_trade_evidence(conn, ticket=770301)
    assert ev2["entry_price"] == 2000.0


async def test_collect_trade_evidence_without_candles_marks_unavailable(client):
    order_id = await _insert_closed_llm_position(
        ticket=770302, with_candles=False)
    async with db.pool().connection() as conn:
        ev = await collect_trade_evidence(conn, order_id=order_id)
    assert ev["candles"]["status"] == "unavailable"
    assert "mfe" not in ev and "mae" not in ev


async def test_collect_trade_evidence_rejects_open_position(client):
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "INSERT INTO orders (symbol, side, volume, strategy, status) "
            "VALUES ('XAUUSD', 'BUY', 0.01, 'llm', 'FILLED') RETURNING id")).fetchone()
        await conn.execute(
            "INSERT INTO positions (ticket, order_id, symbol, side, volume, "
            "open_price, profit, status) VALUES (770303, %s, 'XAUUSD', 'BUY', 0.01, "
            "2000, 0, 'OPEN')", (row["id"],))
        with pytest.raises(IntrospectionInvalid, match="masih OPEN"):
            await collect_trade_evidence(conn, order_id=str(row["id"]))


async def test_collect_daily_evidence_summary(client):
    await _insert_closed_llm_position(ticket=770311, profit=-50.0)
    await _insert_closed_llm_position(ticket=770312, profit=25.0,
                                      close_price=2005.0, sl=1990.0)
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO orders (symbol, side, volume, strategy, status, fail_reason, "
            "created_at) VALUES ('XAUUSD', 'SELL', 0.01, 'llm', 'FAILED', "
            "'risk gate: max spread', %s)", (TRADE_ORDER_DAY,))
    async with db.pool().connection() as conn:
        ev = await collect_daily_evidence(conn, TRADE_ORDER_DAY.date())
    summary = ev["summary"]
    assert summary["positions_closed"] == 2
    assert summary["win_count"] == 1 and summary["loss_count"] == 1
    assert summary["total_profit"] == -25.0
    assert summary["orders_created"] == 3  # 2 order entry + 1 gagal
    assert summary["orders_failed"] == 1
    assert len(ev["positions_closed"]) == 2
    assert ev["date"] == "2026-11-24"


# ---------------------------------------------------------------- engine run
async def test_run_trade_introspection_saves_evidence_and_narasi(client, monkeypatch):
    _set_llm_env(monkeypatch)
    calls: list = []
    narasi = ("XAUUSD entry 2000.0 ditutup 1995.0 dengan loss -50.0 setelah SL "
              "1999.0 kena; MFE 2.0 lawan MAE 6.0 menunjukkan entry terlalu dini.")
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_llm_post(narasi, calls))
    order_id = await _insert_closed_llm_position()

    out = await run_trade_introspection(order_id)
    assert out["inserted"] is True and out["prompt_version"] == PROMPT_VERSION
    assert out["narasi"] == narasi
    # Prompt LLM memuat evidence data spesifik, bukan asumsi.
    prompt_text = json.dumps(calls[0]["json"]["messages"], ensure_ascii=False)
    assert "breakout M5" in prompt_text and "1999.0" in prompt_text
    rows = await _rows(
        "SELECT scope, ref_key, evidence, narasi, model, prompt_version "
        "FROM llm_introspections WHERE ref_key = %s", (order_id,))
    assert len(rows) == 1
    row = rows[0]
    assert row["scope"] == "trade" and row["narasi"] == narasi
    assert row["evidence"]["profit"] == -50.0
    assert row["evidence"]["mfe"] == 2.0 and row["evidence"]["mae"] == 6.0
    assert row["model"] == "test-model"

    # Re-run: idempoten (UNIQUE scope+ref_key, tabel append-only -> DO NOTHING).
    out2 = await run_trade_introspection(order_id)
    assert out2["inserted"] is False
    rows2 = await _rows(
        "SELECT id, narasi FROM llm_introspections WHERE ref_key = %s", (order_id,))
    assert len(rows2) == 1 and rows2[0]["narasi"] == narasi


async def test_run_trade_introspection_rejects_narasi_without_data(client, monkeypatch):
    _set_llm_env(monkeypatch)
    monkeypatch.setattr(
        httpx.AsyncClient, "post",
        _fake_llm_post("Pasar bergerak tidak menentu sehingga keputusan ini sulit "
                       "dinilai; sebaiknya lebih berhati-hati pada siklus berikut."))
    order_id = await _insert_closed_llm_position(ticket=770321)
    with pytest.raises(IntrospectionInvalid, match="tidak menyebut"):
        await run_trade_introspection(order_id)
    rows = await _rows("SELECT id FROM llm_introspections")
    assert rows == []


async def test_run_daily_introspection_saves_and_is_idempotent(client, monkeypatch):
    _set_llm_env(monkeypatch)
    narasi = ("Total profit hari ini -25.0 dari 2 posisi close (1 win, 1 loss); "
              "3 order dibuat dan 1 order gagal di risk gate.")
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_llm_post(narasi))
    await _insert_closed_llm_position(ticket=770331, profit=-50.0)
    await _insert_closed_llm_position(ticket=770332, profit=25.0,
                                      close_price=2005.0, sl=1990.0)
    out = await run_daily_introspection("2026-11-24")
    assert out["inserted"] is True and out["ref_key"] == "2026-11-24"
    rows = await _rows(
        "SELECT scope, ref_key, evidence, narasi FROM llm_introspections "
        "WHERE scope = 'daily'")
    assert len(rows) == 1
    assert rows[0]["evidence"]["summary"]["positions_closed"] == 2
    assert rows[0]["evidence"]["summary"]["total_profit"] == -25.0
    out2 = await run_daily_introspection("2026-11-24")
    assert out2["inserted"] is False
    assert len(await _rows("SELECT id FROM llm_introspections")) == 1


# ------------------------------------------------------------------ endpoint
def _patch_llm_http(monkeypatch, narasi: str, calls: list | None = None):
    """Patch httpx.AsyncClient.post HANYA utk /chat/completions.

    Endpoint test memakai client ASGI (httpx) juga, jadi permintaan non-LLM
    diteruskan ke implementasi asli.
    """
    original = httpx.AsyncClient.post
    fake_chat = _fake_llm_post(narasi, calls)

    async def fake_post(self, url, **kwargs):
        if str(url).endswith("/chat/completions"):
            return await fake_chat(self, url, **kwargs)
        return await original(self, url, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


async def test_get_config_readonly_without_secret(monkeypatch, client):
    _set_llm_env(monkeypatch)
    resp = await client.get("/llm-agent/config")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Field READ yang diminta butir owner (2).
    assert body["system_prompt"] == SYSTEM_PROMPT
    assert body["prompt_version"] == PROMPT_VERSION
    assert body["model"] == "test-model"
    assert body["interval_s"] == 300.0
    assert isinstance(body["llm_risk"], dict) and body["llm_risk"]
    assert body["calendar"]["blackout_active"] is False
    assert body["calendar"]["data"]["status"] == "ok"
    assert body["pause"]["active"] is False
    assert body["kill_switch"]["active"] is False
    assert body["halted"] is False
    # TANPA secret: API key / base URL / token apa pun tidak pernah bocor.
    raw = resp.text
    assert "test-key-not-a-real-credential" not in raw
    assert "http://llm.test" not in raw
    assert "LLM_API_KEY" not in raw
    assert "bridge_token" not in raw
    assert "password" not in raw.lower()


async def test_get_config_requires_login():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as anon:
        resp = await anon.get("/llm-agent/config")
    assert resp.status_code in (401, 403)


async def test_get_decisions_latest_first_and_symbol_filter(client):
    id1 = await _insert_decision_event("XAUUSD", "alasan hold satu")
    id2 = await _insert_decision_event("BTCUSD", "alasan hold dua")
    body = (await client.get("/llm-agent/decisions")).json()
    assert body["count"] == 2
    assert [d["id"] for d in body["decisions"]] == [id2, id1]
    assert body["decisions"][0]["decision"]["symbol"] == "BTCUSD"
    assert body["decisions"][0]["decision"]["reasoning"] == "alasan hold dua"
    assert body["decisions"][0]["to_status"] == "AGENT_HOLD"
    # Filter symbol case-insensitive; limit dihormati.
    assert (await client.get(
        "/llm-agent/decisions?symbol=btcusd")).json()["count"] == 1
    assert (await client.get("/llm-agent/decisions?limit=1")).json()["count"] == 1


async def test_get_introspection_scope_and_date(client):
    today = datetime.now(timezone.utc).date().isoformat()
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO llm_introspections (scope, ref_key, evidence, narasi) "
            "VALUES ('daily', '2026-11-23', %s, %s)",
            (json.dumps({"summary": {"total_profit": 1.5}}), "narasi harian"))
        await conn.execute(
            "INSERT INTO llm_introspections (scope, ref_key, narasi) "
            "VALUES ('trade', 'ref-trade-1', 'narasi trade satu')")
    daily = (await client.get(
        "/llm-agent/introspection?scope=daily&date=2026-11-23")).json()
    assert daily["count"] == 1
    assert daily["introspections"][0]["ref_key"] == "2026-11-23"
    assert daily["introspections"][0]["evidence"]["summary"]["total_profit"] == 1.5
    trade = (await client.get(
        f"/llm-agent/introspection?scope=trade&date={today}")).json()
    assert trade["count"] == 1
    assert trade["introspections"][0]["ref_key"] == "ref-trade-1"
    all_trade = (await client.get("/llm-agent/introspection?scope=trade")).json()
    assert all_trade["count"] == 1
    # Validasi query.
    assert (await client.get(
        "/llm-agent/introspection?scope=bogus")).status_code == 422
    assert (await client.get(
        "/llm-agent/introspection?scope=daily&date=23-11-2026")).status_code == 422


async def test_post_introspect_requires_admin_2fa(client):
    resp = await client.post("/llm-agent/introspect",
                             json={"scope": "trade", "ref_key": "x"})
    assert resp.status_code == 403


async def test_post_introspect_trade_endpoint(client_2fa, monkeypatch):
    _set_llm_env(monkeypatch)
    narasi = ("XAUUSD entry 2000.0 ditutup 1995.0 dengan loss -50.0 setelah SL "
              "1999.0 kena; MFE 2.0 lawan MAE 6.0, entry terlalu dini.")
    _patch_llm_http(monkeypatch, narasi)
    order_id = await _insert_closed_llm_position(ticket=770341)
    resp = await client_2fa.post(
        "/llm-agent/introspect", json={"scope": "trade", "ref_key": order_id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True and body["inserted"] is True
    assert body["ref_key"] == order_id and body["narasi"] == narasi
    listed = (await client_2fa.get(
        "/llm-agent/introspection?scope=trade")).json()
    assert [x["ref_key"] for x in listed["introspections"]] == [order_id]
    # ref_key tidak dikenal -> 404; posisi OPEN / tanggal salah -> 422.
    missing = await client_2fa.post(
        "/llm-agent/introspect",
        json={"scope": "trade", "ref_key": "00000000-0000-0000-0000-000000000000"})
    assert missing.status_code == 404
    assert (await client_2fa.post(
        "/llm-agent/introspect", json={"scope": "trade"})).status_code == 422
    assert (await client_2fa.post(
        "/llm-agent/introspect",
        json={"scope": "trade", "ref_key": "bukan-uuid"})).status_code == 422
    assert (await client_2fa.post(
        "/llm-agent/introspect", json={"scope": "bogus"})).status_code == 422


async def test_post_introspect_daily_endpoint(client_2fa, monkeypatch):
    _set_llm_env(monkeypatch)
    narasi = ("Total profit 2026-11-24 adalah -50.0 dari 1 posisi close "
              "(0 win, 1 loss) dengan 1 order dibuat.")
    _patch_llm_http(monkeypatch, narasi)
    await _insert_closed_llm_position(ticket=770345, profit=-50.0)
    resp = await client_2fa.post(
        "/llm-agent/introspect", json={"scope": "daily", "ref_key": "2026-11-24"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["inserted"] is True
    listed = (await client_2fa.get(
        "/llm-agent/introspection?scope=daily&date=2026-11-24")).json()
    assert listed["count"] == 1 and listed["introspections"][0]["narasi"] == narasi
    bad = await client_2fa.post(
        "/llm-agent/introspect", json={"scope": "daily", "ref_key": "24-11-2026"})
    assert bad.status_code == 422


async def test_post_introspect_without_llm_env_503(client_2fa, monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    resp = await client_2fa.post(
        "/llm-agent/introspect", json={"scope": "daily", "ref_key": "2026-11-22"})
    assert resp.status_code == 503
    assert "LLM_BASE_URL" in resp.text


# ------------------------------------------------- trigger loop (butir 5/6)
TRADE_NARASI = ("XAUUSD entry 2000.0 ditutup 1995.0 dengan loss -50.0 setelah "
                "SL 1999.0 kena; MFE 2.0 lawan MAE 6.0.")
DAILY_NARASI = ("Rekap 2026-11-24: 1 posisi close dengan total profit -50.0 "
                "(0 win, 1 loss), 1 order dibuat.")


async def test_tick_closed_trade_then_utc_rollover_daily(client, monkeypatch):
    """Posisi llm CLOSED -> introspeksi trade; pergantian tanggal UTC ->
    introspeksi harian untuk hari yang baru selesai (sekali per rollover)."""
    _set_llm_env(monkeypatch)

    async def fake_chat(evidence, http=None):
        narasi = TRADE_NARASI if evidence.get("scope") == "trade" else DAILY_NARASI
        return {"narasi": narasi, "model": "test-model", "prompt_tokens": 1,
                "completion_tokens": 1, "latency_ms": 1}

    monkeypatch.setattr(llm_introspection, "_call_introspection_llm", fake_chat)
    order_id = await _insert_closed_llm_position(ticket=770351)
    reset_tick_state()

    t0 = datetime(2026, 11, 24, 23, 55, tzinfo=timezone.utc)
    r1 = await run_introspection_tick(now=t0)
    assert r1["trade_scheduled"] == 1 and r1["daily_scheduled"] == 0
    await asyncio.gather(*r1["tasks"])
    rows = await _rows(
        "SELECT ref_key, narasi FROM llm_introspections WHERE scope = 'trade'")
    assert [r["ref_key"] for r in rows] == [order_id]
    assert rows[0]["narasi"] == TRADE_NARASI

    # Tick berikutnya (masih hari yang sama): sudah ada narasi -> tidak
    # dijadwalkan ulang.
    r2 = await run_introspection_tick(now=t0 + timedelta(minutes=2))
    assert r2["trade_scheduled"] == 0 and r2["daily_scheduled"] == 0

    # Lewat tengah malam UTC -> rekap harian 2026-11-24.
    r3 = await run_introspection_tick(
        now=datetime(2026, 11, 25, 0, 5, tzinfo=timezone.utc))
    assert r3["daily_scheduled"] == 1
    await asyncio.gather(*r3["tasks"])
    daily = await _rows(
        "SELECT ref_key, narasi FROM llm_introspections WHERE scope = 'daily'")
    assert [d["ref_key"] for d in daily] == ["2026-11-24"]
    assert daily[0]["narasi"] == DAILY_NARASI
    # Rollover hanya sekali.
    r4 = await run_introspection_tick(
        now=datetime(2026, 11, 25, 0, 10, tzinfo=timezone.utc))
    assert r4["daily_scheduled"] == 0 and r4["trade_scheduled"] == 0


async def test_tick_failure_does_not_raise_and_audits_error(client, monkeypatch):
    """Gagal introspeksi TIDAK boleh menghentikan siklus: task menelan
    exception, audit ke system_events, dan narasi tidak disimpan."""
    reset_tick_state()
    await _insert_closed_llm_position(ticket=770352)

    async def boom(*args, **kwargs):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(llm_introspection, "run_trade_introspection", boom)
    r = await run_introspection_tick(
        now=datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc))
    assert r["trade_scheduled"] == 1
    await asyncio.gather(*r["tasks"])  # tidak raise
    events = await _rows(
        "SELECT event_type, severity, source, details FROM system_events "
        "WHERE event_type = 'LLM_INTROSPECTION_ERROR'")
    assert len(events) == 1
    assert events[0]["severity"] == "ERROR"
    assert events[0]["source"] == "llm_agent_loop"
    assert events[0]["details"]["scope"] == "trade"
    assert "LLM down" in events[0]["details"]["error"]
    assert await _rows("SELECT id FROM llm_introspections") == []


async def test_tick_never_raises_when_scan_fails(client, monkeypatch):
    reset_tick_state()

    async def boom_scan():
        raise RuntimeError("db down")

    monkeypatch.setattr(llm_introspection, "fetchall_conn_scan", boom_scan)
    r = await run_introspection_tick(
        now=datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc))
    assert r.get("errors") == 1


def test_agent_loop_has_introspection_wiring():
    """DoD: trigger terpasang di llm_agent_loop (satu-satunya edit file itu)."""
    src = inspect.getsource(agent_loop)
    assert "from .llm_introspection import run_introspection_tick" in src
    assert 'run_introspection_tick(source="llm_agent_loop")' in src
    assert "TIDAK pernah menghentikan siklus trading" in src



