"""Alert Telegram standalone: kill-switch aktif/nonaktif, EA offline, rekap harian.

PRD v2.1 §5.9 (cron harian: rekap P&L, kesehatan bridge, deteksi anomali →
Telegram), §5.8 (notifikasi reconciler), KEPUTUSAN_OWNER D12 (Telegram kanal
alert primer). Task FUND2-P1b hari 11.

Dijalankan sebagai proses terpisah dari fund2-api (systemd user service
fund2-alerts) supaya:
  - alert tetap jalan tanpa me-restart service API;
  - tidak ada edit di modul API existing (anti-clobber dengan kartu backend).

Sumber data dibaca dari Postgres (sama seperti fund2-api):
  - kill_switch_events  -> alert ACTIVATE / ESCALATE / RELEASE / FLATTEN_REQUEST
  - settings.ea_last_seen_at -> EA offline / recovery (transisi, tanpa spam)
  - positions / orders / candles -> rekap harian (24 jam terakhir)

Kirim pesan memakai telegram_bot.notify_owner (token + chat id owner dari env
TELEGRAM_BOT_TOKEN / TELEGRAM_OWNER_ID). Tanpa keduanya daemon no-op.

CLI:
  python -m app.alerts                # daemon (loop background + watchdog)
  python -m app.alerts --rekap-now    # kirim rekap harian sekarang, lalu exit

Ketahanan (kartu t_f837fe2c, temuan F-1 audit v2.2 — insiden 25 Nov 2026
06:45 WIB, daemon beku diam-diam setelah reboot):
  - Start DITAHAN sampai Postgres menerima query (`db.wait_ready`: retry +
    backoff eksplisit, log tiap percobaan). Budget habis (ALERTS_DB_READY_
    TIMEOUT_S, default 300 s) -> exit 75 supaya systemd mengulang, bukan diam.
  - Acquire koneksi selalu berbatas waktu (`db.connection()`); tidak ada
    jalur yang menunggu tanpa batas.
  - Tiap watcher dibungkus supervisor: exception tak tertangkap hanya
    me-restart watcher itu, bukan mematikan/membekukan daemon.
  - Watchdog thread memantau heartbeat semua watcher; bila tidak ada tick
    alert > ALERTS_STALE_TIMEOUT_S (default 300 s) -> dump stack ke journal,
    kirim alert "daemon stale", lalu exit 70 agar systemd me-restart.
  - Sinyal: SIGTERM/SIGINT = berhenti rapi; SIGUSR1 = dump stack semua
    thread ke journal (diagnosa freeze); SIGHUP = kirim self-test ke owner
    dari proses daemon yang sedang jalan (bukti jalur alert hidup).
"""
from __future__ import annotations

import asyncio
import faulthandler
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

from . import config, db, kill_switch, metrics
from .state_machine import fetchall, fetchone
from .telegram_bot import notify_owner
from paper import feed
from strategies.broker_time import broker_utc_offset_hours, stored_to_utc

log = logging.getLogger("fund2.alerts")

WIB = timezone(timedelta(hours=7))

KS_POLL_INTERVAL_S = 5.0
EA_CHECK_INTERVAL_S = 10.0
RECAP_WAKE_MAX_S = 600.0  # bangun tiap <=10 menit agar stop responsif & jam rekap bisa berubah
# Heartbeat saat menunggu jam rekap. WAJIB <= ALERTS_STALE_TIMEOUT_S/2, kalau
# tidak watchdog menganggap watcher recap mati (exit 70, restart tiap 5 menit).
RECAP_BEAT_S = 60.0

# ── resiliensi (kartu t_f837fe2c, temuan F-1 audit v2.2) ────────────────────
# Budget tunggu Postgres siap saat start. Habis -> keluar non-zero supaya
# systemd mengulang, TIDAK menggantung dan TIDAK diam.
DB_READY_TIMEOUT_S = float(config.get("ALERTS_DB_READY_TIMEOUT_S", "300") or 300)
# Watchdog: bila tidak ada tick alert sama sekali > N detik, proses keluar
# non-zero. 300 s = 5x interval watcher terlambat (rekap <=600 s, jadi
# heartbeat rekap diperbarui jauh lebih sering daripada timeout).
ALERTS_STALE_TIMEOUT_S = float(config.get("ALERTS_STALE_TIMEOUT_S", "300") or 300)
WATCHDOG_INTERVAL_S = float(config.get("ALERTS_WATCHDOG_INTERVAL_S", "15") or 15)
WATCHDOG_OFF = str(config.get("ALERTS_WATCHDOG_OFF", "") or "").strip().lower() in (
    "1", "true", "yes", "on")
EXIT_DB_NOT_READY = 75   # EX_TEMPFAIL: systemd Restart=always mengulang
EXIT_STALE = 70          # EX_SOFTWARE: daemon beku, systemd restart

# Event kill_switch_events yang di-alert. TRIGGERS_UPDATED & AUTO_TRIGGER
# sengaja diabaikan (noise; auto-trigger selalu menulis ACTIVATE/ESCALATE juga).
KS_ALERT_ACTIONS = ("ACTIVATE", "ESCALATE", "RELEASE", "FLATTEN_REQUEST")

