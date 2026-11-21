# BTC & ETH Order-Flow Zone Research — Backtest Results

Generated UTC: 2026-11-17T02:19:20.722388+00:00

## Scope and data integrity

Data: Binance USD-M perpetual 5-minute klines for BTCUSDT and ETHUSDT. Two years requested; current incomplete candle excluded.
Chronological split: 70% development / 15% validation / 15% untouched out-of-sample by UTC calendar day.
Primary comparison: fixed 2R target, assumed 10 bps round-trip cost. Full 1.5R/2R/3R and 4/7/10/20 bps sensitivity is in metrics.csv.
A trade is counted only when its full lifecycle ends inside its assigned split. One open position and at most one trade per side per UTC day per model.

## Strategy definitions

- **VP_ONLY:** prior complete UTC day's 70% volume-value edge rejection; 5m candle volume is allocated across 48 price bins.
- **TPO_DELTA:** prior complete UTC day's 70% TPO-value edge rejection plus opposing aggressive 5m delta.
- **VP_TPO_DELTA_MSS:** VP/TPO boundary confluence (within 0.15 prior ATR), opposing delta, then a later 5m close through the preceding 3-bar swing; entry next bar open.
Stops are beyond the rejection candle extreme by 0.10 prior ATR; max hold four hours; stop wins ambiguous same-bar stop/target touches.

## Primary comparison: 2R / 10 bps round trip

| Asset | Model | Split | Trades | Win % | PF | Net R | Max DD R | Max loss streak | Positive active months |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | VP_ONLY | development | 567 | 27.69 | 0.15 | -780.39 | -785.07 | 16 | 5.56% |
| BTC | VP_ONLY | validation | 112 | 16.07 | 0.09 | -198.76 | -198.76 | 26 | 0.00% |
| BTC | VP_ONLY | out_of_sample | 125 | 28.00 | 0.13 | -185.42 | -185.42 | 11 | 0.00% |
| BTC | TPO_DELTA | development | 243 | 16.87 | 0.05 | -495.14 | -495.73 | 25 | 0.00% |
| BTC | TPO_DELTA | validation | 55 | 21.82 | 0.06 | -114.60 | -114.60 | 11 | 0.00% |
| BTC | TPO_DELTA | out_of_sample | 66 | 19.70 | 0.06 | -140.18 | -140.18 | 13 | 0.00% |
| BTC | VP_TPO_DELTA_MSS | development | 27 | 40.74 | 0.28 | -23.87 | -23.94 | 5 | 25.00% |
| BTC | VP_TPO_DELTA_MSS | validation | 6 | 16.67 | 0.11 | -8.38 | -8.38 | 4 | 25.00% |
| BTC | VP_TPO_DELTA_MSS | out_of_sample | 6 | 16.67 | 0.05 | -7.68 | -7.68 | 4 | 25.00% |
| ETH | VP_ONLY | development | 571 | 33.80 | 0.34 | -419.47 | -420.84 | 12 | 0.00% |
| ETH | VP_ONLY | validation | 115 | 31.30 | 0.24 | -110.21 | -110.21 | 10 | 0.00% |
| ETH | VP_ONLY | out_of_sample | 114 | 32.46 | 0.24 | -126.03 | -129.45 | 9 | 0.00% |
| ETH | TPO_DELTA | development | 226 | 30.97 | 0.19 | -265.84 | -265.84 | 20 | 0.00% |
| ETH | TPO_DELTA | validation | 66 | 19.70 | 0.08 | -103.73 | -104.91 | 12 | 0.00% |
| ETH | TPO_DELTA | out_of_sample | 63 | 22.22 | 0.09 | -120.63 | -120.63 | 14 | 0.00% |
| ETH | VP_TPO_DELTA_MSS | development | 32 | 40.62 | 0.50 | -15.66 | -18.50 | 4 | 23.08% |
| ETH | VP_TPO_DELTA_MSS | validation | 12 | 50.00 | 0.81 | -1.87 | -4.92 | 3 | 25.00% |
| ETH | VP_TPO_DELTA_MSS | out_of_sample | 7 | 0.00 | 0.00 | -12.57 | -12.57 | 7 | 0.00% |

## Data quality and model limitations

- **BTC:** 209,925 valid bars, 2024-11-17T02:15:00+00:00 to 2026-11-15T23:55:00+00:00; 0 timestamp gaps; 728 complete UTC profile days; 549 bars without prior-day profile.
  - Volume Profile is a 48-bin candle-volume allocation proxy, not exchange-native trade-by-price volume.
  - TPO counts 5-minute candles whose high-low ranges intersect each price bin; this is 5m time-at-price, not standard 30m letter TPO.
  - Delta is exact taker-buy minus taker-sell base volume aggregated per 5m Binance futures candle, but not delta-at-price or footprint-level absorption.
  - Absorption uses opposing bar-level delta with rejection/close-location; it is a proxy, not proof of resting liquidity.
  - Fees are sensitivities only; spread, slippage, market impact and funding cashflows are not modeled. Positions close before 8h funding boundaries.
- **ETH:** 209,925 valid bars, 2024-11-17T02:15:00+00:00 to 2026-11-15T23:55:00+00:00; 0 timestamp gaps; 728 complete UTC profile days; 549 bars without prior-day profile.
  - Volume Profile is a 48-bin candle-volume allocation proxy, not exchange-native trade-by-price volume.
  - TPO counts 5-minute candles whose high-low ranges intersect each price bin; this is 5m time-at-price, not standard 30m letter TPO.
  - Delta is exact taker-buy minus taker-sell base volume aggregated per 5m Binance futures candle, but not delta-at-price or footprint-level absorption.
  - Absorption uses opposing bar-level delta with rejection/close-location; it is a proxy, not proof of resting liquidity.
  - Fees are sensitivities only; spread, slippage, market impact and funding cashflows are not modeled. Positions close before 8h funding boundaries.

## Interpretation guardrails

This is a proxy-based study, not a true tick-level footprint backtest. VP and TPO are not trade-by-price, and Delta is bar-aggregated. Do not describe it as a full footprint model.
OOS is reported once as a final diagnostic and must not be used for tuning. No production rules or live alerts are modified by this experiment.
