"""Telegram owner channel untuk kill-switch (PRD v2.1 §5.7, v2.2 §16, D11/D12).

Hanya owner (TELEGRAM_OWNER_ID) yang perintahnya dilayani; pengirim lain diabaikan.
Butuh env TELEGRAM_BOT_TOKEN + TELEGRAM_OWNER_ID (api/.env). Tanpa token, loop
poller tidak jalan (fitur off, API Dashboard tetap berfungsi).

Guard pengiriman (test/worker): env TELEGRAM_ALERTS_OFF=1 membuat notify_owner()
no-op berlogged tanpa mematikan rekonsiliasi/bridge. Jangan diset di produksi.

Perintah:
  /status                    - status kill-switch + metrik risiko
  /stop                      - STOP_NEW_ORDERS
  /stopflatten [confirm]     - STOP_AND_FLATTEN (confirm eksplifit; risiko slippage)
  /flatten [confirm]         - tutup semua posisi (confirm eksplisit)
  /pause <strategi>          - PAUSE_STRATEGY
  /resume [strategi|ACK]     - lepas kill-switch; GLOBAL_HALT wajib ACK checklist
  /halt                      - GLOBAL_HALT
  /proposals                 - daftar usulan self-improve + status
  /approve <id> [alasan]     - setujui usulan -> deploy flag enabled (owner saja)
  /reject <id> [alasan]      - tolak usulan (flag enabled tidak diubah)
  /help
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

import httpx

from . import config, db, kill_switch

log = logging.getLogger("fund2.telegram")

OFFSETS_KEY = "telegram_update_offset"

HELP_TEXT = (
    "Perintah kill-switch (owner saja):\n"
    "/status - status kill-switch + metrik risiko\n"
    "/stop - tolak semua order baru\n"
    "/stopflatten - stop + tutup semua posisi (butuh konfirmasi)\n"
    "/flatten - tutup semua posisi (butuh konfirmasi)\n"
    "/pause <strategi> - pause satu strategi\n"
    "/resume - lepas kill-switch (/resume ACK untuk GLOBAL_HALT)\n"
    "/halt - GLOBAL_HALT (pelepasan butuh checklist recovery)\n"
    "/help - daftar perintah"
)


def parse_command(text: str) -> tuple[str, list[str]]:
    """'/stopflatten confirm' -> ('stopflatten', ['confirm'])."""
    parts = (text or "").strip().split()
    if not parts:
        return "", []
    cmd = parts[0].lstrip("/").split("@")[0].lower()
    return cmd, parts[1:]


async def tg_api(token: str, method: str, **params) -> dict:
    async with httpx.AsyncClient(timeout=35) as client:
        resp = await client.post(f"https://api.telegram.org/bot{token}/{method}", json=params)
        data = resp.json()
        if not data.get("ok"):
            log.warning("telegram %s failed: %s", method, data)
        return data


async def send_message(token: str, chat_id, text: str) -> None:
    data = await tg_api(token, "sendMessage", chat_id=chat_id, text=text,
                        parse_mode="Markdown")
    # Respons ok=False (mis. 400 parse Markdown, 429 rate limit) = TIDAK
    # terkirim; raise agar notify_owner melaporkan gagal, bukan sukses.
    if not data.get("ok"):
        raise RuntimeError(
            f"telegram sendMessage gagal: {data.get('description', data)}")


def alerts_suppressed() -> bool:
    """True bila env TELEGRAM_ALERTS_OFF aktif (1/true/yes/on).

    Guard untuk test/worker: mematikan PENGIRIMAN alert tanpa mematikan
    jalur rekonsiliasi/bridge itu sendiri. Dibaca saat dipanggil (bukan saat
    import) agar cukup di-set di shell worker. Sengaja TIDAK dibaca dari
    api/.env supaya tidak bisa terlanjur mati di produksi.
    """
    return os.environ.get("TELEGRAM_ALERTS_OFF", "").strip().lower() in (
        "1", "true", "yes", "on")


# ── anti-spam dedup (insiden 22-23 Nov 2026) ────────────────────────────────
# Alert dengan baris pertama identik dalam window ini hanya dikirim sekali.
# Key-nya baris pertama (dipotong 160 char); window 300 detik.
_DEDUP_WINDOW_S = 300.0
_dedup_seen: dict[str, float] = {}


def _dedup_hit(text: str) -> bool:
    """True bila alert identik sudah terkirim dalam window -> lewati."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    key = stripped.splitlines()[0][:160]
    now = time.monotonic()
    last = _dedup_seen.get(key)
    if last is not None and now - last < _DEDUP_WINDOW_S:
        return True
    _dedup_seen[key] = now
    stale = [k for k, t in _dedup_seen.items() if now - t >= _DEDUP_WINDOW_S * 4]
    for k in stale:
        _dedup_seen.pop(k, None)
    return False


