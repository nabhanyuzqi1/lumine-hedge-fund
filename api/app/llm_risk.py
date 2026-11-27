"""Risk gate & circuit breaker khusus agent LLM (t_f2llm2).

Empat lapisan di atas risk gate umum (risk.py) yang tetap dipakai PENUH
oleh semua order LLM:

0. Calendar blackout (t_d9e6b2a3): order baru LLM ditolak di sekitar event
   high-impact USD (NFP/CPI/FOMC). Fail-closed saat kalender unavailable.
   Order close tidak pernah diblok; hanya order LLM (role 'agent' ATAU
   strategy 'llm'). Keputusan LLM soal konteks makro (FUND2-LLM-2) tetap
   harus lolos gate deterministik ini.

1. Rate limit LLM (lebih ketat dari A8): max 2 order/menit, max 20
   order/hari, plus cooldown setelah order diterima gate. Counter dihitung
   dari tabel orders (semua attempt LLM non-CLOSE), sehingga membatasi
   juga beban API saat agent runaway. Order CLOSE (penutupan posisi)
   tidak dihitung: menutup selalu diizinkan.
2. Circuit breaker agent: 3 order LLM FAILED beruntun ATAU drawdown hari
   ini > 1.5% -> agent di-pause otomatis (settings 'llm_agent_pause') +
   alert Telegram. Resume hanya owner (POST /llm-agent/resume, admin+2FA).
   Berbeda dari breaker account-level kill_switch (yang mengecualikan
   order ditolak risk gate), breaker agent menghitung SEMUA FAILED LLM:
   3 penolakan beruntun juga menandakan agent stuck/looping yang harus
   dihentikan.
3. Control gate untuk loop agent: kill-switch aktif / agent pause ->
   skip siklus (agent tidak memanggil LLM, tidak POST order). Flag legacy
   'halted' tidak dibaca: mirror state kill-switch (t_4d524475).

Semua pause/resume tercatat di kill_switch_events (audit append-only).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from . import db, drawdown
from .risk import DEFAULT_LLM_RISK
from .state_machine import fetchall, fetchone

PAUSE_INACTIVE: dict = {
    "active": False,
    "reason": None,
    "source": None,
    "actor": None,
    "activated_at": None,
}

# ── Calendar blackout (t_d9e6b2a3, keputusan CEO final) ─────────────────────
# Window ±30 menit sekitar event impact High ber-mata uang USD (NFP/CPI/
# FOMC). Berlaku sama untuk XAUUSD dan BTCUSD (keduanya kena USD liquidity
# shock). Key settings: 'llm_risk.calendar_blackout' (merge parsial, pola
# get_llm_risk). Default enabled=True; owner bisa mematikan via settings.
DEFAULT_CALENDAR_BLACKOUT: dict = {
    "enabled": True,
    "before_min": 30,
    "after_min": 30,
    "currencies": ["USD"],
}
BLACKOUT_TITLE_MAX = 60


def get_calendar_blackout(settings: dict) -> dict:
    """Konfigurasi efektif blackout: default <- settings, merge parsial."""
    cfg = dict(DEFAULT_CALENDAR_BLACKOUT)
    raw = settings.get("llm_risk")
    if isinstance(raw, dict):
        sub = raw.get("calendar_blackout")
        if isinstance(sub, dict):
            for key in cfg:
                if sub.get(key) is not None:
                    cfg[key] = sub[key]
    return cfg


def _parse_time(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def calendar_blackout_reason(settings: dict, symbol: str,
                                   now_utc: datetime | None = None) -> str | None:
    """Alasan deterministik untuk menolak order baru LLM, atau None=lolos.

    Fail-closed: kalender 'unavailable' (>24 jam tanpa data) -> alasan
    'calendar_unavailable...'. 'stale' (<24 jam) tetap dipakai evaluasinya.
    Kalender diambil API-side via fetch_calendar() (cache 3600s), TIDAK
    percaya data dari agent/LLM. Window INCLUSIVE kedua ujung:
    [event - before_min, event + after_min].
    """
    cfg = get_calendar_blackout(settings)
    if not cfg.get("enabled", True):
        return None
    from .llm_context_extras import fetch_calendar

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    block = await fetch_calendar(now_utc)
    status = block.get("status")
    if status == "unavailable":
        return ("calendar_unavailable: data kalender tidak tersedia "
                f"({str(block.get('error') or 'unknown')[:120]})")
    if status not in ("ok", "stale"):
        return "calendar_unavailable: status kalender tidak dikenal"
    currencies = {str(c).strip().upper() for c in (cfg.get("currencies") or ["USD"])}
    try:
        before = int(cfg.get("before_min", 30))
        after = int(cfg.get("after_min", 30))
    except (TypeError, ValueError):
        before, after = 30, 30
    for event in block.get("events") or []:
        if not isinstance(event, dict):
            continue
        if str(event.get("impact", "")).strip().lower() != "high":
            continue
        if event.get("country") is not None:
            if str(event.get("country")).strip().upper() not in currencies:
                continue
        if event.get("currency") is not None:
            if str(event.get("currency")).strip().upper() not in currencies:
                continue
        # Event parser FUND2-LLM-1 hanya mengembalikan USD; pipeline
        # faireconomy tidak membawa 'country', jadi country-aware saja
        # di atas (tidak mengkueri flag broker).
        t = _parse_time(event.get("time_utc") or event.get("time"))
        if t is None:
            continue
        start_dt = t - timedelta(minutes=before)
        end_dt = t + timedelta(minutes=after)
        if start_dt <= now_utc <= end_dt:
            title = str(event.get("title") or "high-impact event")[:BLACKOUT_TITLE_MAX]
            return (f"calendar_blackout: {','.join(sorted(currencies)) or 'USD'} "
                    f"{str(event.get('impact'))} '{title}' at {t.isoformat()} "
                    f"within -{before}/{after}min window")
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_llm_risk(settings: dict) -> dict:
    """Batas LLM efektif: default <- settings key 'llm_risk' (merge parsial).

    Ambang circuit breaker (drawdown_pause_pct, consecutive_failed_pause,
    ea_offline_block_s) SELALU diturunkan dari settingan Risk Ops
    (settings key 'kill_switch_triggers', diubah owner via halaman
    Operations & Recovery) supaya breaker agent mengikuti risk ops —
    owner hanya punya satu tempat atur risiko. Key 'llm_risk' tetap
    mengatur batas non-breaker (rate limit, cooldown, check interval).
    """
    cfg = dict(DEFAULT_LLM_RISK)
    raw = settings.get("llm_risk")
    if isinstance(raw, dict):
        for key in cfg:
            if raw.get(key) is not None:
                cfg[key] = raw[key]
    # Rate limit LLM tidak boleh lebih longgar dari limit akun: gate
    # menegakkan `max_orders_per_min` core, jadi angka agent di atasnya
    # tidak pernah tercapai. Nilai efektif = yang paling ketat supaya UI
    # menampilkan angka yang benar-benar berlaku.
    try:
        core_raw = settings.get("max_orders_per_min")
        core_rate = float(core_raw) if core_raw is not None else None
    except (TypeError, ValueError):
        core_rate = None
    if core_rate is not None:
        try:
            cfg["max_orders_per_min"] = min(
                float(cfg["max_orders_per_min"]), core_rate)
        except (TypeError, ValueError, KeyError):
            pass
    return _apply_breaker_triggers(cfg, settings)


# Peta ambang breaker agent LLM -> trigger Risk Ops (kill_switch_triggers).
_BREAKER_FROM_TRIGGERS: dict = {
    "drawdown_pause_pct": "daily_drawdown_pct",
    "consecutive_failed_pause": "consecutive_failed_orders",
    "ea_offline_block_s": "ea_offline_seconds",
}


def _apply_breaker_triggers(cfg: dict, settings: dict) -> dict:
    """Timpa ambang breaker dgn nilai Risk Ops yang valid (fail-open per key:
    nilai trigger tidak valid/absen -> ambang default dipakai).

    Drawdown harian memakai helper bersama `drawdown.limit_pct`, jadi
    absen-nya key pun jatuh ke default A6 yang SAMA dengan gate order
    dan kill-switch (AUDIT-A2; dulu breaker punya default sendiri 1.5%).
    """
    triggers = settings.get("kill_switch_triggers")
    if not isinstance(triggers, dict):
        triggers = {}
    for cfg_key, trig_key in _BREAKER_FROM_TRIGGERS.items():
        val = triggers.get(trig_key)
        if val is None:
            continue
        try:
            cfg[cfg_key] = float(val)
        except (TypeError, ValueError):
            continue
    cfg["drawdown_pause_pct"] = drawdown.limit_pct(settings)
    return cfg


async def get_pause() -> dict:
    """State circuit breaker agent LLM dari settings (None -> inactive)."""
    settings = await db.get_settings()
    return normalize_pause(settings.get("llm_agent_pause"))


def normalize_pause(raw) -> dict:
    state = dict(PAUSE_INACTIVE)
    if isinstance(raw, dict):
        state.update(
            active=bool(raw.get("active")),
            reason=raw.get("reason"),
            source=raw.get("source"),
            actor=raw.get("actor"),
            activated_at=raw.get("activated_at"),
        )
    return state


async def llm_order_stats(conn, settings: dict) -> dict:
    """Counter order LLM untuk rate limit + breaker.

    Hanya order OPEN (action <> 'CLOSE'): penutupan posisi tidak mengambil
    kuota. Streak FAILED dihitung dari order terbaru ke belakang, hanya
    order setelah marker 'llm_breaker_ack.failed_streak_after' (di-set saat
    resume) yang dihitung agar streak lama tidak langsung memicu ulang.
    """
    last_min = await fetchone(
        conn,
        """
        SELECT COUNT(*) AS n FROM orders
        WHERE strategy = 'llm' AND (action IS NULL OR action <> 'CLOSE')
          AND created_at > now() - interval '60 seconds'
        """,
    )
    today = await fetchone(
        conn,
        """
        -- Kuota HARIAN menghitung order yang benar-benar lolos gate
        -- (bukan FAILED): order yang ditolak tidak mengubah posisi maupun
        -- biaya trading, dan kalau ikut dihitung maka sepuluh penolakan
        -- (mis. spread lebar pagi hari) mematikan trading sepanjang hari.
        -- Rate limit per MENIT tetap menghitung semua attempt.
        SELECT COUNT(*) AS n FROM orders
        WHERE strategy = 'llm' AND (action IS NULL OR action <> 'CLOSE')
          AND status <> 'FAILED'
          AND created_at::date = now()::date
        """,
    )
    last_accepted = await fetchone(
        conn,
        """
        SELECT MAX(created_at) AS last_at FROM orders
        WHERE strategy = 'llm' AND (action IS NULL OR action <> 'CLOSE')
          AND status <> 'FAILED'
        """,
    )
    ack = settings.get("llm_breaker_ack") or {}
    after = ack.get("failed_streak_after") if isinstance(ack, dict) else None
    where_after = ""
    params: list = []
    if after:
        where_after = "AND o.created_at > %s"
        params.append(after)
    params.append(20)
    rows = await fetchall(
        conn,
        f"""
        SELECT o.status,
               (SELECT e.payload->'fail'->>'stage' FROM order_events e
                 WHERE e.order_id = o.id AND e.to_status = 'FAILED'
                 ORDER BY e.id DESC LIMIT 1) AS fail_stage
        FROM orders o
        WHERE o.strategy = 'llm' AND (o.action IS NULL OR o.action <> 'CLOSE')
        {where_after}
        ORDER BY o.created_at DESC
        LIMIT %s
        """,
        tuple(params),
    )
    # Penolakan gate risiko (`fail.stage = 'risk_gate'`) BUKAN kegagalan
    # eksekusi: gate bekerja benar, order tidak pernah sampai ke broker.
    # Kalau ikut dihitung, 3 penolakan wajar (spread lebar, lot di bawah
    # minimum, sesi tutup) mem-pause agent berjam-jam: kejadian nyata
    # 26-11-2026 08:26 UTC. Yang dihitung hanya kegagalan di luar gate.
    streak = 0
    for row in rows:
        if row["status"] != "FAILED":
            break
        if (row["fail_stage"] or "") == "risk_gate":
            continue
        streak += 1
    last_at = last_accepted["last_at"] if last_accepted else None
    if last_at is not None and last_at.tzinfo is None:
        last_at = last_at.replace(tzinfo=timezone.utc)
    return {
        "last_minute": int(last_min["n"]),
        "today": int(today["n"]),
        "last_accepted_at": last_at,
        "failed_streak": streak,
    }


async def daily_drawdown_pct(conn, settings: dict) -> float:
    """Drawdown hari ini (%) dari equity awal hari - aritmetika bersama.

    Aritmetika dan fallback saldo diambil dari `app.drawdown` supaya gate
    order, kill-switch, dan breaker LLM tidak pernah berbeda rumus
    (AUDIT-A2).