# Anti-flapping (kartu t_7c070c31, insiden 25 Nov 2026 18:07-18:21): event
# ACTIVATE/RELEASE berulang untuk trigger+mode yang SAMA dalam jendela ini
# hanya di-alert SEKALI (yang pertama). Flapping 34x ACTIVATE / 33x RELEASE
# tiap ~2 menit membuat owner dibanjiri alert dan menutupi event penting.
# 0 = matikan dedupe (dipakai test). ESCALATE dan FLATTEN_REQUEST selalu dikirim.
KS_ALERT_DEDUPE_S = float(config.get("ALERTS_KS_DEDUPE_S", "300") or 300)
KS_DEDUPE_ACTIONS = ("ACTIVATE", "RELEASE")

ACTION_ICON = {"ACTIVATE": "🛑", "ESCALATE": "⚠️", "RELEASE": "✅", "FLATTEN_REQUEST": "🟠"}


def _md_escape(value) -> str:
    """Escape karakter Markdown Telegram (parse_mode 'Markdown') pada nilai dinamis.

    Underscore di reason/aktor (mis. id task 't_f2p1b3') membuat entity italic
    tak tertutup -> Telegram 400 "can't parse entities" -> alert tak terkirim.
    """
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("_", "\\_")
        .replace("*", "\\*")
        .replace("`", "\\`")
        .replace("[", "\\[")
    )


# ---------------------------------------------------------------- kill-switch events

def fmt_ks_event(row) -> str:
    """Baris kill_switch_events -> teks alert Telegram."""
    action = row["action"]
    icon = ACTION_ICON.get(action, "•")
    details = row["details"] if isinstance(row["details"], dict) else {}
    previous = details.get("previous") if isinstance(details, dict) else None
    lines: list[str] = []

    if action == "ACTIVATE":
        lines.append(f"{icon} KILL-SWITCH AKTIF")
        if row["mode"]:
            lines.append(f"mode: `{_md_escape(row['mode'])}`")
    elif action == "ESCALATE":
        prev_mode = (previous or {}).get("mode") if isinstance(previous, dict) else None
        lines.append(f"{icon} KILL-SWITCH ESKALASI")
        if row["mode"]:
            mode_line = f"mode: `{_md_escape(row['mode'])}`"
            if prev_mode:
                mode_line += f" (sebelumnya: `{_md_escape(prev_mode)}`)"
            lines.append(mode_line)
    elif action == "RELEASE":
        lines.append(f"{icon} KILL-SWITCH NONAKTIF (dilepas)")
        if row["mode"]:
            lines.append(f"mode sebelumnya: `{_md_escape(row['mode'])}`")
    elif action == "FLATTEN_REQUEST":
        orders = details.get("orders") if isinstance(details, dict) else None
        n = len(orders) if isinstance(orders, list) else None
        lines.append(f"{icon} FLATTEN: {n} posisi dikirim untuk ditutup" if n is not None
                     else f"{icon} FLATTEN posisi dikirim")
    if row["strategy"]:
        lines.append(f"strategi: `{_md_escape(row['strategy'])}`")
    lines.append(f"sumber: {_md_escape(row['source'])} | aktor: {_md_escape(row['actor'])}")
    if row["reason"]:
        lines.append(f"alasan: {_md_escape(row['reason'])}")
    return "\n".join(lines)


async def ks_poll_once(last_id: int) -> tuple[int, list[str]]:
    """Baca event kill_switch_events baru. Return (id_terakhir, daftar_teks).

    Anti-spam (insiden 23 Nov 2026): event dengan source berawalan 'kanban:'
    berasal dari worker kanban yang menguji kill-switch/flatten — TIDAK
    dikirim ke owner, cukup tercatat di tabel event + journal. Event dari
    sumber lain (telegram owner, dashboard, reconciler) tetap dikirim.
    """
    async with db.connection() as conn:
        rows = await fetchall(
            conn,
            "SELECT * FROM kill_switch_events WHERE id > %s AND action = ANY(%s) "
            "ORDER BY id",
            (last_id, list(KS_ALERT_ACTIONS)),
        )
    texts = []
    # Fingerprint alert yang sudah "dipakai" di jendela dedupe: (action, mode,
    # source) -> id event pertama. Event berikutnya dengan fingerprint sama
    # dilewati supaya flapping tidak men-spam owner. Sumber kanban: tidak
    # pernah dihitung (memang tidak pernah dikirim).
    seen_fp: dict[tuple, int] = {}
    if KS_ALERT_DEDUPE_S > 0:
        async with db.pool().connection() as conn:
            window_rows = await fetchall(
                conn,
                "SELECT id, action, mode, source FROM kill_switch_events "
                "WHERE created_at > now() - (%s * interval '1 second') "
                "ORDER BY id",
                (KS_ALERT_DEDUPE_S,),
            )
        for w in window_rows:
            if str(w.get("source") or "").startswith("kanban:"):
                continue
            seen_fp.setdefault((w["action"], w["mode"], w["source"]), w["id"])
    for r in rows:
        if str(r.get("source") or "").startswith("kanban:"):
            log.info("ks event worker dilewati (anti-spam): id=%s action=%s source=%s",
                     r["id"], r["action"], r["source"])
            continue
        fp = (r["action"], r["mode"], r["source"])
        if (KS_ALERT_DEDUPE_S > 0 and r["action"] in KS_DEDUPE_ACTIONS
                and seen_fp.get(fp, r["id"]) < r["id"]):
            log.info("ks alert dedupe (flapping guard): id=%s action=%s mode=%s source=%s",
                     r["id"], r["action"], r["mode"], r["source"])
            continue
        texts.append(fmt_ks_event(r))
    new_last = rows[-1]["id"] if rows else last_id
    return new_last, texts


