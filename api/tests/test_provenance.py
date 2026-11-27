"""PRD v2.2 §8.2: provenance (data + kode) dan hash konfigurasi."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from paper.provenance import (
    canonical_json,
    code_hash,
    code_provenance,
    config_hash,
    data_provenance,
    download_dates,
    module_file_hashes,
)

UTC = timezone.utc


def _candles():
    return [
        {"ts": datetime(2026, 3, 2, h, tzinfo=UTC), "open": 2000.0, "high": 2001.0,
         "low": 1999.0, "close": 2000.5, "volume": 100.0}
        for h in range(5)
    ]


def test_canonical_json_deterministic():
    a = {"b": 1, "a": [1, 2, {"z": None, "y": True}]}
    b = {"a": [1, 2, {"y": True, "z": None}], "b": 1}
    assert canonical_json(a) == canonical_json(b)
    assert canonical_json(a) == canonical_json(a)


def test_config_hash_stable_and_sensitive():
    c1 = {"seed": 1, "grid": {"a": [1, 2]}}
    c2 = {"grid": {"a": [1, 2]}, "seed": 1}
    c3 = {"seed": 2, "grid": {"a": [1, 2]}}
    assert config_hash(c1) == config_hash(c2)
    assert config_hash(c1) != config_hash(c3)


def test_data_provenance_fields():
    prov = data_provenance(_candles(), symbol="XAUUSD", tf="H1", raw_dir=None)
    assert prov["symbol"] == "XAUUSD"
    assert prov["timeframe"] == "H1"
    assert prov["timezone"] == "UTC"
    assert prov["bars"] == 5
    assert prov["period_start"] == "2026-03-02T00:00:00+00:00"
    assert prov["period_end"] == "2026-03-02T04:00:00+00:00"
    assert prov["checksum"].startswith("sha256:")
    assert "ts_semantics" in prov


def test_data_provenance_checksum_changes_with_data():
    c1 = _candles()
    c2 = _candles()
    c2[2]["close"] = 2001.5  # satu bar berubah
    p1 = data_provenance(c1, symbol="XAUUSD", tf="H1", raw_dir=None)
    p2 = data_provenance(c2, symbol="XAUUSD", tf="H1", raw_dir=None)
    assert p1["checksum"] != p2["checksum"]


def test_data_provenance_same_data_same_checksum():
    p1 = data_provenance(_candles(), symbol="XAUUSD", tf="H1", raw_dir=None)
    p2 = data_provenance(_candles(), symbol="XAUUSD", tf="H1", raw_dir=None)
    assert p1["checksum"] == p2["checksum"]


def test_code_provenance_shape():
    prov = code_provenance()
    assert prov["git_commit"] is not None and len(prov["git_commit"]) == 40
    assert isinstance(prov["git_dirty"], bool)
    assert prov["code_hash"].startswith("sha256:")
    assert "paper/backtest.py" in prov["module_hashes"]
    assert "python_version" in prov
    assert "dependencies" in prov and prov["dependencies"]


def test_code_hash_changes_when_module_content_changes(tmp_path):
    api = tmp_path / "api"
    (api / "paper").mkdir(parents=True)
    (api / "paper" / "backtest.py").write_text("x = 1\n")
    h1 = code_hash(api)
    (api / "paper" / "backtest.py").write_text("x = 2\n")
    h2 = code_hash(api)
    assert h1 != h2


def test_module_file_hashes_deterministic():
    assert module_file_hashes() == module_file_hashes()


def test_download_dates_missing_dir():
    assert download_dates(None) is None
    assert download_dates(Path("/nonexistent/path/xyz")) is None
