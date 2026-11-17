# BTC Donchian breakout baseline — preregistration (2026-11-18)

## Hypothesis
A confirmed 15-minute close through a prior rolling Donchian boundary may capture directional expansion better than a reactive Supertrend flip. This is a mechanical breakout test, not a claim that all Donchian systems are represented.

## Dataset
- Existing archived Delta BTCUSD perpetual 5-minute OHLCV source: the 2026-11-17 BTC prior-day volume-profile research package, member package/data/btc_5m_source.csv.
- Aggregate only complete, UTC-aligned sets of three 5-minute bars into 15-minute candles.
- Do not interpolate missing bars.
- Preserve source and derived-data SHA-256 hashes.

## Frozen rule matrix
- Donchian lookback: 20 or 55 completed 15-minute bars. Upper/lower channels are rolling prior highs/lows shifted one bar.
- Signal: a 15-minute close crosses above the prior upper boundary (long) or below the prior lower boundary (short); prior close must not already be beyond its prior boundary.
- Entry: next 15-minute open.
- Stops: (A) 10-bar rolling opposite extreme, including the completed signal candle; (B) 1.5 x Wilder ATR(14) at signal close.
- Targets: 2R or 3R.
- Filter: none, or direction must agree with the latest fully completed 1-hour close versus its EMA50. Hourly candles are aggregated from 15-minute bar close timestamps; no partial-hour value is used.
- One open position per configuration; no overlapping positions within a configuration.
- Maximum holding: 7 calendar days (672 15-minute bars).
- Same-bar stop and target: stop first.
- Stop gap-through: fill at adverse bar open. Favorable target gap: cap fill at target.
- Round-trip cost sensitivity: 4, 7, 10 and 20 bps of entry notional. Net R = gross R minus cost_bps / initial_stop_risk_bps.
- No parameter changes after observing results.

## Chronological partitions
Partition the full UTC time span into 70% development, 15% validation and final 15% OOS by chronological row position. Boundaries are exact 15-minute bar opens. Feature history before a partition may be used for causal warm-up; no trade lifecycle may cross a partition boundary. Reserve the full 7-day holding horizon at the end of each partition.

## Promotion gate (at 10 bps round-trip cost)
A configuration must have at least 100 completed development trades and 30 validation trades; PF > 1.10 and net R > 0 in both; at least 55% positive active months in both. The OOS partition is not opened unless a frozen configuration passes all development and validation gates. If none passes, leave OOS uncomputed.

## Required reporting
Trade count, net win rate, PF, net R, average R, trade-sequence max drawdown, max losing streak, positive/active months, long/short split, 1-hour EMA50/200 bull/bear/mixed regime attribution, monthly results, and all cost sensitivities.

## Limitations
The supplied source is OHLCV, not trade-level data. Spread and slippage are not separately modeled. Historical Delta funding rates for this series are not present in the archive, so funding is omitted and all results are pre-funding. This omission is material for a 7-day perpetual hold; any promising result would require a funding-aware replay before consideration.

## Decision discipline
This is one predeclared family with a finite 16-configuration matrix, not a parameter sweep to maximize PnL. Keep all code/results on ai-quant-rebuild; do not alter main, production rules, live alerts, or place orders.
