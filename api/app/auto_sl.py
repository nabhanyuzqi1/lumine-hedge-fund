"""Auto break-even + trailing stop deterministik (RISK-B, t_f3570608).

Loop deterministik di sisi API (bridge layer) -- BUKAN LLM, BUKAN ubah EA.
Dievaluasi timer terpisah di proses fund2-api (pola kill_switch.monitor_loop):

  1. R = |entry - SL awal|; SL awal = orders.sl order pembuka (positions.sl
     adalah SL broker saat ini yang bisa sudah bergeser).
  2. Break-even: profit mengambang >= be_trigger_r x R -> SL ke entry +-
     buffer (menutup spread/komisi; per simbol, default XAUUSD +$0.30).
     Hanya bila SL sekarang masih lebih buruk dari BE.
  3. Trailing: profit >= trail_activate_r x R -> SL di-trail pada jarak
     max(min_trail, trail_atr_mult x ATR(M5,14)); hanya mengencang.
  4. Invarian only-tighten: SL baru WAJIB lebih ketat dari SL efektif
     sekarang (positions.sl + target MODIFY_SL in-flight/baru selesai).
     TIDAK pernah melonggarkan.
  5. Eksekusi memakai antrean bridge_commands MODIFY_SL yang sudah
     didukung EA (LumineEA.mq5 ExecuteModify ~line 1533, TRADE_ACTION_SLTP).
     Setiap modify tercatat di order_events (AUTO_SL_MODIFY) dengan alasan
     BE/trail, R saat itu, dan ATR.

Pause: tidak ada modify saat trading dihentikan -- state kill-switch,
kill-switch aktif (mode apa pun), atau pause agent LLM aktif.

Scope posisi: strategy 'llm' ter-link order pembuka (pola endpoint
/llm-agent/*); parameter BE/trailing dibaca per posisi dari config efektif
merge(global, override) strategi order pembuka (RISK-D, global = ceiling).

Config settings key 'auto_sl' -- DEFAULT OFF. Selama OFF loop hanya membaca
settings dan tidak menulis apa pun (behavior sama dengan sekarang). Owner
aktifkan setelah verifikasi staging:
    python -m app.cli set-setting auto_sl '{"enabled": true}'
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

# Hanya stdlib di level modul: db.py mengimpor DEFAULT_AUTO_SL dari modul
# ini (pola risk.py / portfolio_risk.py), jadi import app.* di sini bersifat
# circular. Semua dependensi app diimpor lazy di dalam fungsi.

DEFAULT_AUTO_SL: dict = {
    "enabled": False,                       # DEFAULT OFF (RISK-B)
    "be_trigger_r": 1.0,                    # BE saat profit >= 1R
    "be_buffer_usd": {"XAUUSD": 0.30, "BTCUSD": 40.0},  # tutup spread/komisi
    "trail_atr_mult": 1.5,                  # jarak trail = max(min, k x ATR)
    "trail_activate_r": 1.0,                # trailing mulai di R ini (>= BE)
    "trail_min_usd": {"XAUUSD": 0.50, "BTCUSD": 10.0},  # floor jarak trail
    "atr_timeframe": "M5",
    "atr_period": 14,
    "interval_s": 10.0,                     # periode evaluasi loop
}

_EPS = 1e-9
_PRICE_DP = 5          # presisi kolom numeric(12,5)
_DONE_GRACE_S = 120    # DONE dianggap "mungkin belum terlihat snapshot" selama ini
_FAILED_RETRY_S = 600  # target yang FAILED tidak diulang selama ini
_RECENT_WINDOW_S = 900 # jendela query bridge_commands (15 menit)


def _pos_num(value, default: float) -> float:
    """float positif dari value, selain itu default (fail-safe config)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return f if f > 0 else default


