# BTC & ETH Order-Flow Zone Research — Backtest Results

Generated UTC: 2026-11-17T19:18:10.740034+00:00

## Scope and data integrity

Data: Binance USD-M perpetual 5-minute klines for BTCUSDT and ETHUSDT. Two years requested; current incomplete candle excluded.
Chronological split: 70% development / 15% validation / 15% historical OOS partition by UTC calendar day. The same OOS partition was already inspected in V1; V2 OOS is descriptive only, not a fresh holdout.
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
| BTC | VP_ONLY | development | 579 | 29.53 | 0.17 | -732.98 | -736.24 | 16 | 0.00% |
| BTC | VP_ONLY | validation | 118 | 20.34 | 0.13 | -183.63 | -183.63 | 13 | 0.00% |
| BTC | VP_ONLY | out_of_sample | 130 | 29.23 | 0.16 | -162.63 | -163.77 | 11 | 0.00% |
| BTC | TPO_DELTA | development | 251 | 17.13 | 0.06 | -502.78 | -503.36 | 25 | 0.00% |
| BTC | TPO_DELTA | validation | 58 | 20.69 | 0.06 | -119.18 | -119.18 | 11 | 0.00% |
| BTC | TPO_DELTA | out_of_sample | 69 | 20.29 | 0.07 | -139.03 | -139.03 | 13 | 0.00% |
| BTC | VP_TPO_DELTA_MSS | development | 44 | 31.82 | 0.25 | -37.75 | -37.82 | 12 | 17.65% |
| BTC | VP_TPO_DELTA_MSS | validation | 10 | 30.00 | 0.27 | -9.80 | -11.72 | 6 | 50.00% |
| BTC | VP_TPO_DELTA_MSS | out_of_sample | 10 | 20.00 | 0.07 | -11.76 | -11.76 | 4 | 0.00% |
| ETH | VP_ONLY | development | 583 | 33.45 | 0.34 | -417.92 | -419.30 | 13 | 0.00% |
| ETH | VP_ONLY | validation | 118 | 30.51 | 0.24 | -110.90 | -111.60 | 6 | 0.00% |
| ETH | VP_ONLY | out_of_sample | 122 | 37.70 | 0.30 | -109.44 | -113.76 | 9 | 0.00% |
| ETH | TPO_DELTA | development | 233 | 32.19 | 0.20 | -260.86 | -260.86 | 11 | 0.00% |
| ETH | TPO_DELTA | validation | 69 | 18.84 | 0.09 | -106.55 | -107.73 | 12 | 0.00% |
| ETH | TPO_DELTA | out_of_sample | 63 | 22.22 | 0.09 | -114.93 | -114.93 | 14 | 0.00% |
| ETH | VP_TPO_DELTA_MSS | development | 35 | 40.00 | 0.51 | -14.84 | -17.68 | 6 | 28.57% |
| ETH | VP_TPO_DELTA_MSS | validation | 13 | 46.15 | 0.80 | -2.02 | -5.01 | 3 | 25.00% |
| ETH | VP_TPO_DELTA_MSS | out_of_sample | 9 | 0.00 | 0.00 | -13.52 | -13.52 | 9 | 0.00% |

## Data quality and model limitations

- **BTC:** 210,009 valid bars, 2024-11-17T19:15:00+00:00 to 2026-11-16T23:55:00+00:00; 0 timestamp gaps; 729 complete UTC profile days; 345 bars without prior-day profile.
  - Volume Profile is a 48-bin candle-volume allocation proxy, not exchange-native trade-by-price volume.
  - TPO counts 5-minute candles whose high-low ranges intersect each price bin; this is 5m time-at-price, not standard 30m letter TPO.
  - Delta is exact taker-buy minus taker-sell base volume aggregated per 5m Binance futures candle, but not delta-at-price or footprint-level absorption.
  - Absorption uses opposing bar-level delta with rejection/close-location; it is a proxy, not proof of resting liquidity.
  - Fees are sensitivities only; spread, slippage, market impact and funding cashflows are not modeled. Positions close before 8h funding boundaries.
- **ETH:** 210,009 valid bars, 2024-11-17T19:15:00+00:00 to 2026-11-16T23:55:00+00:00; 0 timestamp gaps; 729 complete UTC profile days; 345 bars without prior-day profile.
  - Volume Profile is a 48-bin candle-volume allocation proxy, not exchange-native trade-by-price volume.
  - TPO counts 5-minute candles whose high-low ranges intersect each price bin; this is 5m time-at-price, not standard 30m letter TPO.
  - Delta is exact taker-buy minus taker-sell base volume aggregated per 5m Binance futures candle, but not delta-at-price or footprint-level absorption.
  - Absorption uses opposing bar-level delta with rejection/close-location; it is a proxy, not proof of resting liquidity.
  - Fees are sensitivities only; spread, slippage, market impact and funding cashflows are not modeled. Positions close before 8h funding boundaries.

## Interpretation guardrails

This is a proxy-based study, not a true tick-level footprint backtest. VP and TPO are not trade-by-price, and Delta is bar-aggregated. Do not describe it as a full footprint model.
OOS is reported once as a final diagnostic and must not be used for tuning. No production rules or live alerts are modified by this experiment.