# ---------------------------------------------------------------- EA offline watcher

def _parse_ea_age(raw) -> float | None:
    """settings.ea_last_seen_at (ISO string) -> usia dalam detik."""
    if not isinstance(raw, str):
        return None
    try:
        seen = datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return None
    return max(0.0, time.time() - seen)


async def ea_check_once(state: dict | None) -> tuple[dict, str | None]:
    """Transisi online/offline EA dari settings.ea_last_seen_at.

    state: {"online": bool | None, "offline_since": float | None (epoch)}.
    Observasi pertama hanya baseline (tanpa alert) supaya restart service tidak
    mengspam; transisi berikutnya di-alert sekali per kejadian.
    """
    st: dict = dict(state) if state else {}
    st.setdefault("online", None)
    st.setdefault("offline_since", None)
    triggers = await kill_switch.get_triggers()
    # ea_last_seen_at dipersist throttled (EA_PERSIST_EVERY_S) dan dibaca lintas
    # proses, jadi usia terbaca bisa lebih tua dari aslinya: beri kelonggaran.
    threshold = float(triggers.get("ea_offline_seconds", 60)) + kill_switch.EA_PERSIST_EVERY_S + 2.0
    settings = await db.get_settings()
    age = _parse_ea_age(settings.get("ea_last_seen_at"))

    if age is None:
        # belum ada kontak EA sama sekali: tetap unknown, tanpa alert
        return st, None

    online = age <= threshold
    prev = st["online"]

    if prev is None:
        st["online"] = online  # baseline pertama
        return st, None

    if prev is False and online:
        st["online"] = True
        dur = st.get("offline_since")
        dur_txt = ""
        if dur:
            m, s = divmod(max(0, time.time() - dur), 60)
            dur_txt = f"Offline selama ~{int(m)}m {int(s)}s. "
        st["offline_since"] = None
        return st, f"✅ EA ONLINE kembali\n{dur_txt}Bridge pulih."

    if prev is True and not online:
        st["online"] = False
        st["offline_since"] = time.time()
        async with db.connection() as conn:
            metrics = await kill_switch.compute_metrics(conn)
        lines = [
            "🚨 EA OFFLINE",
            f"Terakhir terlihat: {age:.0f}s lalu (threshold {threshold:.0f}s)",
            f"Posisi terbuka: {metrics['open_positions']} (SL broker-side tetap aktif)",
            "Order baru ditolak risk gate (PRD 5.8).",
        ]
        if metrics["open_positions"] > 0:
            lines.append("Auto-trigger kill-switch akan menyala bila dikonfigurasi.")
        return st, "\n".join(lines)

    return st, None


# ---------------------------------------------------------------- paper runner watcher

PAPER_CHECK_INTERVAL_S = 60.0
PAPER_STALE_S = 900.0  # 15 menit: paper_state tak diupdate saat market buka = tidak sehat
PAPER_RUNNER_UNIT = "fund2-paper-runner"
PAPER_STATE_KEYS = ("runner", "runner_mean_reversion")


def runner_service_status() -> str:
    """Status unit systemd paper runner via systemctl --user."""
    try:
        out = subprocess.run(
            ["systemctl", "--user", "is-active", PAPER_RUNNER_UNIT],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except Exception as exc:
        return f"unknown ({exc})"


def paper_market_open() -> bool:
    """Market XAUUSD buka menurut jam broker di log tick HFM (sumber sama
    dengan runner). Filter simbol: tanpa itu BTCUSD (crypto 24/7) membuat
    market dianggap selalu buka walau XAUUSD tutup.

    Blocking (baca file). Pemanggil async WAJIB lewat
    `_paper_market_open_async` supaya event loop tidak beku (t_1b2d66ab).
    """
    now = datetime.now(timezone.utc)
    return feed.is_market_open(feed.read_ticks(16, now, symbol="XAUUSD"), now)


async def _paper_market_open_async() -> bool:
    """`paper_market_open` di thread worker: baca+parse tick tidak menahan
    event loop, jadi watcher lain tidak kena PoolTimeout palsu.

    Nama `paper_market_open` dibaca saat runtime dari globals modul, sehingga
    monkeypatch (test) tetap berlaku.
    """
    return await asyncio.to_thread(paper_market_open)


async def paper_state_age_s(conn) -> float | None:
    """Usia (detik) paper_state runner terbaru; None bila belum ada baris."""
    rows = await fetchall(
        conn,
        "SELECT MAX(updated_at) AS ts FROM paper_state WHERE key = ANY(%s)",
        (list(PAPER_STATE_KEYS),),
    )
    ts = rows[0]["ts"] if rows else None
    if ts is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())


