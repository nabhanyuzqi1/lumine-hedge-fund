"""Resiliensi daemon alert: temuan F-1 (beku diam-diam) & F-2 (markdown).

Kartu t_f837fe2c, audit QA v2.2 (t_83d33b76).

Konteks insiden 25 Nov 2026 06:45 WIB: host reboot, Postgres belum siap,
`ks_watch_loop` membaca baseline DI LUAR try/except -> PoolTimeout tak
tertangkap -> `asyncio.gather` di `_amain` meneruskan exception ->
shutdown `asyncio.run()` menggantung di `_cancel_all_tasks` (task worker
psycopg_pool tidak selesai) -> proses tetap hidup, systemd `active`,
CPU 0, log berhenti: alert kritis tidak pernah terkirim.

Test di file ini menjaga tiga hal:
  1. tidak ada teks alert yang merusak parse Markdown Telegram (F-2),
  2. exception/freezer di satu watcher tidak mematikan/membekukan daemon,
  3. daemon keluar non-zero (bukan menggantung) bila DB tidak siap, dan
     watchdog keluar non-zero bila tidak ada tick alert (F-1).
"""
from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app import alerts, config, db, kill_switch, telegram_bot

API_DIR = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------- Markdown

def md_entities_balanced(text: str) -> tuple[bool, str]:
    """Validator entity Markdown legacy Telegram (parse_mode='Markdown').

    Telegram menolak pesan dengan entity tak tertutup (400 "can't parse
    entities") — persis bug F-2: underscore pada `paper_state` membuka
    italic dan tidak pernah ditutup.
    """
    i, n = 0, len(text)
    quote: str | None = None
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if quote is None:
            if ch in "*_`":
                quote = ch
        elif ch == quote:
            quote = None
        elif ch == "]" and quote == "[":
            if i + 1 >= n or text[i + 1] != "(":
                return False, f"']' tanpa '(' pada offset {i}"
            j = text.find(")", i + 2)
            if j == -1:
                return False, f"link tanpa ')' pada offset {i}"
            quote = None
            i = j + 1
            continue
        elif ch == "[" and quote == "[":
            return False, f"'[' bersarang pada offset {i}"
        i += 1
    if quote is not None:
        return False, f"entity {quote!r} tidak ditutup sampai akhir teks"
    return True, ""


def _assert_md(text: str) -> None:
    ok, why = md_entities_balanced(text)
    assert ok, f"teks alert merusak Markdown Telegram: {why}\n---\n{text}\n---"


@pytest.fixture
def tg(monkeypatch):
    """Aktifkan jalur kirim + rekam teks (tanpa jaringan)."""
    calls: list[str] = []

    async def fake_send(token, chat_id, text):
        calls.append(text)

    monkeypatch.delenv("TELEGRAM_ALERTS_OFF", raising=False)
    monkeypatch.setattr(telegram_bot, "send_message", fake_send)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(config, "TELEGRAM_OWNER_ID", "12345")
    return calls


def test_validator_menolak_pesan_bug_f2():
    """Sanity validator: teks asli insiden 05:21:17 WIB memang tidak valid."""
    bad = "✅ PAPER RUNNER pulih: service active, paper_state terupdate."
    ok, _ = md_entities_balanced(bad)
    assert not ok
    ok, _ = md_entities_balanced(alerts._md_escape(bad))
    assert ok


@pytest.mark.parametrize(
    "row",
    [
        {"action": "ACTIVATE", "mode": "GLOBAL_HALT", "strategy": None,
         "source": "auto:position_mismatch", "actor": "t_f2p1b3",
         "reason": "EA offline 75s [prioritas]", "details": {}, "id": 1},
        {"action": "ESCALATE", "mode": "STOP_AND_FLATTEN", "strategy": "runner_mean_reversion",
         "source": "kanban:t_f2mp1", "actor": "auto", "reason": None,
         "details": {"previous": {"mode": "STOP_NEW_ORDERS"}}, "id": 2},
        {"action": "RELEASE", "mode": "GLOBAL_HALT", "strategy": None,
         "source": "telegram:owner", "actor": "owner", "reason": "cek manual",
         "details": {}, "id": 3},
        {"action": "FLATTEN_REQUEST", "mode": None, "strategy": None,
         "source": "auto:sev_ea_offline", "actor": "auto", "reason": None,
         "details": {"orders": ["a", "b"]}, "id": 4},
    ],
)
def test_teks_kill_switch_valid_markdown(row):
    _assert_md(alerts.fmt_ks_event(row))


