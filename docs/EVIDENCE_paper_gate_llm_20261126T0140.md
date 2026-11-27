# Evaluasi Gerbang Paper — llm

Periode: awal .. sekarang
Ekuitas awal: 10000.0; komisi 7.0 USD/lot round-turn.

## Verdict gerbang

**DATA_BELUM_CUKUP**

| Kriteria | Status | Detail |
| --- | --- | --- |
| Hari kerja >= 20 | FAIL | 3 hari kerja (min 20) |
| Trade >= 100 | FAIL | 30 trade closed (min 100) |
| PF >= 1.3 setelah biaya | FAIL | PF 1.0911674434466294 (min 1.3) setelah biaya |
| Max DD <= 5% | PASS | max DD 2.45% (maks 5.0%) |

## Metrik

- Trades: 30; net profit: 32.08; ekuitas akhir: 10032.08
- Winrate: 0.3; profit factor: 1.0911674434466294
- Max drawdown: 245.17 USD (2.45%)
- Hari kerja teramati: 3

## Per simbol

| Simbol | Trades | Net | PF |
| --- | --- | --- | --- |
| XAUUSD | 30 | 32.08 | 1.0911674434466294 |

## Per sesi (UTC)

| Sesi | Trades | Net | Winrate | PF |
| --- | --- | --- | --- | --- |
| asia | 11 | -70.25 | 0.2727 | 0.5529748647788737 |
| london | 6 | -143.18 | 0.0 | 0.0 |
| london_newyork | 2 | 145.7 | 1.0 | inf |
| newyork | 11 | 99.81 | 0.3636 | 2.936178467507275 |

## Keputusan valid vs hold

- Total 111: valid 31 (ratio 0.2793), hold 37, invalid 43

## Sumber profit (data quality)

- reported: 22; computed: 8 (EA lapor 0, dihitung dari harga); unknown: 0
