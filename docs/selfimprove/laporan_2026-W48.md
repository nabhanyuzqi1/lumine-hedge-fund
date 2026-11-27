*LAPORAN MINGGUAN SELF-IMPROVE 2026-W48*

Kill-switch: STOP\_NEW\_ORDERS
Order 7h: 21 ({"FAILED": 16, "FILLED": 5}) | event: 102
Paper runner: balance 10000.00
Paper runner\_mean\_reversion: balance 10000.00
Paper runner\_btc\_range\_breakout: balance 10000.00
Anomali 7h: tidak ada

*Walk-forward terakhir (window uji terpilih)*
- london\_breakout XAUUSD M5: net -353.46 USD, 9 window, 133 trade, PF rata2 0.957
- mean\_reversion XAUUSD M5: net -347.24 USD, 6 window, 66 trade, PF rata2 0.524
- ml\_gbm XAUUSD M5: net 256.50 USD, 18 window, 51 trade, PF rata2 2.311

*Usulan perbaikan (backtest otomatis)*
[-] w47-p1-lb-minsl5: London Breakout M5 v1.1: floor jarak SL 5.0 USD
  verdict: GAGAL | status: PROPOSED
  net -587.60 USD, PF 0.86, trade 134, DD 0.06
  gagal kriteria: `profit\_factor\_gt`, `expectancy\_usd\_gt`, `net\_profit\_usd\_gt`, `max\_windows\_pf\_below\_1\_ratio`
[-] w47-p2-mr-numstd3: Mean Reversion M5 v1.1: band lebar num\_std 3.0
  verdict: GAGAL | status: PROPOSED
  net -347.24 USD, PF 0.81, trade 66, DD 0.06
  gagal kriteria: `profit\_factor\_gt`, `expectancy\_usd\_gt`, `net\_profit\_usd\_gt`
[+] w47-p3-mlgbm-paper: ML LightGBM triple-barrier (ml\_gbm) v1.0.0: registrasi paper
  verdict: LULUS | status: PROPOSED
  net 256.50 USD, PF 1.31, trade 51, DD 0.02

Approve/reject: login UI (Strategy Lab) atau perintah /proposals di bot Telegram fund2. Deploy hanya dengan approve owner (PRD 5.9).