async def paper_check_once(state: dict | None) -> tuple[dict, str | None]:
    """Transisi sehat/tidak-sehat paper runner (DoD t_b93726cd).

    Tidak sehat bila service fund2-paper-runner tidak active, ATAU market buka
    (jam broker maju di log tick HFM) tapi paper_state tidak diupdate > 15
    menit. Observasi pertama hanya baseline (tanpa alert) supaya restart
    fund2-alerts tidak mengspam; transisi berikutnya di-alert sekali per
    kejadian, sama seperti watcher EA.
    """
    st: dict = dict(state) if state else {}
    st.setdefault("healthy", None)
    st.setdefault("unhealthy_since", None)

    service = await asyncio.to_thread(runner_service_status)
    async with db.connection() as conn:
        age = await paper_state_age_s(conn)
    market_open = await _paper_market_open_async()
    stale = market_open and (age is None or age > PAPER_STALE_S)
    healthy = service == "active" and not stale

    prev = st["healthy"]
    if prev is None:
        st["healthy"] = healthy  # baseline pertama
        return st, None

    if prev is False and healthy:
        st["healthy"] = True
        st["unhealthy_since"] = None
        # F-2 (audit v2.2, t_f837fe2c): 'paper_state' mengandung underscore ->
        # buka italic Markdown -> Telegram 400 "can't parse entities" ->
        # pesan pemulihan tidak pernah terkirim. Wajib lewat _md_escape.
        return st, (
            "✅ PAPER RUNNER pulih: service active, "
            f"{_md_escape('paper_state')} terupdate."
        )

    if prev is True and not healthy:
        st["healthy"] = False
        st["unhealthy_since"] = time.time()
        if service != "active":
            cause = f"service {PAPER_RUNNER_UNIT} status: {service}"
        else:
            age_txt = "belum ada" if age is None else f"{age / 60:.0f} menit lalu"
            cause = f"market buka tapi paper_state terakhir diupdate {age_txt}"
        lines = [
            "🚨 PAPER RUNNER TIDAK SEHAT",
            f"Penyebab: {cause}",
            f"Market: {'BUKA' if market_open else 'tutup'} | service: {service}",
            "Sinyal paper tidak terekam selama kondisi ini.",
        ]
        return st, "\n".join(lines)

    return st, None


async def paper_watch_loop(stop: asyncio.Event) -> None:
    if not _telegram_configured():
        return
    state: dict = {"healthy": None, "unhealthy_since": None}
    log.info("alerts paper-watch aktif")
    while not stop.is_set():
        beat("paper")
        try:
            state, text = await paper_check_once(state)
            if text:
                log.info("alert paper runner: %.80s", text.replace("\n", " | "))
                await notify_owner(text)
        except Exception as exc:  # loop harus hidup
            log.warning("paper_watch error: %s", exc)
        await _sleep_or_stop(stop, PAPER_CHECK_INTERVAL_S)


# ---------------------------------------------------------------- candle M5 watcher (DoD t_86507d65 #3)

CANDLE_CHECK_INTERVAL_S = 60.0
M5_STALE_S = 600.0   # candle M5 terakhir > 10 menit di balik waktu live = feed mati
CANDLE_SYMBOL = "XAUUSD"
CANDLE_TF = "M5"


async def _db_tz_offset_h(conn) -> int:
    """Offset (jam) timezone sesi DB terhadap UTC (Asia/Pontianak = 7)."""
    row = await fetchone(conn, "SELECT current_setting('TimeZone') AS tz")
    name = (row or {}).get("tz", "UTC") if row else "UTC"
    try:
        from zoneinfo import ZoneInfo
        offset = datetime.now(ZoneInfo(name)).utcoffset()
        return int(offset.total_seconds() // 3600) if offset else 0
    except Exception:  # noqa: BLE001 — nama tz tak dikenal: fallback UTC
        return 0


async def candle_age_s(conn, now: datetime) -> tuple[float | None, datetime | None]:
    """Usia candle M5 terakhir (detik sejak bar-open, true UTC) + ts true-UTC-nya.

    Konversi stored -> true UTC memakai konvensi yang sama dengan paper
    runner dan engine backtest (stored_to_utc, offset broker A1' UTC+7
    terukur) supaya kesehatan feed diukur dari sudut pandang yang sama
    dengan yang dibaca strategi.
    """
    rows = await fetchall(
        conn,
        "SELECT MAX(ts) AS ts FROM candles WHERE symbol = %s AND timeframe = %s",
        (CANDLE_SYMBOL, CANDLE_TF),
    )
    ts = rows[0]["ts"] if rows else None
    if ts is None:
        return None, None
    db_tz = await _db_tz_offset_h(conn)
    true_ts = stored_to_utc(ts, db_tz, broker_utc_offset_hours(now))
    return max(0.0, (now - true_ts).total_seconds()), true_ts


async def candle_check_once(state: dict | None) -> tuple[dict, str | None]:
    """Transisi sehat/mati feed candle M5 (DoD t_86507d65 #3).

    Tidak sehat bila market buka (jam broker maju di log tick HFM) tapi
    candle M5 terakhir > 10 menit di balik waktu live — persis insiden
    20 Nov 2026 (seed EA menyangkut di M1, tidak ada agregasi M1->M5,
    paper runner 5m starved). Observasi pertama hanya baseline (tanpa
    alert) supaya restart fund2-alerts tidak mengspam; transisi berikutnya
    di-alert sekali per kejadian, sama seperti watcher EA/paper.
    """
    st: dict = dict(state) if state else {}
    st.setdefault("healthy", None)
    st.setdefault("unhealthy_since", None)

    now = datetime.now(timezone.utc)
    market_open = await _paper_market_open_async()
    async with db.connection() as conn:
        age, true_ts = await candle_age_s(conn, now)
    stale = market_open and (age is None or age > M5_STALE_S)
    healthy = not stale

    prev = st["healthy"]
    if prev is None and healthy:
        st["healthy"] = True  # baseline pertama, feed sehat
        return st, None

    if prev is False and healthy:
        st["healthy"] = True
        st["unhealthy_since"] = None
        return st, "✅ FEED CANDLE M5 pulih: bar terakhir mengikuti waktu live."

    if prev is not False and not healthy:
        # alert saat transisi sehat->mati ATAU saat observasi pertama sudah
        # mati (watcher baru jalan saat feed sudah lama mati — insiden
        # t_86507d65). Observasi mati berikutnya diam (anti-spam).
        st["healthy"] = False
        if st.get("unhealthy_since") is None:
            st["unhealthy_since"] = time.time()
        age_txt = "belum ada" if age is None else f"{age / 60:.0f} menit lalu"
        bar_txt = "-" if true_ts is None else true_ts.strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            "🚨 FEED CANDLE M5 MATI",
            f"Candle M5 {CANDLE_SYMBOL} terakhir: {age_txt} (bar {bar_txt})",
            f"Market: {'BUKA' if market_open else 'tutup'} | "
            f"threshold {M5_STALE_S / 60:.0f} menit",
            "Paper runner 5m tidak akan menghasilkan sinyal selama feed mati.",
        ]
        return st, "\n".join(lines)

    return st, None


