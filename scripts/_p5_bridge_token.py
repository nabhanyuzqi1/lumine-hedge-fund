#!/usr/bin/env python3
"""Rotasi bridge_token untuk mengunci EA real selama pengukuran latensi P5.

Perintah:
  rotate  -> simpan token lama ke scripts/.bridge_token_backup (mode 600),
             ganti dengan token acak baru di settings.
  restore -> kembalikan token lama dari file backup.
  test    -> uji token lama (harus 401) dan baru (harus 200) ke /bridge/poll.

Nilai token TIDAK PERNAH dicetak; hanya panjang dan status HTTP.
"""
import json
import re
import secrets
import stat
import sys
import urllib.request
import urllib.error

sys.path.insert(0, "/home/tekka/fund2/api")

ENV_PATH = "/home/tekka/fund2/api/.env"
BACKUP_PATH = "/home/tekka/fund2/scripts/.bridge_token_backup"
API = "http://127.0.0.1:3110"

env = {}
for line in open(ENV_PATH):
    m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
    if m:
        env[m.group(1)] = m.group(2)

import psycopg


def get_token(cur):
    cur.execute("SELECT value FROM settings WHERE key='bridge_token'")
    row = cur.fetchone()
    return row[0] if row else None


def set_token(cur, value):
    # kolom settings.value bertipe JSON -> simpan sebagai string JSON
    cur.execute("UPDATE settings SET value=%s WHERE key='bridge_token'",
                (json.dumps(value),))


def poll_status(token):
    req = urllib.request.Request(
        f"{API}/bridge/poll?timeout_s=0",
        headers={"Authorization": f"Bearer {token}"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return f"ERR {type(e).__name__}"


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    conn = psycopg.connect(env["DATABASE_URL"], autocommit=True)
    cur = conn.cursor()

    if cmd == "rotate":
        old = get_token(cur)
        assert old, "bridge_token kosong"
        with open(BACKUP_PATH, "w") as f:
            f.write(old)
        os_chmod = stat.S_IRUSR | stat.S_IWUSR
        import os
        os.chmod(BACKUP_PATH, os_chmod)
        new = secrets.token_urlsafe(32)
        set_token(cur, new)
        print(f"rotate OK: token lama disimpan (panjang {len(old)}), "
              f"token baru dipasang (panjang {len(new)})")
        print(f"test token baru -> /bridge/poll: {poll_status(new)}")
        print(f"test token lama -> /bridge/poll: {poll_status(old)} (harus 401)")
    elif cmd == "restore":
        old = open(BACKUP_PATH).read().strip()
        set_token(cur, old)
        print(f"restore OK: token lama dipasang kembali (panjang {len(old)})")
        print(f"test token lama -> /bridge/poll: {poll_status(old)} (harus 200)")
    elif cmd == "test":
        cur_tok = get_token(cur)
        print(f"test token aktif -> /bridge/poll: {poll_status(cur_tok)}")
    else:
        print("perintah: rotate | restore | test")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
