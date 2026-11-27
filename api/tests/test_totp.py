"""TOTP (RFC 6238) + HOTP (RFC 4226) test vectors + replay/skew rules."""
from __future__ import annotations

import base64
import time

from app import totp

# RFC 4226 test secret (ASCII "12345678901234567890")
RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()
RFC_VECTORS = [
    (0, "755224"),
    (1, "287082"),
    (2, "359152"),
    (3, "969429"),
    (4, "338314"),
    (5, "254676"),
    (6, "287922"),
    (7, "162583"),
    (8, "399871"),
    (9, "520489"),
]


def test_hotp_rfc4226_vectors():
    for counter, expected in RFC_VECTORS:
        assert totp.hotp(RFC_SECRET, counter) == expected, f"counter {counter}"


def test_totp_is_hotp_of_time_step():
    # TOTP = HOTP dengan counter = floor(time / 30)
    ts = 59  # RFC 6238 sample time T0
    assert totp.totp_at(RFC_SECRET, ts) == totp.hotp(RFC_SECRET, 1)
    assert totp.current_counter(ts) == 1


def test_verify_accepts_current_code():
    code = totp.totp_at(RFC_SECRET, time.time())
    assert totp.verify(RFC_SECRET, code) is not None


def test_verify_accepts_skew_one_step():
    now = time.time()
    code_prev = totp.totp_at(RFC_SECRET, now - 30)
    code_next = totp.totp_at(RFC_SECRET, now + 30)
    assert totp.verify(RFC_SECRET, code_prev) is not None
    assert totp.verify(RFC_SECRET, code_next) is not None


def test_verify_rejects_wrong_and_malformed():
    fixed = 1234567890  # detik; counter deterministik 41152263
    assert totp.verify(RFC_SECRET, "000000", now_s=fixed) is None
    assert totp.verify(RFC_SECRET, "12345", now_s=fixed) is None   # salah panjang
    assert totp.verify(RFC_SECRET, "abcdef", now_s=fixed) is None  # bukan digit
    assert totp.verify(RFC_SECRET, "", now_s=fixed) is None


def test_verify_rejects_reused_counter():
    fixed = 1234567890
    code = totp.totp_at(RFC_SECRET, fixed)
    counter = totp.verify(RFC_SECRET, code, now_s=fixed)
    assert counter is not None
    # kode yang sama tidak bisa dipakai lagi (anti-replay)
    assert totp.verify(RFC_SECRET, code, last_counter=counter, now_s=fixed) is None
    # counter lebih lama juga ditolak
    assert totp.verify(RFC_SECRET, totp.hotp(RFC_SECRET, counter - 1),
                       last_counter=counter, now_s=fixed) is None


def test_generate_secret_unique_and_b32():
    secrets_ = {totp.generate_secret() for _ in range(20)}
    assert len(secrets_) == 20
    for s in secrets_:
        base64.b32decode(s)  # tidak raise
        assert len(s) == 32  # 160-bit -> 32 char base32


def test_provisioning_uri_shape():
    uri = totp.provisioning_uri("ABC234DEF", "owner@example.com")
    assert uri.startswith("otpauth://totp/Fund2:owner@example.com")
    assert "secret=ABC234DEF" in uri
    assert "issuer=Fund2" in uri
