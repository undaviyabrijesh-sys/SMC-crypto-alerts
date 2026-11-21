# BTC prior-day volume-profile proxy rejection → POC exit variation — results (2026-11-17)

## Decision

**Rejected. No OOS evaluation.** The POC target did not produce a positive gross edge, and every tested round-trip cost (4/7/10/20 bps) produced negative net R in both development and validation. The 2R fixed-target diagnostic also failed both samples.

## Prior-art correction

The preregistration's initial prior-art audit was incomplete. The repository already contains [`research/orderflow_profile_backtest.py`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/blob/ai-quant-rebuild/research/orderflow_profile_backtest.py), which implements the same broad 48-bin prior-UTC-day candle-volume profile proxy, 70% VAH/VAL, 5m rejection, next-open entry, rejection-extreme stop +0.10 ATR and 4h cap. Its `VP_ONLY` model uses fixed 1.5R/2R/3R exits. The present run is therefore **not a new strategy family**: it is a POC-target exit variation of the existing volume-profile rejection family, tested on the archived Delta BTCUSD feed.

The existing Binance USD-M `VP_ONLY` study independently rejected the fixed-R family: BTC 2R/10 bps had 567 development trades (PF 0.155, -780.39R) and 112 validation trades (PF 0.093, -198.76R); ETH had 571 development trades (PF 0.34, -419.47R) and 115 validation trades (PF 0.24, -110.21R). These are a separate feed/implementation and supporting context, not an apples-to-apples comparison. See [existing report](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/blob/ai-quant-rebuild/quant_discovery/ORDERFLOW_ZONE_BACKTEST_LATEST.md).

## Data and split

- Instrument: Delta BTCUSD perpetual, 5-minute traded-price OHLCV.
- Source: archived CSV `btc_5m_source.csv`; 210,239 rows, 2024-11-16 11:30 UTC through 2026-11-16 11:20 UTC.
- Data quality: zero duplicate timestamps, malformed OHLC rows or missing 5m intervals; 334 zero-volume bars retained.
- Raw CSV SHA-256: `5b612e1c496f16277b459f58ddff33b69d8f7912b70d8f733f0a17be844eb4fb`.
- Canonical DataFrame digest: `bfcaa7a0a081246a9e8ec0dcaca0d01c25e793b250e8399699bddf2c7f0756e3`. These are different hash definitions, not a data mismatch.
- Complete prior UTC profile days in the feature prefix: 620.
- Development end-exclusive: 2026-04-11 12:00 UTC (147,174 rows).
- Validation end-exclusive: 2026-07-30 00:00 UTC (178,710 rows total loaded).
- Final 31,529 rows (15%) were not loaded into feature construction or candidate generation. OOS not evaluated.

## Frozen signal and execution

- Previous complete UTC day's 5m candle volume is spread uniformly across 48 equal-width bins intersected by each candle's low/high range. POC is the highest-volume bin centre; 70% contiguous value area expands from POC, ties lower.
- Short VAH rejection / long VAL rejection requires 0.05 prior ATR penetration and close back inside value in the appropriate candle half.
- Next 5m open entry only if still inside value, POC is favourable, and POC reward is at least 1R initial risk. One signal per side per UTC day; one global open trade per target configuration.
- Stop beyond rejection-candle extreme by 0.10 prior ATR. POC is primary target; 1.5R/2R/3R are fixed-target diagnostics. Max hold 4h; exit at the last completed close strictly before next 00:00/08:00/16:00 UTC funding boundary.
- Same-bar stop/target: stop first. Stop gap-through fills at worse open; target gaps fill at target. Missing-bar path unresolved. Funding cashflows excluded; no trade crosses settlement.
- Costs 4/7/10/20 bps round trip, applied to average entry/exit notional; 10 bps primary. Actual fee tier is unverified; spread, slippage and market impact are not separately modelled.

## Primary POC target — 10 bps

| Metric | Development | Validation |
|---|---:|---:|
| Executed trades | 526 | 112 |
| Win rate (net R > 0) | 27.76% | 20.54% |
| Profit factor (net R) | 0.372 | 0.265 |
| Gross R | -3.44R | -21.63R |
| Net R | -408.89R | -115.27R |
| Average net R/trade | -0.777R | -1.029R |
| Max drawdown (trade-sequence R) | -414.56R | -115.75R |
| Longest losing streak | 17 | 15 |
| Positive active months | 1/18 | 0/4 |
| TP / SL / time exits | 112 / 348 / 66 | 20 / 84 / 8 |

The gross result is already negative before fees. Every 4h EMA50/EMA200 regime was negative in both samples; both long and short sides were negative.

## Cost sensitivity — POC target

| Round-trip cost | Development net R | Validation net R |
|---:|---:|---:|
| 4 bps | -165.62R | -59.09R |
| 7 bps | -287.25R | -87.18R |
| 10 bps | -408.89R | -115.27R |
| 20 bps | -814.33R | -208.91R |

Median stop risk was 0.156% of entry in development and 0.135% in validation. At 10 bps, median estimated cost was 0.64R and 0.74R respectively (mean 0.77R / 0.84R). This explains substantial cost drag, but it does not explain away the negative gross POC result.

## Fixed-target diagnostics — 10 bps

| Target | Sample | Trades | Win % | PF | Gross R | Net R | Max DD R | Positive months |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1.5R | Development | 526 | 36.69% | 0.306 | +27.49 | -377.94 | -384.25 | 1/18 |
| 1.5R | Validation | 112 | 27.68% | 0.162 | -21.71 | -115.35 | -115.35 | 0/4 |
| 2R | Development | 526 | 33.84% | 0.363 | +32.69 | -372.76 | -376.10 | 1/18 |
| 2R | Validation | 112 | 26.79% | 0.233 | -18.41 | -112.06 | -112.06 | 0/4 |
| 3R | Development | 526 | 29.47% | 0.454 | +57.03 | -348.41 | -354.62 | 1/18 |
| 3R | Validation | 112 | 24.11% | 0.367 | -0.57 | -94.21 | -95.62 | 0/4 |

## Gate and tests

The frozen POC gate required at least 50 development and 20 validation trades, positive net R, PF >=1.05, drawdown no worse than -20R/-10R and at least 50% positive active months. Trade-count minimums passed, but every profitability, drawdown and monthly-consistency condition failed.

Eight deterministic test groups passed: volume conservation/70% value area; lower-bin tie-breaking; complete-day-only and prior-day-only profile mapping; current-day volume perturbation invariance; strict funding-boundary exit; stop-first ambiguity/adverse gap; next-open entry/one signal per side/day; missing-bar path unresolved. Python compilation passed.

## Limitations and next step

This is only a candle-volume proxy, not true exchange trade-by-price volume. The existing order-flow study also tests TPO and bar-level delta variants, all rejected under its train/validation gates. Do not run more cosmetic candle-volume proxy variants. If profile research resumes, first obtain tick/trade-level BTC and ETH data with aggressor side, then preregister a genuine volume-at-price and delta-at-price study. Otherwise move to a genuinely different strategy family. No production, live alert, exchange order or `main` branch changes.
