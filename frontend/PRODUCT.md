# PRODUCT.md — Lumine Fund v2 ("Fund Core")

Sumber kebenaran: ~/fund2/PRD.md. UI membangun bagian 3.6 PRD.

## Produk
Platform trading XAUUSD milik sendiri: cepat, terlacak, self-improving.
"Quant desk yang self-improving, bukan chatbot yang main uang."

## Audiens
Owner-operator (satu orang) yang menjalankan desk-nya sendiri: memantau pasar,
menaruh order terlindungi, mengaudit setiap keputusan, mengelola strategi.
Memakai desktop di meja kerja dan ponsel untuk cek posisi.

## Pekerjaan yang dilayani UI (mode Operate)
1. Melihat harga XAUUSD live, spread, dan sesi likuiditas (Asia/London/NY).
2. Menaruh order market dengan SL/TP wajib, konfirmasi sebelum kirim,
   hasil tampil realtime.
3. Membaca buku besar event log per order (RECEIVED → RISK_PASS → SENT → FILLED).
4. Mengelola strategi: daftar, hasil backtest, mode paper/live, kill-switch.

## Batasan
- Satu instrumen: XAUUSD, satu broker MT5.
- Target eksekusi <300 ms; UI menampilkan latensi per order dari event log.
- Live trading tidak aktif sebelum P5; UI mendukung mode paper.
- LLM tidak pernah pegang tombol order.

## Platform
Web (desktop + mobile). Bahasa UI: Indonesia.