async def candle_watch_loop(stop: asyncio.Event) -> None:
    if not _telegram_configured():
        return
    state: dict = {"healthy": None, "unhealthy_since": None}
    log.info("alerts candle-watch aktif")
    while not stop.is_set():
        beat("candle")
        try:
            state, text = await candle_check_once(state)
            if text:
                log.info("alert candle M5: %.80s", text.replace("\n", " | "))
                await notify_owner(text)
        except Exception as exc:  # loop harus hidup
            log.warning("candle_watch error: %s", exc)
        await _sleep_or_stop(stop, CANDLE_CHECK_INTERVAL_S)


# ---------------------------------------------------------------- rekap harian

async def build_recap(now: datetime | None = None) -> str:
    """Rekap harian: P&L, posisi, kesehatan bridge (PRD 5.9 cron harian)."""
    now = now or datetime.now(WIB)
    async with db.connection() as conn:
        metrics = await kill_switch.compute_metrics(conn)
        state = await kill_switch.get_state()
        closed = await fetchall(
            conn,
            "SELECT symbol, side, volume, profit FROM positions "
            "WHERE status = 'CLOSED' AND close_time >= now() - interval '24 hours' "
            "ORDER BY close_time",
        )
        open_pos = await fetchall(
            conn,
            "SELECT symbol, side, volume, open_price, profit FROM positions "
            "WHERE status = 'OPEN' ORDER BY open_time",
        )
        stuck = await fetchone(
            conn, "SELECT COUNT(*) AS n FROM orders WHERE status IN ('SENT', 'STUCK')"
        )
        failed = await fetchone(
            conn,
            "SELECT COUNT(*) AS n FROM orders WHERE status = 'FAILED' "
            "AND created_at >= now() - interval '24 hours'",
        )
        candle = await fetchone(conn, "SELECT MAX(ts) AS ts FROM candles")

    wins = sum(1 for r in closed if float(r["profit"]) >= 0)
    losses = len(closed) - wins
    pnl = sum(float(r["profit"]) for r in closed)

    lines = [
        f"📊 *REKAP HARIAN fund2* — {now.strftime('%d %b %Y')} (window 24 jam)",
        "",
        f"P&L 24 jam: *{pnl:+.2f} USD* ({len(closed)} ditutup: {wins} win / {losses} loss)",
        f"Balance: {metrics['balance']:.2f} | Equity: {metrics['equity']:.2f} "
        f"(floating {metrics['open_pnl']:+.2f})",
        f"DD harian: {metrics['daily_drawdown_pct']:.2f}% | "
        f"DD total: {metrics['total_drawdown_pct']:.2f}% "
        f"(puncak {metrics['equity_high_water_mark']:.2f})",
        "",
    ]

    if open_pos:
        lines.append(f"Posisi terbuka: {len(open_pos)}")
        for p in open_pos:
            lines.append(
                f"• {_md_escape(p['symbol'])} {p['side']} {float(p['volume']):.2f} "
                f"@ {float(p['open_price']):.2f} → {float(p['profit']):+.2f}"
            )
    else:
        lines.append("Posisi terbuka: 0")

    lines.append("")
    lines.append("Bridge:")
    settings = await db.get_settings()
    ea_age = _parse_ea_age(settings.get("ea_last_seen_at"))
    if ea_age is None:
        lines.append("• EA: belum ada kontak")
    elif ea_age <= 60:
        lines.append(f"• EA: ONLINE ({ea_age:.0f}s lalu)")
    else:
        lines.append(f"• EA: OFFLINE {ea_age:.0f}s ⚠️")
    lines.append(f"• Order SENT/STUCK: {stuck['n']} | FAILED 24 jam: {failed['n']}")
    ks_txt = "AMAN" if not state["active"] else (
        f"AKTIF mode `{_md_escape(state['mode'])}` ⚠️")
    lines.append(f"• Kill-switch: {ks_txt}")
    if candle and candle["ts"] is not None:
        age_s = (datetime.now(timezone.utc) - candle["ts"]).total_seconds()
        lines.append(f"• Candle terakhir: {age_s / 60:.0f} menit lalu")
    lines.append(f"• Recorder: {_recorder_status()}")

    return "\n".join(lines)