async def test_teks_paper_runner_pulih_valid_markdown(monkeypatch):
    """F-2: pesan pemulihan paper runner (alerts.py:272) harus aman Markdown."""
    monkeypatch.setattr(alerts, "runner_service_status", lambda: "active")

    async def fresh_age(conn):
        return 5.0

    monkeypatch.setattr(alerts, "paper_state_age_s", fresh_age)
    monkeypatch.setattr(alerts, "paper_market_open", lambda: True)

    state, text = await alerts.paper_check_once({"healthy": False, "unhealthy_since": 1.0})
    assert state["healthy"] is True
    assert text is not None
    _assert_md(text)


async def test_teks_paper_runner_sakit_valid_markdown(monkeypatch):
    monkeypatch.setattr(alerts, "runner_service_status", lambda: "inactive")

    async def fresh_age(conn):
        return 5.0

    monkeypatch.setattr(alerts, "paper_state_age_s", fresh_age)
    monkeypatch.setattr(alerts, "paper_market_open", lambda: True)
    _, text = await alerts.paper_check_once({"healthy": True, "unhealthy_since": None})
    assert text is not None
    _assert_md(text)


async def test_teks_candle_mati_valid_markdown(monkeypatch):
    from datetime import datetime, timezone

    async def old_age(conn, now):
        return 6000.0, datetime.now(timezone.utc)

    monkeypatch.setattr(alerts, "candle_age_s", old_age)
    monkeypatch.setattr(alerts, "paper_market_open", lambda: True)
    _, text = await alerts.candle_check_once({"healthy": True, "unhealthy_since": None})
    assert text is not None
    _assert_md(text)


async def test_teks_rekap_harian_valid_markdown():
    _assert_md(await alerts.build_recap())


# ----------------------------------------------------- F-1: watcher tahan error

async def test_ks_watch_tidak_membunuh_daemon_saat_db_gagal(monkeypatch, tg):
    """Baseline ks-watch gagal (DB belum siap) tidak boleh menembus ke _amain."""
    from psycopg_pool import PoolTimeout

    calls = {"n": 0}

    class BoomPool:
        def connection(self, *a, **kw):
            calls["n"] += 1
            raise PoolTimeout("couldn't get a connection after 10.00 sec")

    monkeypatch.setattr(db, "pool", lambda: BoomPool())

    stop = asyncio.Event()
    task = asyncio.create_task(alerts._supervise("ks", alerts.ks_watch_loop, stop))
    await asyncio.sleep(0.3)
    stop.set()
    await asyncio.wait_for(task, timeout=5)  # tidak raise, tidak menggantung
    assert calls["n"] >= 1


async def test_supervisor_restart_watcher_yang_error(caplog):
    runs = {"n": 0}

    async def flaky(stop):
        runs["n"] += 1
        if runs["n"] < 3:
            raise RuntimeError("boom")
        return

    stop = asyncio.Event()
    with caplog.at_level("INFO", logger="fund2.alerts"):
        await asyncio.wait_for(alerts._supervise("uji", flaky, stop), timeout=10)
    assert runs["n"] == 3
    assert any("restart" in r.message.lower() for r in caplog.records)


async def test_pooltimeout_tetap_pooltimeout_walau_diag_gagal(caplog):
    """Diagnosa pool tidak boleh mengubah PoolTimeout menjadi AttributeError.

    psycopg_pool >=3.2 mengembalikan dict dari get_stats(); kode lama membaca
    atribut (`st.pool_size`) sehingga jalur diagnosa melempar AttributeError
    dan PoolTimeout asli hilang — caller yang menangkap PoolTimeout tidak
    pernah jalan (ditemukan saat drill F-1, kartu t_f837fe2c).
    """
    from psycopg_pool import PoolTimeout

    class DictStatsPool:
        def get_stats(self):
            return {"pool_min": 2, "pool_max": 6, "pool_size": 0,
                    "pool_available": 0, "requests_waiting": 3,
                    "requests_num": 10, "requests_errors": 5}

        def connection(self, timeout=None):
            raise PoolTimeout("couldn't get a connection after 10.00 sec")

    with caplog.at_level("WARNING", logger="fund2.db"):
        with pytest.raises(PoolTimeout):
            async with db._connection_diag(DictStatsPool(), 1):
                pass
    assert "PoolTimeout diag" in caplog.text
    assert "pool_max" in caplog.text
    assert "AttributeError" not in caplog.text