def auto_sl_config(settings: dict) -> dict:
    """Config auto-SL efektif: default <- settings key 'auto_sl' (parsial).

    Nilai numerik tidak valid diganti default (salah config tidak boleh
    mematikan proteksi ataupun mengirim SL liar). trail_activate_r
    distop minimum = be_trigger_r: trailing selalu setelah BE (desain RISK-B).
    """
    cfg = dict(DEFAULT_AUTO_SL)
    raw = settings.get("auto_sl") if isinstance(settings, dict) else None
    if isinstance(raw, dict):
        for key in ("enabled", "be_trigger_r", "trail_atr_mult",
                    "trail_activate_r", "interval_s"):
            if raw.get(key) is not None:
                cfg[key] = raw[key]
        for key in ("be_buffer_usd", "trail_min_usd"):
            if isinstance(raw.get(key), dict):
                cfg[key] = raw[key]
    cfg["enabled"] = bool(cfg["enabled"])
    cfg["be_trigger_r"] = _pos_num(cfg["be_trigger_r"], 1.0)
    cfg["trail_atr_mult"] = _pos_num(cfg["trail_atr_mult"], 1.5)
    cfg["trail_activate_r"] = _pos_num(cfg["trail_activate_r"], 1.0)
    if cfg["trail_activate_r"] < cfg["be_trigger_r"]:
        cfg["trail_activate_r"] = cfg["be_trigger_r"]
    cfg["interval_s"] = _pos_num(cfg["interval_s"], 10.0)
    try:
        period = int(cfg.get("atr_period", 14))
    except (TypeError, ValueError):
        period = 14
    cfg["atr_period"] = period if period >= 2 else 14
    cfg["atr_timeframe"] = str(cfg.get("atr_timeframe") or "M5")
    for key in ("be_buffer_usd", "trail_min_usd"):
        clean: dict = {}
        for sym, val in (cfg[key] or {}).items():
            try:
                f = float(val)
            except (TypeError, ValueError):
                continue
            if f >= 0:
                clean[str(sym).upper()] = f
        cfg[key] = clean
    return cfg


def symbol_buffers(cfg: dict, symbol: str) -> tuple[float, float]:
    """(be_buffer, trail_min) untuk simbol; simbol tak dikenal -> 0.0."""
    be_buf = (cfg["be_buffer_usd"] or {}).get(symbol)
    trail_min = (cfg["trail_min_usd"] or {}).get(symbol)
    return (
        max(0.0, float(be_buf)) if be_buf is not None else 0.0,
        max(0.0, float(trail_min)) if trail_min is not None else 0.0,
    )


def position_config(global_cfg: dict, strategy_id: str, override: dict,
                    settings: dict) -> dict:
    """Cfg auto-SL efektif untuk SATU posisi (RISK-D, t_a172bb7b).

    Empat parameter milik config per-strategy (be_trigger_r, be_buffer,
    trail_atr_mult, trail_activate_r) di-merge dengan global lalu di-clamp
    ke ceiling global oleh risk_config.effective: override hanya bisa
    mengetatkan, tidak pernah melonggarkan proteksi.
    """
    from . import risk_config

    eff = risk_config.effective(strategy_id, override, settings)
    out = dict(global_cfg)
    out["be_trigger_r"] = eff["values"]["be_trigger_r"]
    out["trail_atr_mult"] = eff["values"]["trail_atr_mult"]
    out["trail_activate_r"] = eff["values"]["trail_activate_r"]
    out["be_buffer_usd"] = eff["values"]["be_buffer"]
    out["strategy_id"] = strategy_id
    out["risk_sources"] = eff["sources"]
    return out


def atr_from_candles(candles: list[dict], period: int = 14) -> float | None:
    """ATR = rata-rata True Range `period` bar terakhir.

    `candles` ascending {ts, open, high, low, close}; butuh period+1 bar
    (TR bar tertua memakai close bar sebelumnya). Kurang dari itu -> None:
    trailing tidak dihitung, BE tetap jalan (fail-safe per fitur).
    """
    try:
        rows = [(float(c["high"]), float(c["low"]), float(c["close"]))
                for c in candles]
    except (KeyError, TypeError, ValueError):
        return None
    if len(rows) < period + 1:
        return None
    trs = []
    for i in range(len(rows) - period, len(rows)):
        high, low = rows[i][0], rows[i][1]
        prev_close = rows[i - 1][2]
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(trs) / float(period)


def _tighter(side: str, a: float, b: float) -> bool:
    """True bila SL a lebih ketat dari SL b (long: lebih tinggi; short: lebih rendah)."""
    return a > b + _EPS if side == "BUY" else a < b - _EPS


