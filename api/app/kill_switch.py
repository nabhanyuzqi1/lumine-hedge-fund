"""Kill-switch & emergency control (PRD v2.1 §5.7, v2.2 §16, KEPUTUSAN_OWNER D6/D11).

Mode:
  STOP_NEW_ORDERS   : tolak semua order baru.
  STOP_AND_FLATTEN  : tolak order baru + tutup semua posisi (confirm eksplisit,
                      risiko slippage dijelaskan; hanya manual, tidak pernah auto).
  PAUSE_STRATEGY    : hentikan strategi tertentu (daftar paused_strategies).
  GLOBAL_HALT       : hentikan semua entry; pelepasan butuh owner + checklist recovery.

State tersimpan di settings key 'kill_switch' (JSON) sehingga bertahan restart.
Setiap aktivasi / pelepasan / eskalasi / auto-trigger tercatat di kill_switch_events.
Auto-trigger (dapat dikonfigurasi lewat settings key 'kill_switch_triggers'):
  - drawdown harian 3% (A6), drawdown total 8% dari puncak equity (A7)
  - EA offline > 60 detik dengan posisi terbuka
  - 3 order FAILED beruntun (gagal eksekusi, bukan ditolak risk gate)
  - reconciler menemukan selisih posisi tak terjelaskan
Auto-trigger tidak pernah auto-flatten (D6): hanya STOP_NEW_ORDERS / GLOBAL_HALT.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from . import db, drawdown
from .risk import SQL_EXCLUDE_QA_POSITION
from .sse import broadcaster
from .state_machine import fetchall, fetchone

MODES = ("STOP_NEW_ORDERS", "STOP_AND_FLATTEN", "PAUSE_STRATEGY", "GLOBAL_HALT")
SEVERITY = {"PAUSE_STRATEGY": 1, "STOP_NEW_ORDERS": 2, "STOP_AND_FLATTEN": 3, "GLOBAL_HALT": 4}


class ReleaseForbidden(PermissionError):
    """Pelepasan kill-switch ditolak: bukan jalur owner.

    Keputusan owner 25 Nov 2026 (kartu t_7c070c31): driver QA, worker kanban,
    dan service otomatis TIDAK boleh me-release kill-switch. RELEASE hanya sah
    dari source 'dashboard' oleh owner/admin ber-2FA (atau kanal Telegram owner).
    Insiden 25 Nov 18:07-18:21: driver QA (actor svc-qa-driver, source
    kanban:t_baeb3ce4) me-release halt tiap ~2 menit -> 34 ACTIVATE / 33 RELEASE
    bergantian + setiap siklus mengirim alert Telegram ke owner.
    """


# Jalur yang TIDAK boleh me-release. Route /kill-switch/release menegakkan
# admin + 2FA + source dashboard; daftar ini menutup jalur lain (worker kanban,
# auto-trigger, service account) walau memanggil fungsi ini langsung.
RELEASE_FORBIDDEN_SOURCE_PREFIXES = ("kanban:", "auto:", "svc", "agent")
RELEASE_FORBIDDEN_ACTOR_PREFIXES = ("svc-", "svc_", "agent", "auto", "system", "bot")


def assert_release_allowed(source: str | None, actor: str | None) -> None:
    """Raise ReleaseForbidden bila pemanggil bukan jalur owner yang sah."""
    src = (source or "").strip().lower()
    act = (actor or "").strip().lower()
    if src.startswith(RELEASE_FORBIDDEN_SOURCE_PREFIXES):
        raise ReleaseForbidden(
            f"release ditolak: source '{source}' bukan jalur owner "
            "(RELEASE hanya via dashboard owner/admin ber-2FA)"
        )
    if act.startswith(RELEASE_FORBIDDEN_ACTOR_PREFIXES):
        raise ReleaseForbidden(
            f"release ditolak: actor '{actor}' adalah akun service/driver; "
            "RELEASE hanya oleh owner/admin ber-2FA via dashboard"
        )


SLIPPAGE_WARNING = (
    "STOP_AND_FLATTEN akan menutup SEMUA posisi terbuka di harga pasar saat ini. "
    "Risk slippage: eksekusi menutup tidak dijamin pada harga yang diminta; "
    "pada pasar cepat / spread melebar, harga fill bisa jauh lebih buruk. "
    "Konfirmasi eksplisit dibutuhkan (confirm=true)."
)

RECOVERY_CHECKLIST = [
    "Sumber masalah sudah ditemukan dan host aman",
    "Trading halt masih aktif (kill-switch tidak dilepas sebelum Verifikasi)",
    "MT5/EA sudah hidup kembali tanpa mengirim order baru",
    "Snapshot posisi broker sudah diambil",
    "Rekonsiliasi: posisi & pending orders cocok antara broker dan DB",
    "Heartbeat dan command channel sudah diuji di demo/staging",
    "Owner menyetujui resume trading",
]

DEFAULT_TRIGGERS: dict = {
    # A6: persen equity awal hari -> auto-halt (satu konstanta bersama).
    "daily_drawdown_pct": drawdown.DEFAULT_DAILY_DRAWDOWN_PCT,
    "total_drawdown_pct": 8.0,          # A7: 8% dari puncak equity -> auto-halt + notifikasi
    "ea_offline_seconds": 6.0,          # A12: 3 heartbeat x 2 s terlewat -> tandai offline,
                                        # blokir order baru (A11), alert
    "ea_offline_halt_seconds": 60.0,    # auto GLOBAL_HALT hanya bila offline lebih lama dari
                                        # ini (v2.1 §5.7; ROLLBACK_PLAN T9) dan ada posisi
    "ea_offline_requires_positions": True,  # halt EA offline hanya dengan posisi terbuka
    "consecutive_failed_orders": 3,     # 3 order FAILED beruntun
    "position_mismatch": True,          # reconciler: selisih posisi tak terjelaskan
    "check_interval_seconds": 5.0,
    # D6: auto-trigger tidak pernah auto-flatten.
    "modes": {
        "daily_drawdown": "GLOBAL_HALT",
        "total_drawdown": "GLOBAL_HALT",
        "ea_offline": "GLOBAL_HALT",
        "consecutive_failed": "STOP_NEW_ORDERS",
        "position_mismatch": "GLOBAL_HALT",
    },
}

INACTIVE_STATE: dict = {
    "active": False,
    "mode": None,
    "strategy": None,
    "reason": None,
    "source": None,
    "actor": None,
    "activated_at": None,
}

# ---- EA last-seen tracking (in-process; dipersist throttled ke settings) ----
_ea_seen_mono: float | None = None
_ea_last_persist_mono: float = 0.0
# Nilai persisten dibaca proses LAIN (alerts, metrics). Throttle 15 s membuat usia
# bergerigi 0..15 s dan memicu alert "EA OFFLINE" palsu tiap siklus (insiden 26 Nov).
EA_PERSIST_EVERY_S = 3.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_state(raw) -> dict:
    """Normalize nilai settings 'kill_switch' (bool lama / dict / None) ke state kanonik."""
    state = dict(INACTIVE_STATE)
    if raw is True:
        state.update(active=True, mode="STOP_NEW_ORDERS", source="legacy", reason="legacy bool")
    elif isinstance(raw, dict):
        mode = raw.get("mode")
        state.update(
            active=bool(raw.get("active")),
            mode=mode if mode in MODES else None,
            strategy=raw.get("strategy"),
            reason=raw.get("reason"),
            source=raw.get("source"),
            actor=raw.get("actor"),
            activated_at=raw.get("activated_at"),
        )
        if state["active"] and state["mode"] is None:
            state["mode"] = "STOP_NEW_ORDERS"
    return state


async def get_state() -> dict:
    settings = await db.get_settings()
    return normalize_state(settings.get("kill_switch"))


async def get_paused_strategies() -> list[str]:
    settings = await db.get_settings()
    raw = settings.get("paused_strategies")
    return [str(s) for s in raw] if isinstance(raw, list) else []


async def get_triggers() -> dict:
    settings = await db.get_settings()
    raw = settings.get("kill_switch_triggers")
    triggers = dict(DEFAULT_TRIGGERS)
    if isinstance(raw, dict):
        triggers.update({k: v for k, v in raw.items() if k != "modes"})
        modes = dict(DEFAULT_TRIGGERS["modes"])
        modes.update(raw.get("modes") or {})
        triggers["modes"] = modes
    return triggers


async def trigger_mode(trigger: str, default: str = "GLOBAL_HALT") -> str:
    """Mode kill-switch untuk satu auto-trigger, dibaca dari settings.

    SATU sumber mode untuk semua pemicu auto: evaluator (run_trigger_checks)
    dan risk gate (routes.py) wajib memakai nilai yang sama. Bug AUDIT-F2 #4:
    risk gate hardcode GLOBAL_HALT sementara evaluator memakai
    kill_switch_triggers.modes.daily_drawdown -> satu kondisi, dua mode.
    """
    triggers = await get_triggers()
    mode = (triggers.get("modes") or {}).get(trigger, default)
    return mode if mode in MODES else default


def halted_effective(settings: dict) -> bool:
    """True bila kill-switch aktif pada mode yang menghentikan semua entry.

    PAUSE_STRATEGY hanya menghentikan daftar strategi tertentu, jadi bukan
    "halted" global. Sumber kebenaran: settings 'kill_switch'. Flag legacy
    'halted' hanyalah mirror display (lihat sync_legacy_halted) dan tidak boleh
    dipakai untuk keputusan blokir: mirror basi pernah membuat SEMUA order
    ditolak selamanya setelah satu auto-halt (insiden 25 Nov 2026, t_4d524475).
    """
    state = normalize_state(settings.get("kill_switch"))
    return bool(state["active"]) and state["mode"] != "PAUSE_STRATEGY"


async def sync_legacy_halted(settings: dict | None = None) -> bool:
    """Selaraskan mirror legacy settings 'halted' dengan state kill-switch.

    'halted' dipertahankan hanya untuk kompatibilitas pembaca luar/dashboard:
    True selama kill-switch aktif non-PAUSE_STRATEGY, False selain itu.
    Dipanggil saat startup dan tiap siklus monitor auto-trigger, sehingga state
    setengah-halt (kill_switch inactive tapi 'halted' tertinggal True) sembuh
    sendiri tanpa aksi owner.

    Return True bila mirror ditulis ulang (dipakai test & log boot).
    """
    if settings is None:
        settings = await db.get_settings()
    expected = halted_effective(settings)
    if bool(settings.get("halted")) == expected:
        return False
    await db.set_setting("halted", expected)
    return True


async def record_event(
    conn,
    action: str,
    mode: str | None = None,
    *,
    strategy: str | None = None,
    source: str = "system",
    actor: str = "auto",
    reason: str | None = None,
    details: dict | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO kill_switch_events (action, mode, strategy, source, actor, reason, details)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (action, mode, strategy, source, actor, reason, json.dumps(details or {})),
    )


def state_brief(state: dict | None) -> dict:
    """Ringkas state kill-switch untuk details audit (sisi `from`/`to`)."""
    state = state or {}
    return {
        "active": bool(state.get("active")),
        "mode": state.get("mode"),
        "strategy": state.get("strategy"),
        "reason": state.get("reason"),
    }


def actor_label(actor: str | None) -> str:
    """Label aktor manusiawi untuk reason event (auto vs owner)."""
    actor = (actor or "").strip()
    if not actor or actor in ("auto", "system", "unknown"):
        return "otomatis oleh sistem"
    if actor.lower().startswith("tg:"):
        return f"manual via Telegram oleh owner ({actor})"
    return f"manual oleh owner ({actor})"


async def release_conditions() -> dict:
    """Snapshot kondisi saat pelepasan kill-switch (audit; gagal -> kosong)."""
    try:
        async with db.pool().connection() as conn:
            m = await compute_metrics(conn)
        return {
            "daily_drawdown_pct": round(float(m["daily_drawdown_pct"]), 2),
            "total_drawdown_pct": round(float(m["total_drawdown_pct"]), 2),
            "consecutive_failed": int(m["consecutive_failed"]),
            "open_positions": int(m["open_positions"]),
            "equity": float(m["equity"]),
        }
    except Exception:  # noqa: BLE001 - audit tidak boleh menggagalkan release
        return {}


def release_reason(actor: str | None, *, checklist_ack: bool,
                   conditions: dict | None = None) -> str:
    """Alasan TRANSISI pelepasan: siapa yang melepas + kondisi saat itu.

    Alasan aktivasi lama BUKAN alasan pelepasan; ia disimpan di
    details.previous / details.previous_reason.
    """
    parts = [f"release {actor_label(actor)}"]
    if checklist_ack:
        parts.append("checklist recovery diakui (ack)")
    conditions = conditions or {}
    if conditions.get("daily_drawdown_pct") is not None:
        parts.append(f"drawdown harian saat ini {conditions['daily_drawdown_pct']}%")
    if conditions.get("total_drawdown_pct") is not None:
        parts.append(f"drawdown total {conditions['total_drawdown_pct']}%")
    if conditions.get("consecutive_failed") is not None:
        parts.append(f"streak FAILED {conditions['consecutive_failed']}")
    return "; ".join(parts)


def _publish(state: dict, event: str) -> None:
    broadcaster.publish({"type": "kill_switch", "event": event, "state": state})
    # kompatibilitas frontend lama yang mendengarkan event 'halt'
    broadcaster.publish({"type": "halt", "armed": bool(state["active"]), "mode": state["mode"]})


async def activate(
    mode: str,
    *,
    strategy: str | None = None,
    reason: str | None = None,
    source: str = "dashboard",
    actor: str | None = None,
    details_extra: dict | None = None,
) -> dict:
    """Aktifkan kill-switch pada mode tertentu. Eskalasi otomatis bila mode baru
    lebih berat dari mode aktif. Return state baru.

    `details_extra` = field tambahan untuk details event (mis. daftar strategi
    saat PAUSE_STRATEGY) supaya satu transisi = satu event yang lengkap.
    """
    if mode not in MODES:
        raise ValueError(f"unknown kill-switch mode: {mode}")
    current = await get_state()
    if current["active"]:
        if SEVERITY[mode] <= SEVERITY[current["mode"]]:
            return current  # sudah aktif pada mode sama / lebih berat: no-op
        action = "ESCALATE"
    else:
        action = "ACTIVATE"

    state = {
        "active": True,
        "mode": mode,
        "strategy": strategy,
        "reason": reason,
        "source": source,
        "actor": actor,
        "activated_at": _now_iso(),
    }
    await db.set_setting("kill_switch", state)
    # t_baeb3ce4/t_4d524475: legacy mirror 'halted' mengikuti kill-switch.
    # PAUSE_STRATEGY tidak menghentikan order strategi lain jadi tidak men-set
    # halted. Mirror ini HANYA display/kompatibilitas: pembaca (risk gate, loop
    # agent, auto-SL) memakai state kill-switch lewat halted_effective(), dan
    # sync_legacy_halted() merapikan mirror basi tiap siklus monitor.
    if mode != "PAUSE_STRATEGY":
        await db.set_setting("halted", True)
    details = {
        "previous": current,
        "from": state_brief(current),
        "to": state_brief(state),
    }
    if details_extra:
        details.update(details_extra)
    async with db.pool().connection() as conn:
        await record_event(
            conn, action, mode,
            strategy=strategy, source=source, actor=actor or "auto", reason=reason,
            details=details,
        )
    _publish(state, action.lower())
    return state


async def release(
    *,
    checklist_ack: bool = False,
    strategy: str | None = None,
    source: str = "dashboard",
    actor: str | None = None,
) -> dict:
    """Lepas kill-switch (seluruh mode) atau satu strategi (PAUSE_STRATEGY).

    GLOBAL_HALT wajib checklist recovery + owner (D11). Setiap pelepasan
    mereset streak FAILED beruntun agar trigger lama tidak langsung menyala ulang.

    Otorisasi (AUDIT-F2, keputusan owner 25 Nov 2026): pemanggil dengan source
    kanban:/auto:/svc* atau actor svc-*/agent* ditolak ReleaseForbidden; route
    dashboard menegakkan admin + 2FA.
    """
    assert_release_allowed(source, actor)
    current = await get_state()
    if not current["active"]:
        # t_baeb3ce4: mirror legacy 'halted' bisa tertinggal True dari auto-halt
        # lama (release lama tidak pernah membersihkannya). Release eksplisit
        # harus menyelesaikan state setengah-halt ini, bukan early-return kotor.
        await db.set_setting("halted", False)
        return current

    if strategy is not None:
        # lepas satu strategi dari PAUSE_STRATEGY
        paused = await get_paused_strategies()
        paused = [s for s in paused if s.lower() != strategy.lower()]
        await db.set_setting("paused_strategies", paused)
        state = dict(INACTIVE_STATE) if not paused else dict(current)
        if not paused:
            await db.set_setting("kill_switch", state)
            await db.set_setting("halted", False)  # t_baeb3ce4: mirror legacy
        async with db.pool().connection() as conn:
            await record_event(
                conn, "RELEASE", "PAUSE_STRATEGY",
                strategy=strategy, source=source, actor=actor or "unknown",
                reason=f"resume strategi {strategy} {actor_label(actor)}",
                details={"paused_strategies": paused,
                         "from": state_brief(current),
                         "to": state_brief(state)},
            )
        if not paused:
            _publish(state, "release")
        return state

    if current["mode"] == "GLOBAL_HALT" and not checklist_ack:
        raise PermissionError("GLOBAL_HALT release membutuhkan checklist recovery (checklist_ack=true)")

    # AUDIT: kondisi diambil SEBELUM state direset (streak FAILED masih utuh),
    # alasan event RELEASE = alasan pelepasan (aktor + checklist ack + kondisi
    # saat itu), BUKAN salinan alasan aktivasi. Alasan aktivasi lama tetap
    # utuh di details.previous / details.previous_reason.
    conditions = await release_conditions()
    reason = release_reason(actor, checklist_ack=checklist_ack, conditions=conditions)

    state = dict(INACTIVE_STATE)
    await db.set_setting("kill_switch", state)
    await db.set_setting("paused_strategies", [])
    await db.set_setting("halted", False)  # t_baeb3ce4: mirror legacy ikut lepas
    # reset streak FAILED: order lama tidak boleh langsung memicu trigger baru
    await db.set_setting("trigger_ack", {"failed_streak_after": _now_iso()})
    async with db.pool().connection() as conn:
        await record_event(
            conn, "RELEASE", current["mode"],
            strategy=current.get("strategy"), source=source, actor=actor or "unknown",
            reason=reason,
            details={"checklist_ack": checklist_ack, "previous": current,
                     "previous_reason": current.get("reason"),
                     "release_reason": reason, "conditions": conditions,
                     "from": state_brief(current), "to": state_brief(state)},
        )
    _publish(state, "release")
    return state


async def pause_strategy(strategy: str, *, source="dashboard", actor=None, reason=None) -> dict:
    strategy = strategy.strip()
    if not strategy:
        raise ValueError("nama strategi tidak boleh kosong")
    paused = await get_paused_strategies()
    if not any(s.lower() == strategy.lower() for s in paused):
        paused.append(strategy)
    await db.set_setting("paused_strategies", paused)
    # Satu transisi = satu event: `activate` sudah mencatat ACTIVATE/ESCALATE
    # lengkap dengan from/to; dulu ada event ACTIVATE kedua di sini yang
    # menyalin reason (sering None) tanpa status asal/tujuan.
    return await activate(
        "PAUSE_STRATEGY", strategy=strategy,
        reason=reason or f"strategi {strategy} di-pause {actor_label(actor)}",
        source=source, actor=actor,
        details_extra={"paused_strategies": paused},
    )


# ---------------------------------------------------------------- flatten

async def flatten_positions(*, actor: str | None = None, source: str = "dashboard") -> list[dict]:
    """Tutup semua posisi terbuka: buat order CLOSE (RISK_PASS) per posisi.

    Order CLOSE tidak melewati risk gate (penutupan selalu diizinkan). EA
    mengambil lewat /bridge/poll; hasil FILLED menutup posisi di DB.
    Payload event RECEIVED mencatat `username` aktor (t_4651d431) supaya
    order flatten oleh layanan QA (role 'qa') dapat dikecualikan dari
    metrik anomaly harian.
    """
    async with db.pool().connection() as conn:
        async with conn.transaction():
            positions = await fetchall(conn, "SELECT * FROM positions WHERE status = 'OPEN'")
            created: list[dict] = []
            for p in positions:
                row = await fetchone(
                    conn,
                    """
                    INSERT INTO orders (user_id, symbol, side, volume, sl, tp, strategy,
                                        ticket, action, status)
                    VALUES (NULL, %s, %s, %s, NULL, NULL, %s, %s, 'CLOSE', 'RECEIVED')
                    RETURNING id, command_id
                    """,
                    (
                        p["symbol"], "SELL" if p["side"] == "BUY" else "BUY",
                        float(p["volume"]), p.get("strategy") or "flatten", p["ticket"],
                    ),
                )
                await conn.execute(
                    """
                    INSERT INTO order_events (order_id, from_status, to_status, payload)
                    VALUES (%s, NULL, 'RECEIVED', %s)
                    """,
                    (row["id"], json.dumps({"source": source, "action": "CLOSE",
                                            "position_ticket": p["ticket"],
                                            "username": actor})),
                )
                await transition_close(conn, row["id"])
                created.append({
                    "order_id": str(row["id"]), "command_id": str(row["command_id"]),
                    "position_ticket": p["ticket"], "symbol": p["symbol"],
                    "side": "SELL" if p["side"] == "BUY" else "BUY",
                    "volume": float(p["volume"]),
                })
            if created:
                await record_event(
                    conn, "FLATTEN_REQUEST", None,
                    source=source, actor=actor or "unknown",
                    reason=f"flatten {len(created)} posisi",
                    details={"orders": created},
                )
    if created:
        broadcaster.publish({"type": "flatten", "count": len(created),
                             "orders": [c["order_id"] for c in created]})
    return created


async def transition_close(conn, order_id: str) -> None:
    """RECEIVED -> RISK_PASS untuk order CLOSE (tanpa risk gate: menutup selalu boleh)."""
    from .state_machine import transition

    await transition(conn, order_id, "RISK_PASS", {"risk": "pass", "action": "CLOSE"})


# ---------------------------------------------------------------- metrics & triggers

async def compute_metrics(conn) -> dict:
    """Metrik risiko untuk dashboard + evaluasi auto-trigger."""
    daily = await fetchone(
        conn,
        # t_4651d431 + t_baeb3ce4: exclude posisi QA (order ditandai
        # QA_REATTRIBUTED atau dibuat user role 'qa') dari daily_pnl --
        # kontaminasinya memicu drawdown halt palsu. Lihat risk.py.
        "SELECT COALESCE(SUM(profit), 0) AS pnl FROM positions p "
        "WHERE p.status = 'CLOSED' AND p.close_time::date = now()::date "
        + SQL_EXCLUDE_QA_POSITION,
    )
    daily_pnl = float(daily["pnl"])
    balance_row = await fetchone(
        conn, "SELECT COALESCE(SUM(profit), 0) AS pnl FROM positions WHERE status = 'CLOSED'"
    )
    open_row = await fetchone(
        conn, "SELECT COALESCE(SUM(profit), 0) AS pnl, COUNT(*) AS n FROM positions "
              "WHERE status = 'OPEN'"
    )
    open_pnl = float(open_row["pnl"])
    open_positions = int(open_row["n"])

    settings = await db.get_settings()
    initial = float(settings.get("initial_balance", 10000.0))
    balance = initial + float(balance_row["pnl"])
    equity = balance + open_pnl
    hwm = settings.get("equity_high_water_mark")
    hwm = float(hwm) if hwm is not None else initial
    if equity > hwm:
        hwm = equity
        await db.set_setting("equity_high_water_mark", hwm)

    # Aritmetika bersama dengan gate order + breaker LLM (AUDIT-A2).
    daily_start = drawdown.start_balance(settings)
    daily_dd_pct = drawdown.pct_from_pnl(daily_pnl, daily_start)
    total_dd_pct = max(0.0, hwm - equity) / hwm * 100.0 if hwm else 0.0

    failed_streak = await consecutive_failed_count(conn, settings)
    ea_age = ea_last_seen_age_s()
    flatten_pending = await fetchone(
        conn,
        "SELECT COUNT(*) AS n FROM orders WHERE action = 'CLOSE' "
        "AND status NOT IN ('FILLED', 'FAILED')",
    )
    return {
        "daily_pnl": round(daily_pnl, 2),
        "daily_start_balance": daily_start,
        "daily_drawdown_pct": round(daily_dd_pct, 3),
        "initial_balance": initial,
        "balance": round(balance, 2),
        "open_pnl": round(open_pnl, 2),
        "equity": round(equity, 2),
        "equity_high_water_mark": round(hwm, 2),
        "total_drawdown_pct": round(total_dd_pct, 3),
        "open_positions": open_positions,
        "consecutive_failed": failed_streak,
        "ea_last_seen_age_s": round(ea_age, 1) if ea_age is not None else None,
        "flatten_pending": int(flatten_pending["n"]),
    }


async def consecutive_failed_count(conn, settings: dict) -> int:
    """Streak order FAILED akhir (gagal eksekusi; ditolak risk gate tidak dihitung).

    Hanya order yang dibuat setelah marker trigger_ack.failed_streak_after
    (di-set saat pelepasan kill-switch) yang dihitung.
    """
    ack = settings.get("trigger_ack") or {}
    after = ack.get("failed_streak_after") if isinstance(ack, dict) else None
    params: list = []
    where = ""
    if after:
        where = "AND o.created_at > %s"
        params.append(after)
    params.append(20)
    rows = await fetchall(
        conn,
        f"""
        SELECT o.status, e.payload
        FROM orders o
        LEFT JOIN LATERAL (
            SELECT payload FROM order_events
            WHERE order_id = o.id AND to_status = 'FAILED'
            ORDER BY id DESC LIMIT 1
        ) e ON true
        WHERE o.status IN ('FAILED', 'FILLED', 'SENT', 'STUCK', 'RISK_PASS', 'RECEIVED')
        {where}
        ORDER BY o.created_at DESC
        LIMIT %s
        """,
        tuple(params),
    )
    streak = 0
    for row in rows:
        if row["status"] != "FAILED":
            break
        payload = row["payload"] or {}
        if payload.get("risk") == "rejected":
            break  # ditolak risk gate, bukan gagal eksekusi
        streak += 1
    return streak


# ---- EA last-seen ----

def init_ea_seen(settings: dict | None = None) -> None:
    """Inisialisasi last-seen saat boot dari nilai persisten (restart tidak reset jam offline)."""
    global _ea_seen_mono
    if settings is None:
        return
    raw = settings.get("ea_last_seen_at")
    if isinstance(raw, str):
        try:
            seen_wall = datetime.fromisoformat(raw).timestamp()
            _ea_seen_mono = time.monotonic() - (time.time() - seen_wall)
        except ValueError:
            _ea_seen_mono = time.monotonic()
    else:
        _ea_seen_mono = time.monotonic()


async def mark_ea_seen() -> None:
    """Dipanggil bridge endpoints setiap kontak EA. Persist throttled."""
    global _ea_seen_mono, _ea_last_persist_mono
    now = time.monotonic()
    _ea_seen_mono = now
    if now - _ea_last_persist_mono >= EA_PERSIST_EVERY_S:
        _ea_last_persist_mono = now
        await db.set_setting("ea_last_seen_at", _now_iso())


def ea_last_seen_age_s() -> float | None:
    if _ea_seen_mono is None:
        return None
    return time.monotonic() - _ea_seen_mono


# ---------------------------------------------------------------- trigger engine

async def run_trigger_checks() -> list[dict]:
    """Evaluasi semua auto-trigger. Dipanggil monitor loop; return daftar trigger yang menyala."""
    triggers = await get_triggers()
    # t_4d524475: self-heal mirror legacy 'halted' tiap siklus monitor supaya
    # state setengah-halt tidak bertahan (keputusan blokir = state kill-switch).
    await sync_legacy_halted()
    state = await get_state()
    fired: list[dict] = []

    async with db.pool().connection() as conn:
        metrics = await compute_metrics(conn)

    def _mode(trigger: str) -> str:
        return triggers.get("modes", {}).get(trigger, "GLOBAL_HALT")

    def _should_fire(trigger: str, mode: str) -> bool:
        if not state["active"]:
            return True
        return SEVERITY[mode] > SEVERITY[state["mode"]]  # hanya eskalasi

    # 1. drawdown harian (A6)
    threshold = triggers.get("daily_drawdown_pct")
    if threshold is not None and metrics["daily_drawdown_pct"] >= float(threshold):
        mode = _mode("daily_drawdown")
        if _should_fire("daily_drawdown", mode):
            fired.append({"trigger": "daily_drawdown", "mode": mode,
                          "detail": f"drawdown harian {metrics['daily_drawdown_pct']:.2f}% "
                                    f">= {threshold}%"})

    # 2. drawdown total dari puncak equity (A7)
    threshold = triggers.get("total_drawdown_pct")
    if threshold is not None and metrics["total_drawdown_pct"] >= float(threshold):
        mode = _mode("total_drawdown")
        if _should_fire("total_drawdown", mode):
            fired.append({"trigger": "total_drawdown", "mode": mode,
                          "detail": f"drawdown total {metrics['total_drawdown_pct']:.2f}% "
                                    f">= {threshold}% dari puncak {metrics['equity_high_water_mark']:.2f}"})

    # 3. EA offline > X detik dengan posisi terbuka.
    # `ea_offline_seconds` = ambang TANDAI offline (A12: 6 s) dipakai alert dan
    # blokir order baru; `ea_offline_halt_seconds` = ambang GLOBAL_HALT (v2.1
    # §5.7: 60 s) supaya hiccup jaringan 6 detik tidak memicu halt.
    threshold = triggers.get("ea_offline_halt_seconds", 60.0)
    ea_age = metrics["ea_last_seen_age_s"]
    if threshold is not None and ea_age is not None and ea_age > float(threshold):
        if not triggers.get("ea_offline_requires_positions", True) or metrics["open_positions"] > 0:
            mode = _mode("ea_offline")
            if _should_fire("ea_offline", mode):
                fired.append({"trigger": "ea_offline", "mode": mode,
                              "detail": f"EA offline {ea_age:.0f}s (threshold {threshold}s), "
                                        f"{metrics['open_positions']} posisi terbuka"})

    # 4. N order FAILED beruntun
    threshold = triggers.get("consecutive_failed_orders")
    if threshold is not None and metrics["consecutive_failed"] >= int(threshold):
        mode = _mode("consecutive_failed")
        if _should_fire("consecutive_failed", mode):
            fired.append({"trigger": "consecutive_failed", "mode": mode,
                          "detail": f"{metrics['consecutive_failed']} order FAILED beruntun "
                                    f"(threshold {threshold})"})

    for f in fired:
        await activate(
            f["mode"],
            reason=f["detail"],
            source=f"auto:{f['trigger']}",
            actor="auto",
        )
    return fired


async def check_position_mismatch(tickets: list[int]) -> dict | None:
    """Dipanggil reconciler snapshot: posisi DB OPEN yang hilang dari broker
    tanpa order CLOSE FILLED = selisih tak terjelaskan -> kill-switch + alert."""
    if not tickets:
        return None
    triggers = await get_triggers()
    if not triggers.get("position_mismatch", True):
        return None
    mode = triggers.get("modes", {}).get("position_mismatch", "GLOBAL_HALT")
    detail = (f"reconciler: {len(tickets)} posisi hilang dari snapshot broker "
              f"tanpa penutupan yang bisa dijelaskan: {tickets}")
    state = await activate(mode, reason=detail, source="auto:position_mismatch", actor="auto")
    return {"trigger": "position_mismatch", "mode": mode, "tickets": tickets, "state": state}


async def monitor_loop(stop) -> None:
    """Background loop auto-trigger. Interval dari kill_switch_triggers.check_interval_seconds."""
    import asyncio

    while not stop.is_set():
        try:
            interval = float((await get_triggers()).get("check_interval_seconds", 5.0))
            interval = max(interval, 1.0)
            await run_trigger_checks()
        except Exception as exc:  # loop harus hidup
            print(f"[kill-switch] monitor error: {exc}", flush=True)
            interval = 5.0
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
