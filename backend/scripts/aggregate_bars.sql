-- Agregasi bars multi-timeframe dari data real MT5 yang sudah ada.
-- 5m/15m dari bars_1m, 4h dari bars_1h. Idempotent (ON CONFLICT DO NOTHING).
-- Jalankan: docker exec -i backend-postgres-1 psql -U lumine -d lumine < aggregate_bars.sql

-- 5m dari 1m
INSERT INTO bars_5m (symbol, ts, open, high, low, close, volume)
SELECT
  symbol,
  to_timestamp(floor(extract(epoch FROM ts) / 300) * 300)::timestamptz AS bucket,
  (array_agg(open ORDER BY ts))[1],
  max(high),
  min(low),
  (array_agg(close ORDER BY ts DESC))[1],
  sum(volume)
FROM bars_1m
GROUP BY symbol, bucket
ON CONFLICT DO NOTHING;

-- 15m dari 1m (pakai tabel bars_5m yang baru terisi)
INSERT INTO bars_5m (symbol, ts, open, high, low, close, volume)
SELECT
  symbol,
  to_timestamp(floor(extract(epoch FROM ts) / 900) * 900)::timestamptz AS bucket,
  (array_agg(open ORDER BY ts))[1],
  max(high),
  min(low),
  (array_agg(close ORDER BY ts DESC))[1],
  sum(volume)
FROM bars_1m
GROUP BY symbol, bucket
ON CONFLICT DO NOTHING;

-- 4h dari 1h
INSERT INTO bars_4h (symbol, ts, open, high, low, close, volume)
SELECT
  symbol,
  to_timestamp(floor(extract(epoch FROM ts) / 14400) * 14400)::timestamptz AS bucket,
  (array_agg(open ORDER BY ts))[1],
  max(high),
  min(low),
  (array_agg(close ORDER BY ts DESC))[1],
  sum(volume)
FROM bars_1h
GROUP BY symbol, bucket
ON CONFLICT DO NOTHING;

-- Ringkasan
SELECT '5m' tf, COUNT(*) FROM bars_5m
UNION ALL SELECT '4h', COUNT(*) FROM bars_4h;
