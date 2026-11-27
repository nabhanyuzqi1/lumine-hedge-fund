"""Telegram owner channel: parsing, otorisasi, dispatch perintah (tanpa jaringan)."""
from __future__ import annotations

import logging

import pytest

from app import config, db, kill_switch, market, telegram_bot
from app.telegram_bot import handle_command, parse_command


@pytest.fixture(autouse=True)
def owner_env(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(config, "TELEGRAM_OWNER_ID", "12345")
    yield


OWNER = 12345
STRANGER = 99999


def test_parse_command():
    assert parse_command("/stop") == ("stop", [])
    assert parse_command("/stopflatten confirm") == ("stopflatten", ["confirm"])
    assert parse_command("/pause london_breakout") == ("pause", ["london_breakout"])
    assert parse_command("/Resume ACK") == ("resume", ["ACK"])
    assert parse_command("") == ("", [])


@pytest.mark.asyncio
async def test_non_owner_ignored(client):
    reply = await handle_command("/stop", chat_id=1, sender_id=STRANGER)
    assert reply is None
    assert (await kill_switch.get_state())["active"] is False


@pytest.mark.asyncio
async def test_no_owner_config_ignored(client, monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_OWNER_ID", "")
    reply = await handle_command("/stop", chat_id=1, sender_id=OWNER)
    assert reply is None
    assert (await kill_switch.get_state())["active"] is False


@pytest.mark.asyncio
async def test_stop_command(client):
    reply = await handle_command("/stop", chat_id=1, sender_id=OWNER)
    assert "STOP_NEW_ORDERS" in reply
    state = await kill_switch.get_state()
    assert state["active"] and state["mode"] == "STOP_NEW_ORDERS"
    assert state["source"] == "telegram"
    events = await db.get_settings()  # sanity: settings masih terbaca
    assert events["kill_switch"]["active"] is True


@pytest.mark.asyncio
async def test_halt_and_resume_with_ack(client):
    reply = await handle_command("/halt", chat_id=1, sender_id=OWNER)
    assert "GLOBAL_HALT" in reply
    # resume tanpa ACK -> checklist, tetap aktif
    reply = await handle_command("/resume", chat_id=1, sender_id=OWNER)
    assert "checklist" in reply.lower()
    assert (await kill_switch.get_state())["active"] is True
    # resume dengan ACK -> lepas
    reply = await handle_command("/resume ACK", chat_id=1, sender_id=OWNER)
    assert (await kill_switch.get_state())["active"] is False


@pytest.mark.asyncio
async def test_stopflatten_two_step(client):
    market.update_tick("XAUUSD", bid=1999.85, ask=2000.15)
    reply = await handle_command("/stopflatten", chat_id=1, sender_id=OWNER)
    assert "slippage" in reply.lower()
    assert (await kill_switch.get_state())["active"] is False  # belum aktif
    reply = await handle_command("/stopflatten confirm", chat_id=1, sender_id=OWNER)
    state = await kill_switch.get_state()
    assert state["mode"] == "STOP_AND_FLATTEN"
    assert "Flatten" in reply


@pytest.mark.asyncio
async def test_pause_and_resume_strategy(client):
    reply = await handle_command("/pause london_breakout", chat_id=1, sender_id=OWNER)
    assert "london_breakout" in reply
    assert await kill_switch.get_paused_strategies() == ["london_breakout"]
    reply = await handle_command("/resume london_breakout", chat_id=1, sender_id=OWNER)
    assert (await kill_switch.get_state())["active"] is False
    assert await kill_switch.get_paused_strategies() == []


@pytest.mark.asyncio
async def test_status_and_help(client):
    reply = await handle_command("/status", chat_id=1, sender_id=OWNER)
    assert "kill-switch" in reply.lower()
    assert "DD harian" in reply
    reply = await handle_command("/help", chat_id=1, sender_id=OWNER)
    assert "/stop" in reply


@pytest.mark.asyncio
async def test_unknown_command_ignored(client):
    reply = await handle_command("/nggrngg", chat_id=1, sender_id=OWNER)
    assert reply is None


# ── Guard TELEGRAM_ALERTS_OFF (insiden 22 Nov 2026 10:40-12:22 WIB) ──


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["1", "true", "YES", " on "])
async def test_notify_owner_suppressed_by_env_guard(monkeypatch, caplog, value):
    """Guard aktif: notify_owner no-op berlogged, 0 request ke api.telegram.org."""
    monkeypatch.setenv("TELEGRAM_ALERTS_OFF", value)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(config, "TELEGRAM_OWNER_ID", "12345")
    calls: list[tuple] = []

    async def record_tg(token, method, **params):
        calls.append((method, params))
        return {"ok": True, "result": []}

    monkeypatch.setattr(telegram_bot, "tg_api", record_tg)
    with caplog.at_level(logging.INFO, logger="fund2.telegram"):
        ok = await telegram_bot.notify_owner("ORPHAN ADOPTED: uji guard")
    assert ok is False
    assert calls == []  # tidak ada request keluar, token pun tidak dipakai
    assert any("TELEGRAM_ALERTS_OFF" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_notify_owner_sends_without_guard(fake_tg):
    """Tanpa guard: alert terkirim normal via sendMessage (token palsu + rekam)."""
    ok = await telegram_bot.notify_owner("uji kirim normal")
    assert ok is True
    assert len(fake_tg) == 1
    call = fake_tg[0]
    assert call["method"] == "sendMessage"
    assert call["params"]["chat_id"] == "12345"
    assert call["params"]["text"] == "uji kirim normal"


@pytest.mark.asyncio
async def test_notify_owner_no_token_noop(monkeypatch, fake_tg):
    """Tanpa guard tapi token kosong: tetap no-op tanpa request."""
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    ok = await telegram_bot.notify_owner("uji tanpa token")
    assert ok is False
    assert fake_tg == []


# ── Integritas pengiriman (temuan gerbang P4, t_f2co_p4) ─────────────────
# Respons Telegram ok=False (mis. 400 parse Markdown, 429) artinya pesan
# TIDAK terkirim; send_message wajib raise agar notify_owner melaporkan
# gagal, bukan sukses palsu.


@pytest.mark.asyncio
async def test_send_message_raise_on_telegram_error(monkeypatch):
    async def bad_tg_api(token, method, **params):
        return {"ok": False, "error_code": 400,
                "description": "Bad Request: can't parse entities"}

    monkeypatch.setattr(telegram_bot, "tg_api", bad_tg_api)
    with pytest.raises(RuntimeError, match="sendMessage gagal"):
        await telegram_bot.send_message("tok", "12345", "teks rusak")


@pytest.mark.asyncio
async def test_notify_owner_false_when_telegram_rejects(monkeypatch):
    async def bad_tg_api(token, method, **params):
        return {"ok": False, "error_code": 400, "description": "parse error"}

    monkeypatch.delenv("TELEGRAM_ALERTS_OFF", raising=False)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(config, "TELEGRAM_OWNER_ID", "12345")
    monkeypatch.setattr(telegram_bot, "tg_api", bad_tg_api)
    ok = await telegram_bot.notify_owner("pesan ditolak Telegram")
    assert ok is False