async def notify_owner(text: str) -> bool:
    """Kirim alert ke owner Telegram (PRD 5.8: notifikasi reconciler).

    No-op bila token/chat belum dikonfigurasi, atau bila env
    TELEGRAM_ALERTS_OFF=1 (guard test/worker; insiden 22 Nov 2026: setiap
    siklus test reconciler mengirim alert sungguhan ke owner). Tidak pernah
    raise agar jalan rekonsiliasi tidak pernah gagal karena notifikasi.

    Anti-spam dedup (insiden 23 Nov 2026): alert dengan baris pertama
    identik dalam window _DEDUP_WINDOW_S dikirim sekali saja.
    """
    if alerts_suppressed():
        log.info("notify_owner dilewati (TELEGRAM_ALERTS_OFF): %.80s",
                 (text or "").replace("\n", " "))
        return False
    if _dedup_hit(text):
        log.info("notify_owner dedup (identik dalam %.0fs): %.80s",
                 _DEDUP_WINDOW_S, (text or "").replace("\n", " "))
        return False
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_OWNER_ID
    if not token or not chat_id:
        return False
    try:
        await send_message(token, chat_id, text)
        return True
    except Exception as exc:  # notifikasi tidak boleh menggagalkan rekonsiliasi
        log.warning("notify_owner gagal: %s", exc)
        return False


def _fmt_state(state: dict) -> str:
    if not state["active"]:
        return "kill-switch: *AMAN* (tidak aktif)"
    mode = state["mode"]
    line = f"kill-switch: *AKTIF* mode `{mode}`"
    if state.get("strategy"):
        line += f" (strategi `{state['strategy']}`)"
    line += f"\nsumber: {state.get('source')}, aktor: {state.get('actor')}"
    if state.get("activated_at"):
        line += f"\nsejak: {state['activated_at']}"
    return line