def _recorder_status() -> str:
    """Status service recorder (fund2-hfm-recorder) via systemctl --user."""
    try:
        out = subprocess.run(
            ["systemctl", "--user", "is-active", "fund2-hfm-recorder"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except Exception as exc:
        return f"unknown ({exc})"


def next_recap_time(now: datetime | None = None) -> datetime:
    """Waktu rekap berikutnya: jam TELEGRAM_RECAP_HOUR_WIB (default 07:00) WIB."""
    now = now or datetime.now(WIB)
    hour = int(config.get("TELEGRAM_RECAP_HOUR_WIB", "7"))
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


# ---------------------------------------------------------------- heartbeat + watchdog

_STARTED_AT = time.monotonic()
_HEARTBEATS: dict[str, float] = {}
_HEARTBEAT_LOCK = threading.Lock()


def beat(name: str, *, now: float | None = None) -> None:
    """Catat tick terakhir watcher `name` (dibaca watchdog thread)."""
    with _HEARTBEAT_LOCK:
        _HEARTBEATS[name] = time.monotonic() if now is None else now


def heartbeat_snapshot() -> dict[str, float]:
    with _HEARTBEAT_LOCK:
        return dict(_HEARTBEATS)


def stale_watchers(
    *, now: float | None = None, timeout_s: float | None = None
) -> list[tuple[str, float]]:
    """[(nama, usia_detik)] watcher yang tidak beat > timeout (paling basi dulu)."""
    now = time.monotonic() if now is None else now
    limit = ALERTS_STALE_TIMEOUT_S if timeout_s is None else float(timeout_s)
    stale = [(n, now - ts) for n, ts in heartbeat_snapshot().items() if now - ts > limit]
    return sorted(stale, key=lambda item: -item[1])


def _notify_owner_sync(text: str, timeout_s: float = 10.0) -> bool:
    """Kirim alert dari thread watchdog (tanpa event loop). Best effort."""
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_OWNER_ID
    if not token or not chat_id:
        return False
    try:
        import httpx

        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=timeout_s,
        )
        data = resp.json()
        if not data.get("ok"):
            log.error("alert watchdog gagal: %s", data.get("description", data))
            return False
        return True
    except Exception as exc:  # noqa: BLE001 — best effort, jangan ganggu exit
        log.error("alert watchdog gagal: %s: %s", type(exc).__name__, exc)
        return False


class AlertsWatchdog(threading.Thread):
    """Pengawas heartbeat: keluar non-zero bila tidak ada tick alert > timeout.

    Sengaja THREAD, bukan task asyncio: kasus yang harus ditangkap adalah
    event loop itu sendiri yang beku (insiden 25 Nov 2026 06:45 WIB) — watchdog
    berbasis asyncio akan ikut beku dan tidak berguna. Sebelum keluar, stack
    semua thread di-dump ke journal supaya penyebabnya terlihat.
    """

    def __init__(
        self,
        *,
        timeout_s: float | None = None,
        interval_s: float | None = None,
        exit_fn=None,
        alert_fn=None,
        monotonic=None,
        name: str = "alerts-watchdog",
    ) -> None:
        super().__init__(name=name, daemon=True)
        self.timeout_s = (
            ALERTS_STALE_TIMEOUT_S if timeout_s is None else float(timeout_s)
        )
        self.interval_s = WATCHDOG_INTERVAL_S if interval_s is None else float(interval_s)
        self._exit = exit_fn or os._exit
        self._alert = alert_fn or _notify_owner_sync
        self._monotonic = monotonic or time.monotonic
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.wait(self.interval_s):
            try:
                stale = stale_watchers(now=self._monotonic(), timeout_s=self.timeout_s)
            except Exception:  # noqa: BLE001 — watchdog tidak boleh mati diam
                log.exception("watchdog gagal membaca heartbeat")
                continue
            if not stale:
                continue
            detail = ", ".join(f"{n} {age / 60:.0f}m" for n, age in stale)
            log.critical(
                "alerts daemon STALE: tidak ada tick alert > %.0fs (%s); dump stack "
                "lalu keluar exit %d agar systemd restart",
                self.timeout_s, detail, EXIT_STALE,
            )
            try:
                faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
            except Exception:  # noqa: BLE001
                pass
            self._alert(
                "🚨 *ALERTS DAEMON STALE*\n"
                f"Tidak ada tick alert dari: {_md_escape(detail)}\n"
                f"uptime {int(self._monotonic() - _STARTED_AT)}s; proses keluar "
                f"(exit {EXIT_STALE}) agar systemd me-restart. Stack sudah di-dump "
                "ke journal."
            )
            self._exit(EXIT_STALE)
            return


def _dump_stacks(signum=None, frame=None) -> None:  # noqa: ARG001 — signature signal
    """SIGUSR1: dump stack semua thread ke journal (diagnosa freeze).

    Argumen opsional: `loop.add_signal_handler` memanggil callback TANPA
    argumen, sedangkan handler signal klasik mengirim (signum, frame). Versi
    lama mewajibkan dua argumen sehingga SIGUSR1 selalu gagal dengan
    TypeError dan tidak pernah menghasilkan dump (t_1b2d66ab) — justru saat
    dump paling dibutuhkan untuk mendiagnosa daemon yang beku.
    """
    log.warning("SIGUSR1 diterima: dump stack semua thread")
    faulthandler.dump_traceback(file=sys.stderr, all_threads=True)


# ---------------------------------------------------------------- loops

async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=max(0.0, seconds))
    except asyncio.TimeoutError:
        pass


