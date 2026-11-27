#!/usr/bin/env python3
"""One-shot: tambahkan 3 URL whitelist MT5 via UI automation (metode proven
mt5-whitelist-watch.py). Tidak menyentuh file config MT5 sama sekali."""
import os, re, subprocess, time, glob

MT5_DIR = os.path.expanduser("~/wine-mt5/drive_c/Program Files/MetaTrader 5")
LOG_DIR = os.path.join(MT5_DIR, "MQL5", "logs")
URLS = [
    "https://fund.lumine.biz.id",
    "http://fund.lumine.biz.id",
    "http://127.0.0.1:3110",
]

def log(msg): print(time.strftime("%H:%M:%S"), msg, flush=True)

def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""

def read_ea_log():
    files = sorted(glob.glob(os.path.join(LOG_DIR, "*.log")))
    if not files: return ""
    raw = open(files[-1], "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"): raw = raw[2:]
    return raw.decode("utf-16-le", errors="replace")

def mt5_window():
    for pat in ("HF.?Markets", "terminal64\\.exe$"):
        out = run(f"xdotool search --onlyvisible --name '{pat}' 2>/dev/null | head -1")
        if out: return int(out.splitlines()[0])
    return None

def ensure_wm():
    if run("pgrep -x xfwm4"): return True
    log("xfwm4 mati — nyalakan ulang")
    subprocess.Popen(["xfwm4", "--replace"], env={**os.environ, "DISPLAY": ":99"},
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(8)
    return bool(run("pgrep -x xfwm4"))

def type_chars(text):
    keysym = {".": "period", ":": "colon", "/": "slash"}
    for ch in text:
        run(f"xdotool key {keysym.get(ch, ch)}")
        time.sleep(0.2)

def add_url_via_ui(url):
    if not ensure_wm(): return False
    wid = mt5_window()
    if not wid:
        log("window MT5 tidak ditemukan"); return False
    run(f"xdotool windowactivate {wid}"); time.sleep(1.0)
    run("xdotool key --clearmodifiers ctrl+o"); time.sleep(3.0)
    did = 0
    for _ in range(4):
        dout = run("xdotool search --onlyvisible --name '^Options$' 2>/dev/null | head -1")
        if dout: did = int(dout.splitlines()[0]); break
        run(f"xdotool windowactivate {wid}"); time.sleep(1.0)
        run("xdotool key --clearmodifiers ctrl+o"); time.sleep(4.0)
    if not did:
        log("dialog Options tidak muncul"); run("xdotool key Escape"); return False
    out = run(f"xdotool getwindowgeometry {did}")
    m = re.search(r"Position:\s*(-?\d+),(-?\d+)", out)
    if not m:
        run("xdotool key Escape"); return False
    dx, dy = int(m.group(1)), int(m.group(2))
    run(f"xdotool windowactivate {did}"); run(f"xdotool windowfocus {did}"); time.sleep(1.0)
    run(f"xdotool mousemove {dx + 158} {dy + 16} click 1"); time.sleep(1.2)   # tab Experts
    run(f"xdotool mousemove {dx + 312} {dy + 207} click --repeat 2 --delay 80 1"); time.sleep(1.0)  # baris add
    type_chars(url); time.sleep(0.5)
    run("xdotool key --clearmodifiers Return"); time.sleep(1.0)
    run(f"xdotool mousemove {dx + 407} {dy + 341} click 1"); time.sleep(2.0)  # OK
    closed = not run("xdotool search --onlyvisible --name '^Options$' 2>/dev/null | head -1")
    log(f"add {url}: dialog {'tertutup' if closed else 'MASIH TERBUKA'}")
    if not closed: run("xdotool key Escape")
    return closed

if __name__ == "__main__":
    ok = 0
    for u in URLS:
        if add_url_via_ui(u): ok += 1
        time.sleep(3)
    log(f"selesai: {ok}/{len(URLS)} URL diketik")
    # verifikasi: tunggu RECOVERED di log EA (v1 EA polling fund.lumine.biz.id)
    for i in range(20):
        time.sleep(6)
        txt = read_ea_log()
        lines = [l for l in txt.splitlines() if "proxy" in l]
        tail = lines[-1] if lines else ""
        if "RECOVERED" in tail:
            log("RECOVERED terkonfirmasi di log EA"); break
        log(f"tunggu RECOVERED... ({i+1}) tail: {tail[-80:]}")
