# Binance USD-M BTCUSDT September 2026 aggTrades pilot

- Status: **PASS**
- Retrieved: 2026-11-18T11:31:10.181518+00:00
- Requested interval: 2026-09-01T00:00:00+00:00 to 2026-10-01T00:00:00+00:00 (exclusive)
- Integrity pass: True
- Reconciliation pass: True

## Archive integrity
- aggtrade_rows: 36036629
- first_agg_id: 3435054521
- last_agg_id: 3471091149
- first_timestamp_utc: 2026-09-01T00:00:00.003000+00:00
- last_timestamp_utc: 2026-09-30T23:59:59.591000+00:00
- aggregate_id_gaps: 0
- duplicate_ids: 0
- id_order_violations: 0
- timestamp_regressions: 0
- out_of_month_timestamps: 0
- aggtrade_total_base_quantity: 4267354.779
- taker_buy_base_quantity: 2112553.2379999994
- taker_sell_base_quantity: 2154801.541
- signed_delta_base_quantity: -42248.30300000077

## 5-minute reconciliation
- kline_buckets: 8640
- aggtrade_buckets: 8640
- kline_only_buckets: 0
- aggtrade_only_buckets: 0
- unmatched_timestamp_rows: 0
- matched_buckets: 8640
- agg_total_base_quantity: 4267354.77900014
- kline_total_base_volume: 4267354.779
- total_volume_relative_error: 3.273652963653008e-14
- agg_taker_buy_base_quantity: 2112553.2380000115
- kline_taker_buy_base_volume: 2112553.238
- taker_buy_total_relative_error: 5.510645589085733e-15
- volume_per_bar_relative_error_median: 1.0516627875379301e-14
- volume_per_bar_relative_error_p95: 4.380483044410305e-05
- volume_per_bar_relative_error_max: 0.02644125240605231
- taker_buy_per_bar_relative_error_median: 4.083064934423918e-15
- taker_buy_per_bar_relative_error_p95: 6.832834682694543e-06
- taker_buy_per_bar_relative_error_max: 0.07939200088489878
- volume_exact_match_fraction_1e-8: 0.8862268518518519
- taker_buy_exact_match_fraction_1e-8: 0.9434027777777778
- total_volume_tolerance: 0.001
- taker_buy_tolerance: 0.001
- total_volume_pass: True
- taker_buy_pass: True
- bucket_coverage_pass: True

## Interpretation
Ready for a separately preregistered trade-level feature study; this pilot itself contains no strategy result.

## Source files
- aggtrade_url: https://data.binance.vision/data/futures/um/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-09.zip
- aggtrade_sha256: 252e92894886c2f752744656e4f1d7a278a75e1456aa32442451b07ee9703b80
- aggtrade_expected_sha256: 252e92894886c2f752744656e4f1d7a278a75e1456aa32442451b07ee9703b80
- kline_url: https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m/BTCUSDT-5m-2026-09.zip
- kline_sha256: 3a2d163a2bd28ca614fa0840a92ecbcde0d9c4962b278dd619d5bf81a9918e26
- kline_expected_sha256: 3a2d163a2bd28ca614fa0840a92ecbcde0d9c4962b278dd619d5bf81a9918e26

No strategy backtest, signal test or trading result was run.