async def _supervise(name: str, factory, stop: asyncio.Event) -> None:
    """Jalankan satu watcher; exception tak tertangkap -> log + restart backoff.

    Sebelumnya satu exception di satu watcher (mis. PoolTimeout saat Postgres
    belum siap pada insiden 06:45 WIB) ikut mematikan/membekukan seluruh
    daemon lewat `asyncio.gather`. Sekarang watcher lain tetap jalan dan yang
    gagal dijalankan ulang.
    """
    delay = 1.0
    while not stop.is_set():
        try:
            await factory(stop)
            return
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — satu watcher tidak boleh mematikan daemon
            log.exception("watcher %s berhenti karena error; restart dalam %.0fs",
                          name, delay)
            await _sleep_or_stop(stop, delay)
            delay = min(60.0, delay * 2)


KS_LAST_ID_KEY = "alerts_last_ks_event_id"


async def ks_baseline() -> int:
    """id kill_switch_events terakhir yang SUDAH di-alert (persist di settings).

    Tanpa ini, setiap restart memakai `MAX(id)` sebagai baseline sehingga
    event yang terjadi saat daemon mati tidak pernah di-alert (insiden
    25 Nov 2026: event id 138/139 tidak pernah sampai ke owner). Bila setting
    belum ada (start pertama), baseline = MAX(id).
    """
    async with db.connection() as conn:
        rows = await fetchall(
            conn, "SELECT value FROM settings WHERE key = %s", (KS_LAST_ID_KEY,)
        )
    if rows:
        value = rows[0]["value"]
        try:
            return int(value)
        except (TypeError, ValueError):
            log.warning("setting %s tidak valid (%r); pakai MAX(id)",
                        KS_LAST_ID_KEY, value)
    async with db.connection() as conn:
        rows = await fetchall(
            conn, "SELECT COALESCE(MAX(id), 0) AS m FROM kill_switch_events"
        )
    return int(rows[0]["m"])


async def ks_note_sent(last_id: int) -> None:
    """Simpan id event terakhir yang sudah diproses (best effort)."""
    await db.set_setting(KS_LAST_ID_KEY, int(last_id))


async def ks_watch_loop(stop: asyncio.Event) -> None:
    if not _telegram_configured():
        return
    beat("ks")
    last_id = await ks_baseline()
    log.info("alerts ks-watch aktif (baseline event id %s)", last_id)
    while not stop.is_set():
        beat("ks")
        try:
            new_last, texts = await ks_poll_once(last_id)
            for text in texts:
                log.info("alert kill-switch terkirim: %.80s", text.replace("\n", " | "))
                await notify_owner(text)
            if new_last != last_id:
                last_id = new_last
                try:
                    await ks_note_sent(last_id)
                except Exception as exc:  # noqa: BLE001 — alert sudah terkirim
                    log.warning("gagal simpan %s: %s", KS_LAST_ID_KEY, exc)
        except Exception as exc:  # loop harus hidup
            log.warning("ks_watch error: %s", exc)
        await _sleep_or_stop(stop, KS_POLL_INTERVAL_S)


async def ea_watch_loop(stop: asyncio.Event) -> None:
    if not _telegram_configured():
        return
    state: dict = {"online": None, "offline_since": None}
    log.info("alerts ea-watch aktif")
    while not stop.is_set():
        beat("ea")
        try:
            state, text = await ea_check_once(state)
            if text:
                log.info("alert EA: %.80s", text.replace("\n", " | "))
                await notify_owner(text)
        except Exception as exc:
            log.warning("ea_watch error: %s", exc)
        await _sleep_or_stop(stop, EA_CHECK_INTERVAL_S)