async def handle_command(text: str, chat_id, sender_id) -> str | None:
    """Eksekusi perintah Telegram. Return teks balasan, atau None bila pengirim
    bukan owner / perintah tidak dikenal (abaikan)."""
    owner = str(config.TELEGRAM_OWNER_ID).strip()
    if not owner or str(sender_id).strip() != owner:
        return None

    cmd, args = parse_command(text)
    if not cmd:
        return None

    if cmd in ("help", "start"):
        return HELP_TEXT

    if cmd == "status":
        state = await kill_switch.get_state()
        triggers = await kill_switch.get_triggers()
        async with db.pool().connection() as conn:
            metrics = await kill_switch.compute_metrics(conn)
        lines = [_fmt_state(state), ""]
        lines.append(
            f"DD harian: {metrics['daily_drawdown_pct']:.2f}% "
            f"(limit {triggers.get('daily_drawdown_pct')}%)"
        )
        lines.append(
            f"DD total: {metrics['total_drawdown_pct']:.2f}% "
            f"(limit {triggers.get('total_drawdown_pct')}%, puncak "
            f"{metrics['equity_high_water_mark']:.2f})"
        )
        ea_age = metrics["ea_last_seen_age_s"]
        lines.append(f"EA terakhir terlihat: {ea_age:.0f}s lalu" if ea_age is not None
                     else "EA: belum ada kontak")
        lines.append(
            f"Posisi terbuka: {metrics['open_positions']}, "
            f"FAILED beruntun: {metrics['consecutive_failed']}"
        )
        if state["mode"] == "GLOBAL_HALT":
            lines.append("")
            lines.append("Pelepasan GLOBAL_HALT wajib checklist recovery:")
            for i, item in enumerate(kill_switch.RECOVERY_CHECKLIST, 1):
                lines.append(f"  {i}. {item}")
            lines.append("Kirim `/resume ACK` setelah checklist dipenuhi.")
        return "\n".join(lines)

    if cmd == "stop":
        state = await kill_switch.activate(
            "STOP_NEW_ORDERS", reason="perintah Telegram owner",
            source="telegram", actor=f"tg:{sender_id}",
        )
        return f"{_fmt_state(state)}\nSemua order baru ditolak."

    if cmd == "halt":
        state = await kill_switch.activate(
            "GLOBAL_HALT", reason="perintah Telegram owner",
            source="telegram", actor=f"tg:{sender_id}",
        )
        return (
            f"{_fmt_state(state)}\n"
            "Semua entry dihentikan. Pelepasan wajib checklist recovery "
            "(`/resume ACK` setelah checklist dipenuhi)."
        )

    if cmd in ("stopflatten", "flatten"):
        confirm = "confirm" in [a.lower() for a in args]
        if not confirm:
            return (
                f"*PERINGATAN SLIPPAGE*\n{kill_switch.SLIPPAGE_WARNING}\n\n"
                "Balas `/stopflatten confirm` untuk melanjutkan."
                if cmd == "stopflatten"
                else f"*PERINGATAN SLIPPAGE*\n{kill_switch.SLIPPAGE_WARNING}\n\n"
                "Balas `/flatten confirm` untuk melanjutkan."
            )
        flat = await kill_switch.flatten_positions(actor=f"tg:{sender_id}", source="telegram")
        state = await kill_switch.get_state()
        if cmd == "stopflatten":
            state = await kill_switch.activate(
                "STOP_AND_FLATTEN", reason="perintah Telegram owner (confirm)",
                source="telegram", actor=f"tg:{sender_id}",
            )
        return (
            f"{_fmt_state(state)}\n"
            f"Flatten: {len(flat)} posisi dikirim untuk ditutup "
            f"({', '.join(str(c['position_ticket']) for c in flat) or '-'})"
        )

    if cmd == "pause":
        if not args:
            return "Gunakan: /pause <nama_strategi>"
        strategy = " ".join(args)
        state = await kill_switch.pause_strategy(
            strategy, source="telegram", actor=f"tg:{sender_id}",
            reason=f"perintah Telegram owner",
        )
        paused = await kill_switch.get_paused_strategies()
        return f"{_fmt_state(state)}\nStrategi di-pause: {', '.join(paused)}"

    if cmd == "resume":
        state = await kill_switch.get_state()
        if not state["active"]:
            return "kill-switch tidak aktif."
        if state["mode"] == "GLOBAL_HALT" and not args:
            lines = ["GLOBAL_HALT aktif. Checklist recovery wajib:"]
            for i, item in enumerate(kill_switch.RECOVERY_CHECKLIST, 1):
                lines.append(f"  {i}. {item}")
            lines.append("Kirim `/resume ACK` setelah checklist dipenuhi.")
            return "\n".join(lines)
        ack = args and args[0].upper() == "ACK"
        strategy = None if ack else (args[0] if args else None)
        try:
            state = await kill_switch.release(
                checklist_ack=bool(ack), strategy=strategy,
                source="telegram", actor=f"tg:{sender_id}",
            )
        except PermissionError:
            return "GLOBAL_HALT membutuhkan ACK checklist recovery."
        return _fmt_state(state)

    # ── approve/deploy usulan self-improve (PRD v2.1 P4, garis merah §5.9) ──
    # Sudah lewat gate owner di atas (TELEGRAM_OWNER_ID), jadi semua perintah
    # di bawah ini owner-only. Keputusan dicatat append-only; deploy hanya
    # terjadi lewat self_improve.decide() yang menegaskan status APPROVED.
    if cmd in ("proposals", "approve", "reject"):
        from . import self_improve

        if cmd == "proposals":
            proposals = (await self_improve.status())["proposals"]
            if not proposals:
                return "Belum ada usulan self-improve."
            lines = ["Usulan self-improve:"]
            for p in proposals[:10]:
                lines.append(
                    f"• `{p['id']}` - {p['verdict']} - {p['status']}"
                    + (f" (by {p['reviewer']})" if p.get("reviewer") else ""))
            lines.append("Putuskan dengan /approve <id> atau /reject <id>")
            return "\n".join(lines)

        if not args:
            return f"Gunakan: /{cmd} <id_usulan> [alasan]"
        proposal_id = args[0]
        rationale = " ".join(args[1:]) or f"{cmd} via Telegram owner"
        try:
            decision = "APPROVED" if cmd == "approve" else "REJECTED"
            result = await self_improve.decide(
                proposal_id, decision, reviewer=f"tg:{sender_id}",
                rationale=rationale)
        except KeyError as exc:
            return f"Usulan tidak ditemukan: {exc}"
        except ValueError as exc:
            return f"Ditolak: {exc}"
        if decision == "REJECTED":
            return f"🚫 {proposal_id} REJECTED. Flag `enabled` tidak diubah."
        return (
            f"✅ {proposal_id} APPROVED → DEPLOYED\n"
            f"strategi `{result['strategy']}` v{result['version']} "
            f"(mode {result['mode']}) flag enabled=true.\n"
            f"Tercatat: strategy_approvals + deployment_records.")

    return None  # perintah tidak dikenal: abaikan


async def telegram_loop(stop) -> None:
    """Long-poll getUpdates. Off bila TELEGRAM_BOT_TOKEN / OWNER_ID tidak diset,
    atau bila env TELEGRAM_POLLER_OFF=1 (bot dipakai gateway; notify_owner tetap jalan)."""
    if os.environ.get("TELEGRAM_POLLER_OFF", "").strip().lower() in ("1", "true", "yes"):
        log.info("telegram poller off: TELEGRAM_POLLER_OFF diset")
        return
    token = config.TELEGRAM_BOT_TOKEN
    if not token or not config.TELEGRAM_OWNER_ID:
        log.info("telegram off: TELEGRAM_BOT_TOKEN / TELEGRAM_OWNER_ID tidak diset")
        return
    offset = 0
    log.info("telegram poller aktif (owner %s)", config.TELEGRAM_OWNER_ID)
    while not stop.is_set():
        try:
            data = await tg_api(token, "getUpdates", timeout=25, offset=offset,
                                allowed_updates=["message"])
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message") or {}
                text = msg.get("text") or ""
                chat_id = (msg.get("chat") or {}).get("id")
                sender_id = (msg.get("from") or {}).get("id")
                if not text or chat_id is None:
                    continue
                reply = await handle_command(text, chat_id, sender_id)
                if reply:
                    await send_message(token, chat_id, reply)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("telegram loop error: %s", exc)
            await asyncio.sleep(5)
        try:
            await asyncio.wait_for(stop.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass
