#!/usr/bin/env python3
"""Watcher kanban fund: kirim notifikasi Telegram ke owner setiap ada update board.

Update yang dilaporkan (per siklus poll, digabung 1 pesan):
  - perubahan status kartu (dengan judul + assignee)
  - kartu baru
  - komentar baru di kartu
  - kartu diarsipkan/dihapus

Anti-spam bawaan: perubahan digabung jadi SATU pesan per siklus; perubahan
yang gagal dikirim disimpan dan digabung di siklus berikutnya. Poll 30 detik.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

BOARD_DB = Path("/home/tekka/.hermes/kanban/boards/deskrpg-da0b82b192024c709c4e12675baf3afe/kanban.db")
ENV_ALERTS = Path("/home/tekka/fund2/api/.env.alerts")
STATE_FILE = Path("/home/tekka/fund2/data/kanban_watch_state.json")
POLL_S = 30
STATE_VERSION = 1

STATUS_ICON = {
    "todo": "📥", "ready": "🟡", "running": "▶️", "review": "🔍",
    "done": "✅", "blocked": "⛔", "archived": "🗂️", "needs_input": "❓",
}


def load_env(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def tg_send(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id, "text": text, "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode())
        if not body.get("ok"):
            raise RuntimeError(f"telegram ok=false: {body}")


def read_board_fixed() -> tuple[dict, dict]:
    """Return (tasks, comments) terpisah supaya hitungan komentar akurat."""
    conn = sqlite3.connect(f"file:{BOARD_DB}?mode=ro", uri=True, timeout=10)
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        tasks = {
            row[0]: {"title": row[1], "status": row[2], "assignee": row[3]}
            for row in conn.execute(
                "SELECT id, title, status, assignee FROM tasks")
        }
        comments = {row[0]: row[1] for row in conn.execute(
            "SELECT task_id, COUNT(*) FROM task_comments GROUP BY task_id")}
    finally:
        conn.close()
    return tasks, comments


def diff_state(old: tuple[dict, dict], new: tuple[dict, dict]) -> list[str]:
    old_tasks, old_comments = old
    new_tasks, new_comments = new
    lines: list[str] = []
    for cid, t in new_tasks.items():
        if cid not in old_tasks:
            lines.append(f"🆕 {cid} {t['title'][:60]} (baru, {t['status']})")
            continue
        o = old_tasks[cid]
        if o["status"] != t["status"]:
            icon = STATUS_ICON.get(t["status"], "•")
            asg = f" ({t['assignee']})" if t["assignee"] else ""
            lines.append(f"{icon} {cid} {t['title'][:55]}: {o['status']} → {t['status']}{asg}")
        elif o["title"] != t["title"]:
            lines.append(f"✏️ {cid} judul berubah: {t['title'][:60]}")
    for cid in old_tasks:
        if cid not in new_tasks:
            lines.append(f"🗂️ {cid} diarsipkan/dihapus")
    for cid, n in new_comments.items():
        old_n = old_comments.get(cid, 0)
        if n > old_n and cid in new_tasks:
            lines.append(f"💬 {cid} {new_tasks[cid]['title'][:50]}: +{n - old_n} komentar")
    return lines


def main() -> int:
    env = load_env(ENV_ALERTS)
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_OWNER_ID", "")
    if not token or not chat_id:
        print("token/chat belum dikonfigurasi di .env.alerts", flush=True)
        return 1

    if STATE_FILE.exists():
        try:
            old = json.loads(STATE_FILE.read_text())
            old = (old["tasks"], old["comments"])
        except Exception:
            old = None
    else:
        old = None

    pending: list[str] = []
    while True:
        try:
            new = read_board_fixed()
            if old is None:
                print(f"baseline: {len(new[0])} kartu, tanpa kirim", flush=True)
            else:
                changes = diff_state(old, new)
                if changes:
                    pending.extend(changes)
            old = new
            if pending:
                stamp = time.strftime("%d/%m %H:%M")
                head = f"📋 *Kanban fund* {stamp}"
                body = "\n".join(pending[:15])
                if len(pending) > 15:
                    body += f"\n… dan {len(pending) - 15} perubahan lainnya"
                try:
                    tg_send(token, chat_id, f"{head}\n{body}")
                    print(f"kirim {len(pending)} perubahan", flush=True)
                    pending = []
                except Exception as exc:
                    print(f"kirim gagal (dicoba lagi siklus depan): {exc}", flush=True)
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps({
                "version": STATE_VERSION,
                "tasks": new[0],
                "comments": new[1],
            }))
        except Exception as exc:
            print(f"poll error: {exc}", flush=True)
        time.sleep(POLL_S)
    return 0


if __name__ == "__main__":
    sys.exit(main())