async def daily_recap_loop(stop: asyncio.Event) -> None:
    if not _telegram_configured():
        return
    log.info("alerts rekap harian aktif (jam %s WIB)",
             config.get("TELEGRAM_RECAP_HOUR_WIB", "7"))
    while not stop.is_set():
        beat("recap")
        target = next_recap_time()
        wait = (target - datetime.now(WIB)).total_seconds()
        # Tunggu sampai jam rekap TAPI tetap kirim heartbeat tiap <=60 s.
        # Sebelumnya satu `beat("recap")` lalu tidur sampai RECAP_WAKE_MAX_S
        # (600 s) > ALERTS_STALE_TIMEOUT_S (300 s) -> watchdog menganggap
        # watcher recap mati dan keluar exit 70, daemon restart tiap ~5 menit
        # (insiden 26 Nov 2026 05:00 WIB).
        end = time.monotonic() + min(max(wait, 1.0), RECAP_WAKE_MAX_S)
        stopped = False
        while not stop.is_set():
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            beat("recap")
            try:
                await asyncio.wait_for(stop.wait(), timeout=min(RECAP_BEAT_S, remaining))
                stopped = True
                break
            except asyncio.TimeoutError:
                continue
        if stopped:
            return
        if datetime.now(WIB) >= target:
            try:
                text = await build_recap()
                log.info("rekap harian terkirim")
                await notify_owner(text)
            except Exception as exc:
                log.warning("rekap harian gagal: %s", exc)


async def _sev_watch_loop(stop: asyncio.Event) -> None:
    """SEV-1..SEV-3 (metrics.py) dengan heartbeat untuk watchdog."""
    await metrics.sev_watch_loop(stop, beat=beat)


def _telegram_configured() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_OWNER_ID)


async def _send_self_test() -> None:
    """Self-test dari proses daemon yang sedang jalan (dipicu SIGHUP)."""
    stamp = datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S")
    text = (
        f"✅ *ALERTS DAEMON HIDUP* — self-test {_md_escape(stamp)} WIB\n"
        f"pid: {os.getpid()} | uptime: {int(time.monotonic() - _STARTED_AT)}s\n"
        f"heartbeat: {_md_escape(', '.join(sorted(heartbeat_snapshot())) or 'belum ada')}\n"
        "Dikirim dari jalur kirim yang sama dengan alert produksi."
    )
    ok = await notify_owner(text)
    log.info("self-test SIGHUP: terkirim=%s", ok)


async def _amain() -> int:
    if not _telegram_configured():
        print("alerts off: TELEGRAM_BOT_TOKEN / TELEGRAM_OWNER_ID tidak diset", flush=True)
        return 0

    log.info(
        "alerts daemon start pid=%s (budget db %.0fs, watchdog %s, interval %.0fs)",
        os.getpid(), DB_READY_TIMEOUT_S,
        "MATI" if WATCHDOG_OFF else f"{ALERTS_STALE_TIMEOUT_S:.0f}s",
        WATCHDOG_INTERVAL_S,
    )
    await db.init_pool()
    try:
        # Insiden 06:45 WIB: watcher start sebelum Postgres siap. Sekarang
        # start ditahan sampai DB benar-benar menerima query, dengan retry
        # ber-backoff dan log tiap percobaan; budget habis -> keluar non-zero.
        waited = await db.wait_ready(timeout_s=DB_READY_TIMEOUT_S, logger=log)
    except Exception as exc:  # noqa: BLE001 — termasuk DBNotReady
        log.critical("alerts daemon TIDAK bisa start: %s", exc)
        await db.close_pool()
        return EXIT_DB_NOT_READY

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: stop.set())
    loop.add_signal_handler(signal.SIGUSR1, _dump_stacks)
    loop.add_signal_handler(signal.SIGHUP, lambda: asyncio.create_task(_send_self_test()))

    watchdog: AlertsWatchdog | None = None
    if not WATCHDOG_OFF:
        watchdog = AlertsWatchdog()
        watchdog.start()

    watchers = (
        ("ks", ks_watch_loop),
        ("ea", ea_watch_loop),
        ("paper", paper_watch_loop),
        ("candle", candle_watch_loop),
        ("recap", daily_recap_loop),
        # SEV-1..SEV-3 (PRD v2.2 §20, t_f2v22a10): satu daemon, satu sender.
        ("sev", _sev_watch_loop),
    )
    log.info("alerts daemon siap: db OK setelah %.1fs, %d watcher aktif",
             waited, len(watchers))
    tasks = [
        asyncio.create_task(_supervise(name, fn, stop), name=f"alerts-{name}")
        for name, fn in watchers
    ]
    await asyncio.gather(*tasks, return_exceptions=True)
    if watchdog is not None:
        watchdog.stop()
    await db.close_pool()
    log.info("alerts daemon berhenti rapi")
    return 0


async def _rekap_now() -> None:
    """CLI: kirim rekap sekarang (untuk uji DoD tanpa menunggu jam 07:00)."""
    if not _telegram_configured():
        print("alerts off: TELEGRAM_BOT_TOKEN / TELEGRAM_OWNER_ID tidak diset", flush=True)
        sys.exit(2)
    await db.init_pool()
    try:
        await db.wait_ready(timeout_s=min(60.0, DB_READY_TIMEOUT_S), logger=log)
        text = await build_recap()
        ok = await notify_owner(text)
        print(text)
        print(f"\n[alerts] rekap terkirim: {ok}", flush=True)
    finally:
        await db.close_pool()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if "--rekap-now" in sys.argv:
        asyncio.run(_rekap_now())
    else:
        sys.exit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
