"""Alert Telegram (FUND2-P1b hari 11): kill-switch events, EA offline, rekap harian.

Semua test tanpa jaringan: telegram_bot.send_message di-patch untuk merekam teks.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app import alerts, config, db, kill_switch, telegram_bot

WIB = alerts.WIB


@pytest.fixture
def sent(monkeypatch):
    """Rekam semua teks yang mau dikirim (notify_owner -> send_message)."""
    calls: list[str] = []

    async def fake_send(token, chat_id, text):
        calls.append(text)

    # opt-in jalur kirim: matikan guard session (conftest) untuk test ini
    monkeypatch.delenv("TELEGRAM_ALERTS_OFF", raising=False)
    monkeypatch.setattr(telegram_bot, "send_message", fake_send)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(config, "TELEGRAM_OWNER_ID", "12345")
    return calls


async def _ks_event(action, mode=None, **kw):
    async with db.pool().connection() as conn:
        await kill_switch.record_event(conn, action, mode, **kw)


async def _set_ea_seen(age_s: float | None) -> None:
    if age_s is None:
        await db.set_setting("ea_last_seen_at", None)
    else:
        ts = datetime.now(timezone.utc) - timedelta(seconds=age_s)
        await db.set_setting("ea_last_seen_at", ts.isoformat())


# ---------------------------------------------------------------- fmt kill-switch

def _raw(text: str) -> str:
    """Hilangkan escape Markdown untuk assert isi teks."""
    return text.replace("\\_", "_").replace("\\*", "*").replace("\\`", "`").replace("\\[", "[")


def test_fmt_activate():
    row = {
        "action": "ACTIVATE", "mode": "GLOBAL_HALT", "strategy": None,
        "source": "auto:ea_offline", "actor": "auto", "reason": "EA offline 75s",
        "details": {}, "id": 1,
    }
    text = _raw(alerts.fmt_ks_event(row))
    assert "KILL-SWITCH AKTIF" in text
    assert "GLOBAL_HALT" in text
    assert "auto:ea_offline" in text
    assert "EA offline 75s" in text


def test_fmt_escalate_shows_previous():
    row = {
        "action": "ESCALATE", "mode": "GLOBAL_HALT", "strategy": None,
        "source": "auto:total_drawdown", "actor": "auto", "reason": "DD 8%",
        "details": {"previous": {"mode": "STOP_NEW_ORDERS"}}, "id": 1,
    }
    text = _raw(alerts.fmt_ks_event(row))
    assert "ESKALASI" in text
    assert "GLOBAL_HALT" in text and "STOP_NEW_ORDERS" in text


def test_fmt_release():
    row = {
        "action": "RELEASE", "mode": "PAUSE_STRATEGY", "strategy": "london_breakout",
        "source": "telegram", "actor": "tg:12345", "reason": None,
        "details": {"checklist_ack": True}, "id": 1,
    }
    text = _raw(alerts.fmt_ks_event(row))
    assert "NONAKTIF" in text
    assert "PAUSE_STRATEGY" in text
    assert "telegram" in text


def test_fmt_flatten():
    row = {
        "action": "FLATTEN_REQUEST", "mode": None, "strategy": None,
        "source": "dashboard", "actor": "admin", "reason": "flatten 2 posisi",
        "details": {"orders": [{"order_id": "a"}, {"order_id": "b"}]}, "id": 1,
    }
    text = alerts.fmt_ks_event(row)
    assert "FLATTEN" in text and "2 posisi" in text


def test_fmt_escapes_markdown_specials():
    """Underscore di reason/aktor/strategi tidak boleh memecah Markdown Telegram."""
    row = {
        "action": "ACTIVATE", "mode": "PAUSE_STRATEGY", "strategy": "a_b*c",
        "source": "dashboard", "actor": "tg:x_y", "reason": "E2E (t_f2p1b3)",
        "details": {}, "id": 1,
    }
    text = alerts.fmt_ks_event(row)
    assert "t\\_f2p1b3" in text
    assert "a\\_b\\*c" in text
    assert text.count("`") % 2 == 0  # entity backtick tetap berpasangan


# ---------------------------------------------------------------- ks_poll_once

@pytest.mark.asyncio
async def test_ks_poll_once_reads_new_events(sent):
    await _ks_event("ACTIVATE", "STOP_NEW_ORDERS", source="dashboard",
                    actor="ui:admin", reason="tes manual")
    last, texts = await alerts.ks_poll_once(0)
    assert len(texts) == 1 and "KILL-SWITCH AKTIF" in texts[0]
    assert last > 0
    # poll ulang dari last: tidak ada lagi (tanpa duplikat)
    again_last, again_texts = await alerts.ks_poll_once(last)
    assert again_texts == []
    # TRIGGERS_UPDATED tidak di-alert
    await _ks_event("TRIGGERS_UPDATED", None, source="dashboard", actor="ui:admin",
                    reason="ubah threshold")
    _, texts2 = await alerts.ks_poll_once(last)
    assert texts2 == []


# ---------------------------------------------------------------- ks_watch_loop

@pytest.mark.asyncio
async def test_ks_watch_loop_sends_new_events(monkeypatch, sent):
    monkeypatch.setattr(alerts, "KS_POLL_INTERVAL_S", 0.02)
    # event lama = baseline, tidak di-alert
    await _ks_event("ACTIVATE", "STOP_NEW_ORDERS", source="dashboard",
                    actor="ui:admin", reason="baseline")
    stop = asyncio.Event()
    task = asyncio.create_task(alerts.ks_watch_loop(stop))
    await asyncio.sleep(0.15)
    assert sent == []  # baseline tidak dikirim
    await _ks_event("ESCALATE", "GLOBAL_HALT", source="auto:ea_offline",
                    actor="auto", reason="EA offline 90s")
    await asyncio.sleep(0.3)
    stop.set()
    await task
    assert len(sent) == 1
    assert "ESKALASI" in sent[0] and "GLOBAL\\_HALT" in sent[0]


# ---------------------------------------------------------------- EA offline

@pytest.mark.asyncio
async def test_ea_check_once_no_contact_is_silent():
    await _set_ea_seen(None)
    state, text = await alerts.ea_check_once(None)
    assert state["online"] is None and text is None


@pytest.mark.asyncio
async def test_ea_offline_and_recovery_transition():
    # baseline: EA baru saja terlihat
    await _set_ea_seen(1.0)
    state, text = await alerts.ea_check_once(None)
    assert state["online"] is True and text is None  # baseline tanpa alert

    # EA hilang > threshold -> alert sekali
    await _set_ea_seen(120.0)
    state, text = await alerts.ea_check_once(state)
    assert state["online"] is False
    assert text is not None and "EA OFFLINE" in text and "120" in text

    # masih offline: tidak ada alert ulang (anti spam)
    await _set_ea_seen(130.0)
    state, text = await alerts.ea_check_once(state)
    assert text is None

    # EA kembali -> alert recovery
    await _set_ea_seen(0.5)
    state, text = await alerts.ea_check_once(state)
    assert state["online"] is True
    assert text is not None and "ONLINE kembali" in text


@pytest.mark.asyncio
async def test_ea_offline_alert_mentions_open_positions():
    await _set_ea_seen(1.0)
    state, _ = await alerts.ea_check_once(None)
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO positions (ticket, symbol, side, volume, open_price, "
            "open_time, profit, status) VALUES (9001, 'XAUUSD', 'BUY', 0.10, "
            "2000.00, now(), 1.50, 'OPEN')",
        )
    await _set_ea_seen(200.0)
    state, text = await alerts.ea_check_once(state)
    assert text is not None
    assert "Posisi terbuka: 1" in text


@pytest.mark.asyncio
async def test_ea_watch_loop_sends_transitions(monkeypatch, sent):
    monkeypatch.setattr(alerts, "EA_CHECK_INTERVAL_S", 0.02)
    await _set_ea_seen(300.0)  # baseline: offline lama, tanpa alert saat start
    stop = asyncio.Event()
    task = asyncio.create_task(alerts.ea_watch_loop(stop))
    await asyncio.sleep(0.15)
    assert sent == []
    await _set_ea_seen(0.5)  # pulih -> alert recovery
    await asyncio.sleep(0.3)
    stop.set()
    await task
    assert len(sent) == 1 and "ONLINE kembali" in sent[0]


# ---------------------------------------------------------------- rekap harian

@pytest.mark.asyncio
async def test_build_recap_content():
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO positions (ticket, symbol, side, volume, open_price, "
            "open_time, close_price, close_time, profit, status) VALUES "
            "(9101, 'XAUUSD', 'BUY', 0.10, 2000.00, now() - interval '3 hours', "
            "2005.00, now() - interval '2 hours', 5.00, 'CLOSED')",
        )
        await conn.execute(
            "INSERT INTO positions (ticket, symbol, side, volume, open_price, "
            "open_time, close_price, close_time, profit, status) VALUES "
            "(9102, 'XAUUSD', 'SELL', 0.10, 2000.00, now() - interval '2 hours', "
            "1998.00, now() - interval '1 hours', -2.00, 'CLOSED')",
        )
        await conn.execute(
            "INSERT INTO positions (ticket, symbol, side, volume, open_price, "
            "open_time, profit, status) VALUES "
            "(9103, 'XAUUSD', 'BUY', 0.05, 1999.00, now() - interval '30 minutes', "
            "1.25, 'OPEN')",
        )
        await conn.execute(
            "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close) "
            "VALUES ('XAUUSD', 'M1', now() - interval '2 minutes', 1, 1, 1, 1)",
        )
    text = await alerts.build_recap()
    assert "REKAP HARIAN" in text
    assert "+3.00 USD" in text            # 5.00 - 2.00
    assert "1 win / 1 loss" in text
    assert "Posisi terbuka: 1" in text
    assert "XAUUSD BUY 0.05" in text
    assert "EA: ONLINE" in text or "EA: belum ada kontak" in text
    assert "Kill-switch: AMAN" in text
    assert "Candle terakhir" in text
    assert "Recorder:" in text


@pytest.mark.asyncio
async def test_recap_mentions_kill_switch_when_active(sent):
    await kill_switch.activate("STOP_NEW_ORDERS", reason="tes", source="dashboard",
                               actor="ui:admin")
    text = await alerts.build_recap()
    assert "AKTIF mode" in text


def test_next_recap_time():
    now = datetime(2026, 11, 22, 6, 0, tzinfo=WIB)
    assert alerts.next_recap_time(now) == datetime(2026, 11, 22, 7, 0, tzinfo=WIB)
    now = datetime(2026, 11, 22, 8, 0, tzinfo=WIB)
    assert alerts.next_recap_time(now) == datetime(2026, 11, 23, 7, 0, tzinfo=WIB)
    now = datetime(2026, 11, 22, 7, 0, tzinfo=WIB)  # tepat jam rekap -> besok
    assert alerts.next_recap_time(now) == datetime(2026, 11, 23, 7, 0, tzinfo=WIB)


@pytest.mark.asyncio
async def test_daily_recap_loop_fires_when_due(monkeypatch, sent):
    monkeypatch.setattr(alerts, "RECAP_WAKE_MAX_S", 0.05)
    fixed = datetime.now(WIB) + timedelta(seconds=0.2)
    monkeypatch.setattr(alerts, "next_recap_time", lambda now=None: fixed)
    stop = asyncio.Event()

    async def killer():
        await asyncio.sleep(0.7)
        stop.set()

    k = asyncio.create_task(killer())
    await alerts.daily_recap_loop(stop)
    k.cancel()
    assert any("REKAP HARIAN" in t for t in sent)


# ---------------------------------------------------------------- daemon guards

@pytest.mark.asyncio
async def test_loops_noop_without_config(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_OWNER_ID", "")
    stop = asyncio.Event()
    stop.set()  # langsung stop
    await asyncio.wait_for(alerts.ks_watch_loop(stop), timeout=2)
    await asyncio.wait_for(alerts.ea_watch_loop(stop), timeout=2)
    await asyncio.wait_for(alerts.paper_watch_loop(stop), timeout=2)
    await asyncio.wait_for(alerts.daily_recap_loop(stop), timeout=2)


# ---------------------------------------------------------------- paper runner watcher

async def _set_paper_state_age(age_s: float | None) -> None:
    """paper_state runner di-update age_s lalu (None = hapus barisnya)."""
    async with db.pool().connection() as conn:
        if age_s is None:
            await conn.execute(
                "DELETE FROM paper_state WHERE key = ANY(%s)",
                (list(alerts.PAPER_STATE_KEYS),),
            )
            return
        await conn.execute(
            "INSERT INTO paper_state (key, value, updated_at) "
            "VALUES ('runner', '{}', now() - (%s * interval '1 second')) "
            "ON CONFLICT (key) DO UPDATE SET updated_at = EXCLUDED.updated_at",
            (age_s,),
        )


def _mock_paper_env(monkeypatch, *, service: str, market_open: bool) -> None:
    monkeypatch.setattr(alerts, "runner_service_status", lambda: service)
    monkeypatch.setattr(alerts, "paper_market_open", lambda: market_open)


@pytest.mark.asyncio
async def test_paper_check_once_baseline_silent(monkeypatch):
    _mock_paper_env(monkeypatch, service="active", market_open=False)
    await _set_paper_state_age(5.0)
    state, text = await alerts.paper_check_once(None)
    assert state["healthy"] is True and text is None  # baseline tanpa alert


@pytest.mark.asyncio
async def test_paper_runner_dead_service_alerts_once_then_recovers(monkeypatch):
    _mock_paper_env(monkeypatch, service="inactive", market_open=False)
    state, text = await alerts.paper_check_once(None)
    assert state["healthy"] is False and text is None  # baseline

    # masih mati: tidak ada alert ulang (anti spam)
    state, text = await alerts.paper_check_once(state)
    assert text is None

    # service hidup lagi + state terupdate -> alert recovery sekali
    _mock_paper_env(monkeypatch, service="active", market_open=False)
    await _set_paper_state_age(5.0)
    state, text = await alerts.paper_check_once(state)
    assert state["healthy"] is True
    assert text is not None and "PAPER RUNNER pulih" in text


@pytest.mark.asyncio
async def test_paper_state_stale_alerts_only_when_market_open(monkeypatch):
    _mock_paper_env(monkeypatch, service="active", market_open=False)
    await _set_paper_state_age(1200.0)  # 20 menit
    state, text = await alerts.paper_check_once(None)
    assert state["healthy"] is True and text is None  # market tutup: belum alert

    # market buka + state basi 20 menit -> alert sekali
    _mock_paper_env(monkeypatch, service="active", market_open=True)
    state, text = await alerts.paper_check_once(state)
    assert state["healthy"] is False
    assert text is not None
    raw = text.replace("\\_", "_")
    assert "PAPER RUNNER TIDAK SEHAT" in raw and "20 menit lalu" in raw

    # masih basi: tidak ada alert ulang
    state, text = await alerts.paper_check_once(state)
    assert text is None

    # state terupdate lagi -> recovery
    await _set_paper_state_age(5.0)
    state, text = await alerts.paper_check_once(state)
    assert state["healthy"] is True
    assert text is not None and "PAPER RUNNER pulih" in text


@pytest.mark.asyncio
async def test_paper_state_missing_when_market_open_alerts(monkeypatch):
    _mock_paper_env(monkeypatch, service="active", market_open=False)
    await _set_paper_state_age(None)
    state, _ = await alerts.paper_check_once(None)  # baseline healthy (market tutup)
    assert state["healthy"] is True

    # market buka tapi belum ada baris paper_state sama sekali -> alert
    _mock_paper_env(monkeypatch, service="active", market_open=True)
    state, text = await alerts.paper_check_once(state)
    assert text is not None and "belum ada" in text.replace("\\_", "_")


# ---------------------------------------------------------------- candle M5 watcher (t_86507d65)

async def _set_m5_bar(age_s: float | None) -> None:
    """Tulis bar M5 XAUUSD berusia age_s (kunci ts dalam basis candle fund2)."""
    async with db.pool().connection() as conn:
        await conn.execute("DELETE FROM candles WHERE symbol='XAUUSD' AND timeframe='M5'")
        if age_s is not None:
            now = datetime.now(timezone.utc)
            db_tz = await alerts._db_tz_offset_h(conn)
            # kebalikan stored_to_utc: stored = true - (db_tz - broker_offset)
            stored = now - timedelta(seconds=age_s) - timedelta(hours=db_tz - 7)
            await conn.execute(
                "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, volume) "
                "VALUES ('XAUUSD', 'M5', %s, 1, 1, 1, 1, 1) ON CONFLICT DO NOTHING",
                (stored,))


@pytest.mark.asyncio
async def test_candle_check_once_baseline_silent(monkeypatch):
    monkeypatch.setattr(alerts, "paper_market_open", lambda: True)
    await _set_m5_bar(60)
    state, text = await alerts.candle_check_once(None)
    assert text is None
    assert state["healthy"] is True


@pytest.mark.asyncio
async def test_candle_check_once_alerts_on_stale_feed(monkeypatch):
    monkeypatch.setattr(alerts, "paper_market_open", lambda: True)
    await _set_m5_bar(3600)  # 1 jam di belakang waktu live
    # observasi pertama sudah mati (watcher jalan saat feed lama mati) -> alert
    state, text = await alerts.candle_check_once(None)
    assert state["healthy"] is False
    assert text is not None
    assert "FEED CANDLE M5 MATI" in text
    assert "60 menit" in text
    # observasi mati berikutnya diam (anti-spam)
    state, text = await alerts.candle_check_once(state)
    assert text is None


@pytest.mark.asyncio
async def test_candle_check_once_silent_when_market_closed(monkeypatch):
    monkeypatch.setattr(alerts, "paper_market_open", lambda: False)
    await _set_m5_bar(3600)
    state, text = await alerts.candle_check_once(None)
    assert state["healthy"] is True  # market tutup: staleness tidak dinilai


@pytest.mark.asyncio
async def test_candle_check_once_recovery(monkeypatch):
    monkeypatch.setattr(alerts, "paper_market_open", lambda: True)
    await _set_m5_bar(3600)
    state, text = await alerts.candle_check_once(None)
    assert text is not None and "MATI" in text  # langsung alert saat mati
    state, text = await alerts.candle_check_once(state)
    assert text is None  # masih mati: diam
    await _set_m5_bar(60)
    state, text = await alerts.candle_check_once(state)
    assert state["healthy"] is True
    assert text is not None and "pulih" in text


@pytest.mark.asyncio
async def test_candle_age_s_converts_stored_to_true_utc(monkeypatch):
    """Usia candle diukur dengan konvensi yang sama dengan paper runner."""
    monkeypatch.setattr(alerts, "paper_market_open", lambda: True)
    await _set_m5_bar(120)
    async with db.pool().connection() as conn:
        age, true_ts = await alerts.candle_age_s(conn, datetime.now(timezone.utc))
    assert age is not None and 100 < age < 140
    assert true_ts is not None


def test_recap_beat_interval_below_watchdog_budget():
    """Heartbeat recap harus jauh di bawah ambang stale watchdog.

    Regresi 26 Nov 2026: RECAP_WAKE_MAX_S (600 s) > ALERTS_STALE_TIMEOUT_S
    (300 s) + satu beat per iterasi = watchdog keluar exit 70 tiap ~5 menit.
    """
    assert alerts.RECAP_BEAT_S <= alerts.ALERTS_STALE_TIMEOUT_S / 2
    assert alerts.RECAP_BEAT_S > 0


@pytest.mark.asyncio
async def test_recap_wait_keeps_heartbeat_fresh(monkeypatch, sent):
    """Selama menunggu jam rekap, heartbeat recap tetap diperbarui."""
    monkeypatch.setattr(alerts, "RECAP_BEAT_S", 0.05)
    monkeypatch.setattr(alerts, "RECAP_WAKE_MAX_S", 0.4)
    far = datetime.now(WIB) + timedelta(hours=5)
    monkeypatch.setattr(alerts, "next_recap_time", lambda now=None: far)
    stop = asyncio.Event()
    task = asyncio.create_task(alerts.daily_recap_loop(stop))
    seen = set()
    for _ in range(6):
        await asyncio.sleep(0.1)
        seen.add(alerts.heartbeat_snapshot().get("recap"))
    stop.set()
    task.cancel()
    seen.discard(None)
    assert len(seen) >= 2, f"heartbeat recap tidak diperbarui selama menunggu: {seen}"
