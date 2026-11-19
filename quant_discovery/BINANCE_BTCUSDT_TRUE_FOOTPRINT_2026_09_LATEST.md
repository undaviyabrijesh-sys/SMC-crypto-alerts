# BTCUSDT 2026-09 true footprint / VP / TPO feature build

- Status: **PASS**
- Retrieved: 2026-11-19T11:17:29.083140+00:00
- AggTrade rows: 36036629
- 5m price-level rows: 8510392
- Daily profile days: 30
- Integrity / reconciliation / profile validation: True / True / True

## Trade-level data
- aggtrade_total_base_quantity: 4267354.779
- taker_buy_base_quantity: 2112553.2379999994
- taker_sell_base_quantity: 2154801.5410000007
- signed_delta_base_quantity: -42248.30300000124
- first_agg_id: 3435054521
- last_agg_id: 3471091149
- aggregate_id_gaps: 0
- duplicate_ids: 0
- id_order_violations: 0
- timestamp_regressions: 0

## 5m reconciliation
- kline_bars: 8640
- aggtrade_bars: 8640
- unmatched_bars: 0
- total_volume_relative_error: 0.0
- taker_buy_relative_error: 0.0
- volume_per_bar_relative_error_p95: 4.380483043990616e-05
- volume_per_bar_relative_error_max: 0.026441252406052662
- taker_buy_per_bar_relative_error_p95: 6.8328347408553824e-06
- taker_buy_per_bar_relative_error_max: 0.07939200088489878
- volume_pass: True
- taker_buy_pass: True
- coverage_pass: True

## Exact-price footprint outputs
- unique_price_levels: 124629
- bars_with_footprint: 8640
- mean_price_levels_per_5m_bar: 984.9990740740741
- median_price_levels_per_5m_bar: 781.0
- max_price_levels_per_5m_bar: 16594
- max_tpo_30m_count_at_one_price: 33
- daily_volume_value_area_share_min: 0.7000023047458304
- daily_tpo_value_area_share_min: 0.7
- price_level_key_unique: True
- price_level_quantity_sums_match: True
- tpo_count_range_1_to_48: True
- daily_profiles_expected_days: True
- tpo_48_brackets_every_day: True
- price_grid_0_1_usdt: True
- value_area_70pct_check: True

No strategy signal, entry, stop, target, fee, funding or PnL was tested.
