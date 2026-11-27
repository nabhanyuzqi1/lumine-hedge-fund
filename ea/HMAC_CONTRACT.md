# Kontrak Auth HMAC-SHA256 — EA v0 ↔ Bridge (PRD v2.1 §7)

Referensi implementasi: `ea/LumineEA.mq5` (`SignHeaders`) dan
`scripts/dummy_bridge.py` (`BridgeState.check_hmac`).

## Header (setiap request /bridge/*)

| Header | Isi |
| --- | --- |
| `X-Fund2-Timestamp` | unix epoch detik (string); toleransi server ±5 detik |
| `X-Fund2-Nonce` | hex acak 8-64 char; unik, dipakai sekali (replay cache TTL 11 dtk) |
| `X-Fund2-Signature` | hex lowercase HMAC-SHA256(secret, string_to_sign) |

## String to sign (UTF-8)

```
ts \n nonce \n METHOD \n path-with-query \n sha256_hex(body)
```

- `METHOD`: `POST` / `GET` (uppercase).
- `path-with-query`: path persis seperti dikirim, contoh `/bridge/tick`,
  `/bridge/poll?timeout_s=0` (query ikut ditandatangani).
- `body`: byte body mentah; GET tanpa body → `sha256_hex("")`
  (`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`).

## Secret

- Server: env `FUND2_HMAC_SECRET` (wajib, min 16 char).
- EA: file di sandbox `MQL5/Files` (input `InpSecretFile`, default
  `fund2_hmac.secret`), diisi out-of-band dari nilai env server —
  sengaja bukan dari repo dan bukan input chart.
- Secret > 64 byte di-hash SHA256 dulu (standar HMAC, RFC 2104/4231).

## Verifikasi server (urutan)

1. Header lengkap? → else 401 `missing X-Fund2-* headers`
2. Timestamp integer & |now−ts| ≤ 5 → else 401 `timestamp outside +-5s tolerance`
3. Nonce hex & belum pernah dipakai (dalam window) → else 401 `nonce replayed`
4. Signature cocok (constant-time compare) → else 401 `bad signature`

Replay cache dibersihkan lazy saat > 4096 entri; TTL nonce = 2 × toleransi + 1.

## Catatan P1a

`api/app/bridge.py` saat ini masih Bearer token (kontrak lama). Saat P1a
mengadopsi kontrak ini, pakai `check_hmac` di `dummy_bridge.py` sebagai
referensi dan `ea/test_ea_v0.py` sebagai test vektor (RFC 4231 termasuk).

## Batasan v0 (dummy)

- Tidak ada TLS (loopback saja), tidak ada DB, tidak ada order.
- Heartbeat & tick dicatat ke JSONL di `data/ea_v0/` + counter `/_stats`.