def decide_sl_action(
    *,
    side: str,
    entry: float | None,
    initial_sl: float | None,
    current_sl: float | None,
    bid: float | None,
    ask: float | None,
    atr: float | None,
    cfg: dict,
    be_buffer: float = 0.0,
    trail_min: float = 0.0,
) -> dict:
    """Keputusan SL deterministik untuk SATU posisi (fungsi murni).

    Return {"action": "none"|"modify", "target", "reason", "detail"}.
    Semua kegagalan input menghasilkan "none" (fail-closed: tidak ada
    modify tanpa dasar hitung lengkap). Kandidat BE dan trailing masing-
    masing harus lolos (a) trigger R, (b) stop sah di sisi yang benar dari
    harga, (c) only-tighten terhadap SL efektif; yang terketat dipilih.
    """
    detail: dict = {"side": side, "entry": entry, "initial_sl": initial_sl,
                    "current_sl": current_sl, "atr": atr}
    none = {"action": "none", "target": None, "reason": None, "detail": detail}
    if side not in ("BUY", "SELL"):
        return none
    try:
        entry_f = float(entry) if entry is not None else None
        init_f = float(initial_sl) if initial_sl is not None else None
        bid_f = float(bid) if bid is not None else None
        ask_f = float(ask) if ask is not None else None
        cur_f = float(current_sl) if current_sl is not None else None
    except (TypeError, ValueError):
        return none
    if not entry_f or not init_f or not bid_f or not ask_f:
        return none  # komponen harga tidak lengkap -> tidak menebak
    r = abs(entry_f - init_f)
    detail["r"] = r
    if r <= _EPS:
        return none  # R nol -> BE/trailing tidak terdefinisi
    price = bid_f if side == "BUY" else ask_f
    profit_dist = (price - entry_f) if side == "BUY" else (entry_f - price)
    detail.update(price=price, profit_dist=profit_dist,
                  r_multiple=profit_dist / r)

    be_trigger = _pos_num(cfg.get("be_trigger_r"), 1.0)
    trail_activate = _pos_num(cfg.get("trail_activate_r"), 1.0)
    if trail_activate < be_trigger:
        trail_activate = be_trigger

    candidates: list[tuple[float, str]] = []
    if profit_dist >= be_trigger * r - _EPS:
        be_target = entry_f + be_buffer if side == "BUY" else entry_f - be_buffer
        detail["be_candidate"] = be_target
        candidates.append((be_target, "break_even"))
    atr_f = _pos_num(atr, 0.0)
    if profit_dist >= trail_activate * r - _EPS and atr_f > 0:
        dist = max(trail_min, _pos_num(cfg.get("trail_atr_mult"), 1.5) * atr_f)
        trail_target = price - dist if side == "BUY" else price + dist
        detail["trail_candidate"] = trail_target
        detail["trail_dist"] = dist
        candidates.append((trail_target, "trail_atr"))

    chosen: tuple[float, str] | None = None
    for target, reason in candidates:
        if side == "BUY" and target >= price - _EPS:
            continue  # SL long harus di bawah harga (stop sah, modify_gate_reason)
        if side == "SELL" and target <= price + _EPS:
            continue
        if cur_f is not None and not _tighter(side, target, cur_f):
            continue  # only-tighten: JANGAN pernah melonggarkan
        if chosen is None or _tighter(side, target, chosen[0]):
            chosen = (target, reason)
    if chosen is None:
        return none
    target = round(chosen[0], _PRICE_DP)
    detail["target"] = target
    return {"action": "modify", "target": target, "reason": chosen[1],
            "detail": detail}


# ------------------------------------------------------- loop bridge layer

POSITIONS_SQL = """
    SELECT p.ticket, p.order_id, p.symbol, p.side, p.volume,
           p.open_price, p.sl AS current_sl, p.tp,
           o.sl AS initial_sl, o.strategy AS strategy
    FROM positions p
    JOIN orders o ON o.id = p.order_id
    WHERE p.status = 'OPEN' AND o.strategy = 'llm' AND o.action = 'OPEN'
    ORDER BY p.id
"""

CANDLES_SQL = """
    SELECT ts, open, high, low, close FROM candles
    WHERE symbol = %s AND timeframe = %s
    ORDER BY ts DESC LIMIT %s
"""

RECENT_CMDS_SQL = """
    SELECT payload, status, created_at, resolved_at
    FROM bridge_commands
    WHERE action = 'MODIFY_SL'
      AND payload->>'ticket' = ANY(%s)
      AND created_at > now() - (%s || ' seconds')::interval
"""


