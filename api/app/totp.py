"""TOTP (RFC 6238) untuk 2FA langkah-sensitive: SHA1, 6 digit, 30 detik.

Implementasi stdlib murni (hmac/hashlib/struct) supaya tidak menambah
dependency kripto baru; kebenarannya diikat vektor uji RFC 4226/6238 di
api/tests/test_totp.py.

Aturan verifikasi (PRD v2.2 §18):
- Skew clock +-1 langkah (30 detik) diterima.
- Counter yang sudah dipakai TIDAK boleh dipakai lagi (anti-replay):
  users.totp_last_counter menyimpan counter tertinggi yang pernah valid.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time

STEP_S = 30
DIGITS = 6


def generate_secret() -> str:
    """Secret base32 160-bit (20 byte) untuk enrolment."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def hotp(secret: str, counter: int, digits: int = DIGITS) -> str:
    """RFC 4226 HOTP: HMAC-SHA1 + dynamic truncation."""
    key = base64.b32decode(secret, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (
        ((digest[offset] & 0x7F) << 24)
        | (digest[offset + 1] << 16)
        | (digest[offset + 2] << 8)
        | digest[offset + 3]
    )
    return str(code % (10**digits)).zfill(digits)


def totp_at(secret: str, at_s: float | int | None = None) -> str:
    """Kode TOTP untuk waktu `at_s` (epoch detik; default sekarang)."""
    if at_s is None:
        at_s = time.time()
    return hotp(secret, int(at_s) // STEP_S)


def current_counter(at_s: float | int | None = None) -> int:
    if at_s is None:
        at_s = time.time()
    return int(at_s) // STEP_S


def verify(
    secret: str,
    code: str,
    last_counter: int = -1,
    now_s: float | int | None = None,
    skew: int = 1,
) -> int | None:
    """Verifikasi kode TOTP. Return counter yang valid, atau None.

    - Menerima skew +-`skew` langkah (default +-30 detik).
    - Menolak counter <= `last_counter` (kode sudah pernah dipakai).
    """
    if not code or not code.isdigit() or len(code) != DIGITS:
        return None
    now_counter = current_counter(now_s)
    for counter in range(now_counter - skew, now_counter + skew + 1):
        if counter <= last_counter:
            continue
        if hmac.compare_digest(hotp(secret, counter), code):
            return counter
    return None


def provisioning_uri(secret: str, account: str, issuer: str = "Fund2") -> str:
    """URI otpauth untuk QR code authenticator app."""
    label = f"{issuer}:{account}"
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={issuer}"
        f"&algorithm=SHA1&digits={DIGITS}&period={STEP_S}"
    )