"""
    row = await fetchone(
        conn,
        "SELECT COALESCE(SUM(profit), 0) AS pnl FROM positions "
        "WHERE status = 'CLOSED' AND close_time::date = now()::date",
    )
    return drawdown.pct_from_pnl(float(row["pnl"]),
                                 drawdown.start_balance(settings))


def context_fields(settings: dict, stats: dict, ea_age_s: float | None) -> dict:
    """Susun field RiskContext khusus LLM dari stats + usia EA terakhir."""
    cfg = get_llm_risk(settings)
    cooldown_remaining = 0.0
    last = stats.get("last_accepted_at")
    if last is not None:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        remaining = float(cfg["cooldown_s"]) - (
            datetime.now(timezone.utc) - last
        ).total_seconds()
        cooldown_remaining = max(0.0, remaining)
    return {
        "is_llm": True,
        "llm_orders_last_minute": stats["last_minute"],
        "llm_orders_today": stats["today"],
        "llm_cooldown_remaining_s": cooldown_remaining,
        "ea_offline_s": ea_age_s,
    }


async def _set_setting(value_key: str, value, conn=None) -> None:
    if conn is not None:
        await conn.execute(
            """
            INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, now())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """,
            (value_key, json.dumps(value)),
        )
    else:
        await db.set_setting(value_key, value)


def _actor_label(actor: str | None) -> str:
    """Label aktor manusiawi untuk reason event audit (auto vs owner)."""
    actor = (actor or "").strip()
    if not actor or actor in ("auto", "system", "unknown"):
        return "otomatis oleh sistem"
    if actor.lower().startswith("tg:"):
        return f"manual via Telegram oleh owner ({actor})"
    return f"manual oleh owner ({actor})"


async def _resume_conditions(conn=None) -> tuple[dict, dict | None]:
    """Snapshot kondisi saat resume + ambang efektif (audit, tidak boleh gagal).

    Alasan event RESUME harus menggambarkan kondisi SAAT transisi, bukan
    menyalin alasan pause. Return ({}, None) bila pembacaan gagal: resume
    tetap jalan, audit hanya kehilangan detail kondisi.
    """
    try:
        settings = await db.get_settings()
        thresholds = get_llm_risk(settings)

        async def _snapshot(c):
            return (await daily_drawdown_pct(c, settings),
                    await llm_order_stats(c, settings))

        if conn is not None:
            dd, stats = await _snapshot(conn)
        else:
            async with db.pool().connection() as own:
                dd, stats = await _snapshot(own)
        return {
            "daily_drawdown_pct": round(float(dd), 2),
            "failed_streak": int(stats["failed_streak"]),
            "orders_today": int(stats["today"]),
        }, thresholds
    except Exception:  # noqa: BLE001 - audit tidak boleh menggagalkan resume
        return {}, None


def _resume_reason(actor: str | None, conditions: dict) -> str:
    """Alasan TRANSISI resume: siapa yang resume + kondisi saat resume."""
    parts = [f"resume {_actor_label(actor)}"]
    if conditions.get("daily_drawdown_pct") is not None:
        parts.append(f"drawdown harian saat ini {conditions['daily_drawdown_pct']}%")
    if conditions.get("failed_streak") is not None:
        parts.append(f"streak FAILED {conditions['failed_streak']}")
    if conditions.get("orders_today") is not None:
        parts.append(f"{conditions['orders_today']} order LLM hari ini")
    return "; ".join(parts)


async def pause_agent(*, reason: str, source: str = "auto:llm_breaker",
                      actor: str = "auto", conn=None,
                      thresholds: dict | None = None) -> dict:
    """Pause agent LLM (idempotent). Tercatat di kill_switch_events.

    `thresholds` = cfg efektif (get_llm_risk) saat event tercatat; disimpan
    di details.thresholds supaya audit bisa membedakan ambang saat itu vs
    sekarang (parameter Risk Ops bisa berubah setelah event terjadi).
    """
    current = await get_pause()
    if current["active"]:
        return current
    state = {
        "active": True,
        "reason": reason,
        "source": source,
        "actor": actor,
        "activated_at": _now_iso(),
    }
    await _set_setting("llm_agent_pause", state, conn)
    details = dict(state)
    # Alasan event PAUSE = alasan trigger breaker itu sendiri (bukan salinan
    # state lama); from/to eksplisit supaya History terbaca tanpa menebak.
    details["previous"] = current
    details["from"] = {"agent_status": "ACTIVE"}
    details["to"] = {"agent_status": "PAUSED"}
    if thresholds is not None:
        details["thresholds"] = thresholds
    await _record_event("AGENT_PAUSE", source=source, actor=actor, reason=reason,
                        details=details, conn=conn)
    return state


async def resume_agent(*, actor: str, source: str = "dashboard", conn=None) -> dict:
    """Resume agent LLM (hanya owner via endpoint admin+2FA).

    Me-set marker llm_breaker_ack.failed_streak_after agar streak FAILED
    lama tidak langsung memicu pause ulang pada evaluasi berikutnya.
    Event AGENT_RESUME mencatat alasan TRANSISI (siapa resume + kondisi saat
    resume); alasan pause lama tersimpan di details.previous/previous_reason.
    """
    current = await get_pause()
    if not current["active"]:
        return current
    # Snapshot kondisi diambil SEBELUM marker ack di-set (streak lama masih utuh).
    conditions, thresholds = await _resume_conditions(conn)
    state = dict(PAUSE_INACTIVE)
    await _set_setting("llm_agent_pause", state, conn)
    await _set_setting("llm_breaker_ack", {"failed_streak_after": _now_iso()}, conn)
    reason = _resume_reason(actor, conditions)
    await _record_event("AGENT_RESUME", source=source, actor=actor,
                        reason=reason,
                        details={"previous": current,
                                 "previous_reason": current.get("reason"),
                                 "resume_reason": reason,
                                 "conditions": conditions,
                                 "thresholds": thresholds,
                                 "from": {"agent_status": "PAUSED"},
                                 "to": {"agent_status": "ACTIVE"}},
                        conn=conn)
    return state


async def _record_event(action: str, *, source: str, actor: str,
                        reason: str | None, details: dict, conn=None) -> None:
    from .kill_switch import record_event

    if conn is not None:
        await record_event(conn, action, None, source=source, actor=actor,
                           reason=reason, details=details)
        return
    async with db.pool().connection() as own:
        await record_event(own, action, None, source=source, actor=actor,
                           reason=reason, details=details)


def breaker_alert_text(fired: list[dict]) -> str:
    details = "; ".join(f["detail"] for f in fired)
    return (
        f"LLM AGENT PAUSED (circuit breaker): {details}. "
        "Resume hanya oleh owner via POST /llm-agent/resume."
    )


async def evaluate_llm_breaker(conn=None, settings: dict | None = None,
                               notify: bool = True) -> list[dict]:
    """Evaluasi trigger breaker agent LLM; pause + alert saat menyala.

    Return daftar trigger yang menyala (kosong bila tidak ada / sudah pause).
    Dipanggil dari path order LLM (routes) dan monitor loop periodik.
    """
    if settings is None:
        settings = await db.get_settings()
    fired: list[dict] = []
    pause = normalize_pause(settings.get("llm_agent_pause"))
    if not pause["active"]:
        if conn is not None:
            fired = await _evaluate_triggers(conn, settings)
        else:
            async with db.pool().connection() as own:
                fired = await _evaluate_triggers(own, settings)
    if fired and notify:
        try:
            from .telegram_bot import notify_owner

            await notify_owner(breaker_alert_text(fired))
        except Exception:  # noqa: BLE001 - alert tidak boleh menjatuhkan gate
            pass
    return fired


async def _evaluate_triggers(conn, settings: dict) -> list[dict]:
    cfg = get_llm_risk(settings)
    fired: list[dict] = []
    stats = await llm_order_stats(conn, settings)
    n_fail = int(cfg["consecutive_failed_pause"])
    if stats["failed_streak"] >= n_fail:
        fired.append({
            "trigger": "consecutive_failed",
            "detail": (f"{stats['failed_streak']} order LLM FAILED "
                       f"beruntun (threshold {n_fail})"),
        })
    # None = trigger drawdown sengaja dimatikan owner di halaman Ops.
    dd_pct = cfg["drawdown_pause_pct"]
    if dd_pct is not None:
        dd = await daily_drawdown_pct(conn, settings)
        if dd >= float(dd_pct):
            fired.append({
                "trigger": "daily_drawdown",
                "detail": f"drawdown harian {dd:.2f}% >= {dd_pct}%",
            })
    if fired:
        await pause_agent(
            reason="; ".join(f["detail"] for f in fired),
            source="auto:llm_breaker", actor="auto", conn=conn,
            thresholds=cfg,
        )
    return fired


def control_block_reason(settings: dict) -> str | None:
    """Alasan loop agent harus skip siklus ini, atau None bila boleh jalan.

    Cek tiap loop (butir 4 kartu): kill-switch aktif atau agent di-pause
    circuit breaker -> agent tidak memanggil LLM sama sekali.

    Flag legacy 'halted' tidak dibaca: ia mirror state kill-switch dan bisa
    tertinggal True (insiden 25 Nov 2026, t_4d524475).
    """
    pause = settings.get("llm_agent_pause")
    if isinstance(pause, dict) and pause.get("active"):
        return f"agent di-pause circuit breaker: {pause.get('reason')}"
    ks = settings.get("kill_switch")
    if ks is True:
        return "kill-switch aktif"
    if isinstance(ks, dict) and ks.get("active"):
        return f"kill-switch aktif (mode: {ks.get('mode')})"
    return None


async def monitor_loop(stop) -> None:
    """Evaluasi periodik breaker agent LLM (di proses fund2-api)."""
    while not stop.is_set():
        try:
            settings = await db.get_settings()
            interval = max(
                float(get_llm_risk(settings).get("check_interval_seconds", 10.0)),
                1.0,
            )
            await evaluate_llm_breaker(settings=settings)
        except Exception as exc:  # loop harus hidup
            print(f"[llm-risk] monitor error: {exc}", flush=True)
            interval = 10.0
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


# ── LLM agent v2 (FUND2-LLM-B1, t_9f36a70a; rencana D4) ────────────────────
# Konstanta baru utk settings key 'llm_risk' (merge parsial, pola
# get_llm_risk): anti-spam order baru saat ada posisi llm OPEN, batas layer,
# dan kebijakan modify SL. DEFAULT_LLM_RISK (risk.py) TIDAK diubah; key v2
# hidup berdampingan dgn key lama di settings yang sama.
DEFAULT_LLM_AGENT_V2: dict = {
    "block_new_order_with_position": True,  # order baru ditolak bila ada posisi llm OPEN di simbol
    "max_layers": 2,                        # maks posisi llm OPEN per simbol (leg pertama + layer)
    "layer_volume_ratio_max": 1.0,          # volume layer <= rasio x volume leg pertama
    "modify_sl_only_tighten": True,         # SL hanya boleh memperketat (long naik / short turun)
}

# Toleransi floating-point utk perbandingan harga boundary (SL/TP tepat di
# limit harus LOULUS, bukan ditolak karena error biner).
_V2_EPS = 1e-9


def get_llm_agent_v2(settings: dict) -> dict:
    """Konfigurasi v2 efektif: default <- settings key 'llm_risk' (merge parsial)."""
    cfg = dict(DEFAULT_LLM_AGENT_V2)
    raw = settings.get("llm_risk")
    if isinstance(raw, dict):
        for key in cfg:
            if raw.get(key) is not None:
                cfg[key] = raw[key]
    return cfg


async def llm_open_positions(conn, symbol: str) -> list[dict]:
    """Posisi milik strategy 'llm' yang OPEN di `symbol` (positions↔orders).

    Terlama dulu (p.id ASC): elemen [0] = leg pertama, acuan rasio volume
    layer. Dipakai gate anti-spam (POST /orders) dan gate layer.
    """
    return await fetchall(
        conn,
        """
        SELECT p.* FROM positions p JOIN orders o ON o.id = p.order_id
        WHERE p.status = 'OPEN' AND p.symbol = %s AND o.strategy = 'llm'
        ORDER BY p.id
        """,
        (symbol,),
    )


def new_order_block_reason(positions: list[dict], cfg: dict, symbol: str) -> str | None:
    """Gate anti-spam (lapisan 2): order BARU llm ditolak bila ada posisi llm
    OPEN di simbol yang sama. None = lolos.

    Layer tidak lewat sini (punya gate sendiri). Loop agent punya pre-check
    serupa (lapisan 1) sebelum mengirim kind=order; dua lapis sesuai rencana.
    """
    if not cfg.get("block_new_order_with_position", True):
        return None
    if positions:
        return (
            f"llm_position_exists: {len(positions)} posisi llm OPEN di {symbol} "
            "(block_new_order_with_position); gunakan cut/sl/be/tp/layer/hold"
        )
    return None


def layer_gate_reason(positions: list[dict], cfg: dict, symbol: str, side: str,
                      volume: float) -> str | None:
    """Gate layer: searah dgn posisi existing, maks `max_layers` posisi llm
    OPEN di simbol, volume <= `layer_volume_ratio_max` x leg pertama.
    None = lolos. Tanpa posisi existing -> None (diperlakukan sebagai leg
    pertama biasa; gate anti-spam tidak menolaknya karena memang kosong)."""
    if not positions:
        return None
    first = positions[0]
    if side != first["side"]:
        return (
            f"layer_side_mismatch: layer harus searah {first['side']} "
            f"dgn posisi llm existing di {symbol}, dapat {side}"
        )
    try:
        max_layers = int(cfg.get("max_layers", 2))
    except (TypeError, ValueError):
        max_layers = 2
    if len(positions) >= max_layers:
        return (
            f"layer_max: {len(positions)}/{max_layers} posisi llm OPEN di {symbol} "
            "(max_layers)"
        )
    try:
        ratio = float(cfg.get("layer_volume_ratio_max", 1.0))
    except (TypeError, ValueError):
        ratio = 1.0
    first_vol = float(first["volume"])
    if float(volume) > first_vol * ratio + _V2_EPS:
        return (
            f"layer_volume: {volume} melebihi {ratio} x leg pertama "
            f"({first_vol}) di {symbol}"
        )
    return None


def modify_gate_reason(pos: dict, kind: str, new_sl, new_tp, *, bid, ask,
                       cfg: dict) -> str | None:
    """Gate modify (kind sl/be/tp) deterministik utk posisi llm OPEN.

    - SL (sl/be): hanya DIPERKETAT bila modify_sl_only_tighten (long: SL
      naik, short: SL turun); kind=be mengikuti aturan yang sama - BE yang
      sudah lebih ketat dari SL berjalan tetap diterima, yang melonggarkan
      ditolak. SL harus tetap stop yang sah (long: sl < bid, short: sl >
      ask) supaya tidak langsung men-trigger close.
    - TP: tidak melintasi harga sekarang (long: tp > bid, short: tp < ask).
    None = lolos. bid/ask None (tick tidak terbaca) -> fail-closed.
    """
    side = pos["side"]
    if bid is None or ask is None:
        return "modify_gate: tick harga sekarang tidak tersedia (fail-closed)"
    if kind in ("sl", "be"):
        if new_sl is None:
            return f"modify_{kind}: sl wajib diisi"
        new_sl = float(new_sl)
        if bool(cfg.get("modify_sl_only_tighten", True)) and pos["sl"] is not None:
            old_sl = float(pos["sl"])
            if side == "BUY" and new_sl < old_sl - _V2_EPS:
                return (f"modify_{kind}_tighten: long SL {new_sl} < SL lama {old_sl} "
                        "(hanya boleh memperketat)")
            if side == "SELL" and new_sl > old_sl + _V2_EPS:
                return (f"modify_{kind}_tighten: short SL {new_sl} > SL lama {old_sl} "
                        "(hanya boleh memperketat)")
        if side == "BUY" and new_sl >= bid - _V2_EPS:
            return f"modify_{kind}_invalid: long SL {new_sl} >= harga sekarang {bid}"
        if side == "SELL" and new_sl <= ask + _V2_EPS:
            return f"modify_{kind}_invalid: short SL {new_sl} <= harga sekarang {ask}"
    if kind == "tp":
        if new_tp is None:
            return "modify_tp: tp wajib diisi"
        new_tp = float(new_tp)
        if side == "BUY" and new_tp <= bid + _V2_EPS:
            return f"modify_tp_cross: long TP {new_tp} <= harga sekarang {bid}"
        if side == "SELL" and new_tp >= ask - _V2_EPS:
            return f"modify_tp_cross: short TP {new_tp} >= harga sekarang {ask}"
    return None