def _paused(settings: dict) -> bool:
    """True bila trading dihentikan: kill-switch aktif / pause agent.

    Flag legacy 'halted' tidak dibaca: ia mirror state kill-switch dan bisa
    tertinggal True (insiden 25 Nov 2026, t_4d524475).
    """
    pause = settings.get("llm_agent_pause")
    if isinstance(pause, dict) and pause.get("active"):
        return True
    from .kill_switch import normalize_state

    return bool(normalize_state(settings.get("kill_switch"))["active"])


def _fold(cur: float | None, target: float, side: str) -> float:
    """Gabung SL efektif dengan target command: ambil yang paling ketat."""
    if cur is None:
        return target
    return max(cur, target) if side == "BUY" else min(cur, target)


async def run_cycle(cfg: dict | None = None) -> dict:
    """Satu evaluasi loop auto-SL. Return ringkasan (dipakai log/journal).

    Flag OFF -> {"skipped": "flag_off"} tanpa menulis apa pun (behavior
    sama dengan sebelum fitur ada). Pause -> {"skipped": "paused"}.

    Parameter BE/trailing dibaca PER POSISI dari config efektif
    merge(global, override) strategi order pembuka (RISK-D), sehingga
    override hanya bisa mengetatkan (ceiling global tetap berlaku).
    """
    from . import db, market, risk_config
    from .state_machine import fetchall

    settings = await db.get_settings()
    if cfg is None:
        cfg = auto_sl_config(settings)
    if not cfg["enabled"]:
        return {"skipped": "flag_off"}
    if _paused(settings):
        return {"skipped": "paused"}

    async with db.pool().connection() as conn:
        rows = await fetchall(conn, POSITIONS_SQL)
        if not rows:
            return {"positions": 0, "modified": 0}
        overrides = await risk_config.load_overrides(conn)
        symbols = sorted({r["symbol"] for r in rows})
        ticks = {s: market.latest(s) for s in symbols}
        atrs: dict[str, float | None] = {}
        for s in symbols:
            candles = await fetchall(
                conn, CANDLES_SQL,
                (s, cfg["atr_timeframe"], cfg["atr_period"] + 1))
            atrs[s] = atr_from_candles(
                [dict(r) for r in reversed(candles)], cfg["atr_period"])
        tickets = [str(r["ticket"]) for r in rows]
        recent = await fetchall(conn, RECENT_CMDS_SQL,
                                (tickets, str(_RECENT_WINDOW_S)))

        sides = {str(r["ticket"]): r["side"] for r in rows}
        effective: dict[str, float | None] = {
            str(r["ticket"]): (float(r["current_sl"])
                               if r["current_sl"] is not None else None)
            for r in rows
        }
        in_flight: set[str] = set()
        done_targets: dict[str, list[float]] = {}
        failed_targets: dict[str, list[float]] = {}
        now_utc = datetime.now(timezone.utc)
        for cmd in recent:
            payload = cmd["payload"] or {}
            ticket = str(payload.get("ticket", ""))
            if ticket not in sides:
                continue
            raw_sl = payload.get("sl")
            if raw_sl is None:
                continue
            try:
                target = float(raw_sl)
            except (TypeError, ValueError):
                continue
            status = cmd["status"]
            if status in ("QUEUED", "DELIVERED"):
                in_flight.add(ticket)
                effective[ticket] = _fold(
                    effective.get(ticket), target, sides[ticket])
            elif status == "DONE" and cmd["resolved_at"] is not None \
                    and cmd["resolved_at"] > now_utc - timedelta(seconds=_DONE_GRACE_S):
                # Snapshot broker bisa telat: SL DONE dianggap sudah di posisi.
                effective[ticket] = _fold(
                    effective.get(ticket), target, sides[ticket])
                done_targets.setdefault(ticket, []).append(target)
            elif status == "FAILED" and cmd["created_at"] is not None \
                    and cmd["created_at"] > now_utc - timedelta(seconds=_FAILED_RETRY_S):
                failed_targets.setdefault(ticket, []).append(target)

        modifies: list[dict] = []
        skipped: list[dict] = []
        for r in rows:
            ticket = str(r["ticket"])
            if ticket in in_flight:
                skipped.append({"ticket": r["ticket"], "why": "modify_in_flight"})
                continue
            tick = ticks.get(r["symbol"])
            if tick is None:
                skipped.append({"ticket": r["ticket"], "why": "no_tick"})
                continue
            if r["open_price"] is None or r["initial_sl"] is None:
                skipped.append({"ticket": r["ticket"],
                                "why": "missing_entry_or_initial_sl"})
                continue
            sid = str(r["strategy"] or "llm").lower()
            row_cfg = position_config(cfg, sid, overrides.get(sid, {}), settings)
            be_buf, trail_min = symbol_buffers(row_cfg, r["symbol"])
            decision = decide_sl_action(
                side=r["side"], entry=float(r["open_price"]),
                initial_sl=float(r["initial_sl"]),
                current_sl=effective.get(ticket),
                bid=tick.get("bid"), ask=tick.get("ask"),
                atr=atrs.get(r["symbol"]), cfg=row_cfg,
                be_buffer=be_buf, trail_min=trail_min,
            )
            if decision["action"] != "modify":
                skipped.append({"ticket": r["ticket"], "why": "no_action"})
                continue
            target = decision["target"]
            if any(abs(target - t) <= 1e-5
                   for t in done_targets.get(ticket, [])):
                skipped.append({"ticket": r["ticket"], "why": "target_done_recent"})
                continue
            if any(abs(target - t) <= 1e-5
                   for t in failed_targets.get(ticket, [])):
                skipped.append({"ticket": r["ticket"], "why": "target_failed_recent"})
                continue
            modifies.append({
                "ticket": r["ticket"], "order_id": r["order_id"],
                "symbol": r["symbol"], "side": r["side"],
                "strategy": sid,
                "risk_source": row_cfg["risk_sources"].get("be_trigger_r"),
                "tp": float(r["tp"]) if r["tp"] is not None else None,
                "current_sl": decision["detail"].get("current_sl"),
                "target": target, "reason": decision["reason"],
                "detail": decision["detail"],
            })

        if modifies:
            async with conn.transaction():
                for m in modifies:
                    await conn.execute(
                        """
                        INSERT INTO bridge_commands (order_id, action, payload)
                        VALUES (%s, 'MODIFY_SL', %s)
                        """,
                        (m["order_id"], json.dumps({
                            "ticket": m["ticket"], "sl": m["target"],
                            "tp": m["tp"], "reason": f"auto_{m['reason']}",
                            "detail": m["detail"],
                        })),
                    )
                    await conn.execute(
                        "UPDATE positions SET sl = %s, updated_at = now() "
                        "WHERE ticket = %s",
                        (m["target"], m["ticket"]),
                    )
                    await conn.execute(
                        """
                        INSERT INTO order_events
                            (order_id, from_status, to_status, payload)
                        VALUES (%s, NULL, 'AUTO_SL_MODIFY', %s)
                        """,
                        (m["order_id"], json.dumps({
                            "source": "auto_sl", "action": "MODIFY_SL",
                            "reason": m["reason"], "ticket": m["ticket"],
                            "strategy": m.get("strategy"),
                            "risk_source": m.get("risk_source"),
                            "sl": m["target"], "tp": m["tp"],
                            "previous_sl": m["current_sl"],
                            "r": m["detail"].get("r"),
                            "r_multiple": m["detail"].get("r_multiple"),
                            "atr": m["detail"].get("atr"),
                        })),
                    )

    if modifies:
        from .sse import broadcaster

        for m in modifies:
            broadcaster.publish({
                "type": "auto_sl_modify", "ticket": m["ticket"],
                "symbol": m["symbol"], "sl": m["target"],
                "reason": m["reason"],
            })
    return {"positions": len(rows), "modified": len(modifies),
            "skipped": skipped[:20]}


async def monitor_loop(stop) -> None:
    """Timer auto-SL di proses fund2-api (pola kill_switch.monitor_loop).

    Interval dari config (default 10 dtk). Flag OFF: loop tetap hidup
    (murah: satu get_settings per interval) tetapi run_cycle langsung
    return tanpa tulis apa pun.
    """
    from . import db

    while not stop.is_set():
        interval = 10.0
        try:
            cfg = auto_sl_config(await db.get_settings())
            interval = cfg["interval_s"]
            if cfg["enabled"]:
                summary = await run_cycle(cfg)
                if summary.get("modified"):
                    print(f"[auto-sl] {summary}", flush=True)
        except Exception as exc:  # noqa: BLE001 - loop harus hidup
            print(f"[auto-sl] monitor error: {exc}", flush=True)
            interval = 10.0
        try:
            await asyncio.wait_for(stop.wait(), timeout=max(interval, 1.0))
        except asyncio.TimeoutError:
            pass
