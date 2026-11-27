"""Pengawas harian drift guardrail runtime (kartu t_097ef2bb).

Menguji `scripts/check_guardrail_runtime.py` tanpa menyentuh DB live:
  * format + escape Markdown Telegram (pelajaran 23 Nov 2026: underscore di
    luar backtick -> 400 "can't parse entities" -> alert tak terkirim),
  * exit code (0 bersih, 2 drift/open, 1 gate gagal),
  * log JSON harian `guardrail-<tanggal>.json`,
  * tidak ada jalur tulis ke `settings` (read-only).
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
from datetime import datetime, timezone

import pytest

API_DIR = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = API_DIR.parent / "scripts" / "check_guardrail_runtime.py"


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


crw = _load("check_guardrail_runtime", SCRIPT)
_md = _load("alerts_resilience_mod", API_DIR / "tests" / "test_alerts_resilience.py")
md_entities_balanced = _md.md_entities_balanced

NOW = datetime(2026, 11, 26, 5, 10, 0, tzinfo=timezone.utc)

DRIFT_REPORT = {
    "guardrails_pass": False,
    "guardrail_drift": [
        {"key": "max_volume", "expected": 0.1, "actual": 1.0},
        {"key": "ea_offline_seconds", "expected": 6.0, "actual": 60.0},
        {"key": "max_daily_drawdown", "expected": 292.02, "actual": 300.0},
    ],
    "guardrail_open": ["max_feed_age_s: portfolio_risk.max_feed_age_s tidak ditemukan"],
    "settings_actual": {"max_volume": 1.0, "ea_offline_seconds": 60.0},
    "kill_switch_active": False,
    "halted": False,
}

PASS_REPORT = {
    "guardrails_pass": True,
    "guardrail_drift": [],
    "guardrail_open": [],
    "settings_actual": {"max_volume": 0.1},
    "kill_switch_active": False,
    "halted": False,
}


# ------------------------------------------------------------------ formatting

def test_fmt_val():
    assert crw.fmt_val(6.0) == "6"
    assert crw.fmt_val(0.1) == "0.1"
    assert crw.fmt_val(292.02) == "292.02"
    assert crw.fmt_val(None) == "tidak ada"
    assert crw.fmt_val("6.0") == "6.0"


def test_masked_db_hides_credentials():
    label = crw.masked_db("postgresql://fund2:secretpass@127.0.0.1:5433/fund2")
    assert label == "fund2@127.0.0.1:5433"
    assert "secretpass" not in label


def test_alert_mentions_key_value_and_reference():
    msg = crw.build_alert_message(DRIFT_REPORT, db_label="fund2@127.0.0.1:5433",
                                  now=NOW)
    assert "max\\_volume" in msg
    assert "aktif 1, §I 0.1" in msg
    assert "ea\\_offline\\_seconds" in msg
    assert "KEPUTUSAN\\_OWNER.md" in msg
    assert "§I.4" in msg
    assert "PUT /admin/risk-settings" in msg
    assert "sesi 2FA" in msg


def test_alert_markdown_entities_balanced():
    """Tidak boleh ada `_` telanjang di luar backtick (400 can't parse entities)."""
    msg = crw.build_alert_message(DRIFT_REPORT, db_label="fund2_guardrail_test@h:5433",
                                  now=NOW)
    ok, why = md_entities_balanced(msg)
    assert ok, why
    outside = _strip_code_spans(msg)
    unescaped = outside.replace("\\_", "")
    assert "_" not in unescaped, f"underscore tak ter-escape di luar backtick: {outside}"


def test_alert_open_items_escaped():
    msg = crw.build_alert_message(DRIFT_REPORT, db_label="db", now=NOW)
    assert "max\\_feed\\_age\\_s: portfolio\\_risk.max\\_feed\\_age\\_s" in msg


def test_drill_label_prefixed_and_still_balanced():
    msg = crw.build_alert_message(DRIFT_REPORT, db_label="fund2_test_x@127.0.0.1:5433",
                                  now=NOW, label="DRILL")
    assert msg.splitlines()[0].startswith("🚨 DRILL")
    assert md_entities_balanced(msg)[0]


def test_guardrail_id_label_present():
    msg = crw.build_alert_message(DRIFT_REPORT, db_label="db", now=NOW)
    assert "(A3)" in msg
    assert "(A12)" in msg


def _strip_code_spans(text: str) -> str:
    out, inside = [], False
    for ch in text:
        if ch == "`":
            inside = not inside
            continue
        if not inside:
            out.append(ch)
    return "".join(out)


# ------------------------------------------------------------------- lifecycle

@pytest.fixture()
def workdir(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALERTS_OFF", "1")
    return tmp_path


def _patch_gate(monkeypatch, report=None, error: Exception | None = None):
    def fake_check_db():
        if error is not None:
            raise error
        return report

    monkeypatch.setattr(crw.vrp, "check_db", fake_check_db)


def _capture_alerts(monkeypatch):
    sent: list[str] = []

    async def fake_notify(text: str) -> bool:
        sent.append(text)
        return True

    monkeypatch.setattr(crw, "notify_owner", fake_notify)
    return sent


def test_pass_writes_log_and_no_alert(monkeypatch, workdir):
    _patch_gate(monkeypatch, PASS_REPORT)
    sent = _capture_alerts(monkeypatch)

    rc = crw.run(None, alert_enabled=True, label=None, out_dir=workdir)

    assert rc == crw.RC_OK
    assert sent == []
    files = sorted(workdir.glob("guardrail-*.json"))
    assert len(files) == 1
    payload = __import__("json").loads(files[0].read_text())
    assert payload["ok"] is True
    assert payload["exit_code"] == 0
    assert payload["mode"] == "live"
    assert payload["drift_count"] == 0
    assert payload["alert"] == {"attempted": False, "sent": False, "error": None}


def test_drift_alert_once_and_rc2(monkeypatch, workdir):
    _patch_gate(monkeypatch, DRIFT_REPORT)
    sent = _capture_alerts(monkeypatch)

    rc = crw.run(None, alert_enabled=True, label="DRILL", out_dir=workdir)

    assert rc == crw.RC_DRIFT
    assert len(sent) == 1
    assert "max\\_volume" in sent[0]
    payload = __import__("json").loads(next(workdir.glob("guardrail-*.json")).read_text())
    assert payload["ok"] is False
    assert payload["mode"] == "drill"
    assert payload["label"] == "DRILL"
    assert payload["alert"]["sent"] is True
    assert payload["drift_count"] == 3
    assert payload["open_count"] == 1


def test_no_alert_flag_keeps_log(monkeypatch, workdir):
    _patch_gate(monkeypatch, DRIFT_REPORT)
    sent = _capture_alerts(monkeypatch)

    rc = crw.run(None, alert_enabled=False, label=None, out_dir=workdir)

    assert rc == crw.RC_DRIFT
    assert sent == []
    payload = __import__("json").loads(next(workdir.glob("guardrail-*.json")).read_text())
    assert payload["alert"]["attempted"] is False


def test_gate_error_rc1_and_alert(monkeypatch, workdir):
    _patch_gate(monkeypatch, error=RuntimeError("connection refused"))
    sent = _capture_alerts(monkeypatch)

    rc = crw.run(None, alert_enabled=True, label=None, out_dir=workdir)

    assert rc == crw.RC_ERROR
    assert len(sent) == 1
    assert "GAGAL DIJALANKAN" in sent[0]
    payload = __import__("json").loads(next(workdir.glob("guardrail-*.json")).read_text())
    assert payload["ok"] is False
    assert "connection refused" in payload["error"]
    assert md_entities_balanced(sent[0])[0]


def test_db_url_override_sets_env(monkeypatch, workdir):
    _patch_gate(monkeypatch, PASS_REPORT)
    _capture_alerts(monkeypatch)
    url = "postgresql://fund2:x@127.0.0.1:5433/fund2_test_drill"

    crw.run(url, alert_enabled=False, label=None, out_dir=workdir)

    payload = __import__("json").loads(next(workdir.glob("guardrail-*.json")).read_text())
    assert payload["db"] == "fund2_test_drill@127.0.0.1:5433"
    assert "x@127" not in payload["db"]


def test_log_is_atomic_no_tmp_left(monkeypatch, workdir):
    _patch_gate(monkeypatch, PASS_REPORT)
    _capture_alerts(monkeypatch)
    crw.run(None, alert_enabled=False, label=None, out_dir=workdir)
    assert list(workdir.glob("*.tmp")) == []


def test_script_is_read_only():
    """Regresi: skrip tidak boleh punya jalur tulis ke `settings`/DB."""
    src = SCRIPT.read_text().lower()
    for forbidden in ("insert into", "update settings", "delete from", "commit()",
                      "kill_switch_triggers =", "set-setting"):
        assert forbidden not in src, f"jalur tulis terlarang ditemukan: {forbidden}"