async def test_ks_baseline_memakai_id_tersimpan():
    """Restart tidak boleh melewatkan event yang belum ter-alert."""
    await db.set_setting(alerts.KS_LAST_ID_KEY, 4242)
    assert await alerts.ks_baseline() == 4242


async def test_ks_id_terakhir_dipersist_setelah_alert():
    """Id yang sudah diproses disimpan, bukan diambil ulang dari MAX(id)."""
    from app.state_machine import fetchall

    async with db.connection() as conn:
        await kill_switch.record_event(
            conn, "RELEASE", "GLOBAL_HALT", source="telegram:owner", actor="owner",
        )
        rows = await fetchall(
            conn, "SELECT COALESCE(MAX(id), 0) AS m FROM kill_switch_events"
        )
    last = int(rows[0]["m"])
    await alerts.ks_note_sent(last)
    async with db.connection() as conn:
        stored = await fetchall(
            conn, "SELECT value FROM settings WHERE key = %s", (alerts.KS_LAST_ID_KEY,)
        )
    assert int(stored[0]["value"]) == last
    assert await alerts.ks_baseline() == last


# --------------------------------------------------------- F-1: watchdog

def test_stale_watchers_menandai_tick_yang_basi():
    now = time.monotonic()
    alerts.beat("ks", now=now - 900)
    alerts.beat("ea", now=now)
    stale = dict(alerts.stale_watchers(now=now, timeout_s=300))
    assert stale.get("ks", 0) > 300
    assert "ea" not in stale


def test_watchdog_keluar_nonzero_dan_alert_saat_stale():
    now = time.monotonic()
    alerts.beat("ks", now=now - 900)
    exits: list[int] = []
    sent: list[str] = []

    wd = alerts.AlertsWatchdog(
        interval_s=0.05, timeout_s=300.0,
        exit_fn=lambda code: exits.append(code),
        alert_fn=lambda text: sent.append(text),
        monotonic=lambda: now,
    )
    wd.start()
    deadline = time.monotonic() + 5
    while not exits and time.monotonic() < deadline:
        time.sleep(0.02)
    wd.stop()
    assert exits, "watchdog tidak keluar walau tidak ada tick alert > timeout"
    assert exits[0] != 0
    assert sent and "STALE" in sent[0].upper()
    _assert_md(sent[0])


# --------------------------------------------- F-1: startup DB belum siap

def test_daemon_keluar_nonzero_cepat_saat_db_belum_siap():
    """Reproduksi kondisi insiden: DB tidak ada. Daemon harus keluar non-zero
    dengan log jelas dalam budget singkat, BUKAN menggantung/mati diam."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    dead_port = sock.getsockname()[1]
    sock.close()

    env = dict(os.environ)
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_ID"):
        env.pop(key, None)
    env.update(
        DATABASE_URL=f"postgresql://x:x@127.0.0.1:{dead_port}/fund2",
        TELEGRAM_BOT_TOKEN="000:dummy",
        TELEGRAM_OWNER_ID="1",
        TELEGRAM_ALERTS_OFF="1",
        ALERTS_DB_READY_TIMEOUT_S="3",
        ALERTS_WATCHDOG_OFF="1",
    )
    t0 = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", "app.alerts"],
        cwd=str(API_DIR), env=env, capture_output=True, text=True, timeout=60,
    )
    elapsed = time.monotonic() - t0
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, "daemon harus keluar non-zero agar systemd restart"
    assert elapsed < 30, f"daemon menggantung {elapsed:.1f}s saat DB belum siap"
    assert "db belum siap" in out, out[-2000:]
    assert "TIDAK bisa start" in out, out[-2000:]
