# Laporan Latensi Fund2 (T0..T4)

- Run: semua run
- Periode (t0_wall): awal .. sekarang
- Sumber: order_events.payload->'latency' (clock mono_us)
- Sampel order: 15 (lengkap T0..T4: 10, parsial: 5)
- Status terminal: FILLED=15

| Segmen | n | p50 | p95 | p99 | min | max | mean |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T0-T1 pickup EA (API -> EA menerima command) | 10 | 212.4 | 271.1 | 272.9 | 74.0 | 273.3 | 194.9 |
| T1-T2 EA pre-send (EA persiapan sebelum OrderSend) | 10 | 2.1 | 2.8 | 3.2 | 2.1 | 3.3 | 2.2 |
| T2-T3 broker OrderSend (latensi broker (dilaporkan terpisah)) | 10 | 137.0 | 211.4 | 213.0 | 111.8 | 213.4 | 156.2 |
| T3-T4 konfirmasi DB (result POST -> commit FILLED) | 10 | 9.2 | 20.9 | 25.1 | 7.1 | 26.1 | 11.7 |
| T0-T2 SLO internal (SLO p95<300ms p99<500ms) | 10 | 214.5 | 273.2 | 274.9 | 76.1 | 275.4 | 197.2 |
| T0-T4 total (end to end (dilaporkan terpisah)) | 15 | 406.7 | 4840.2 | 5481.3 | 208.1 | 5641.6 | 1371.4 |

SLO T0-T2 (PRD bagian 6): p95 273.2 ms < 300 ms -> PASS; p99 274.9 ms < 500 ms -> PASS
Gate sampel: 15/200 order (BELUM memenuhi syarat >= 200 order untuk keputusan gate).

Satuan milidetik. T2-T3 (broker) dan T0-T4 (total) dilaporkan terpisah tanpa SLO keras (PRD bagian 6).
