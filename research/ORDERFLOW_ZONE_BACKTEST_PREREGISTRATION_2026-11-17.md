# BTC/ETH Volume Profile + Delta + TPO zone backtest — preregistration

**Date:** 2026-11-17  
**Branch:** \`ai-quant-rebuild\`  
**Status:** frozen research experiment; no production or live-alert changes.

## Research question

Do prior-session Volume Profile rejection, TPO rejection with opposing aggressive delta, or a combined VP/TPO confluence + delta absorption + 5-minute market-structure-shift (MSS) entry provide a repeatable intraday edge on BTC and ETH perpetual futures after assumed transaction costs?

## Instruments and data

- Binance USD-M perpetual contracts: \`BTCUSDT\` and \`ETHUSDT\`.
- Native 5-minute futures klines, two years ending at the latest completed candle.
- The Kline response's taker-buy base-asset volume and total base-asset volume are used to calculate per-bar delta: \`2 × taker_buy_base_volume − total_base_volume\`. This is an aggressor-side aggregate per 5-minute bar, not a per-price footprint delta.
- Exclude current/incomplete candles. De-duplicate timestamps, validate OHLC shape, positive prices, volume and taker-buy-volume bounds. Require 288 consecutive 5-minute bars to construct a complete UTC-day profile. Incomplete days do not produce a profile for the following day.
- Data source and SHA-256 fingerprints are recorded in the run metadata.

## Frozen profile construction

For each complete prior UTC day, form 48 equal-width bins between the day's low and high.

- **Volume Profile proxy:** allocate each 5-minute candle's reported volume equally across every price bin intersected by that candle's low-high range. POC is the maximum-volume bin. Build a contiguous 70% value area outward from POC; higher adjacent weight is added first, ties resolve to the lower-price bin. This is an OHLCV candle-volume proxy, not exchange-native trade-by-price volume.
- **TPO proxy:** count each 5-minute candle once in every bin intersected by its low-high range. Build a contiguous 70% TPO value area with the same POC expansion/tie rule. This is 5-minute time-at-price, not standard 30-minute letter-based TPO.
- Prior-day levels are frozen for the entire following UTC day. No current-day volume or time-at-price contributes to that day's levels.
- Wilder ATR(14) on completed 5-minute candles, shifted one bar, is used for offsets and stops.

## Frozen candidate models

1. **VP_ONLY:** long when the current 5-minute low reaches at least \`0.05 × prior ATR\` below prior-day VAL, then closes above VAL and at/above candle midpoint. Short is the mirrored VAH rejection. Entry is next 5-minute open.
2. **TPO_DELTA:** same rejection shape against prior-day TPO VAL/VAH, plus opposing aggressive delta on the rejection bar: \`delta_ratio ≤ −0.15\` for a bullish VAL reclaim (sell aggression absorbed) or \`delta_ratio ≥ +0.15\` for a bearish VAH rejection (buy aggression absorbed). Entry is next 5-minute open.
3. **VP_TPO_DELTA_MSS:** corresponding VP and TPO value boundaries must be within \`0.15 × prior ATR\`; require the same opposing-delta rejection, then wait up to six subsequent 5-minute bars for a close through the preceding three-bar swing in the trade direction. Entry is the next bar open after MSS.

The delta/absorption feature is necessarily a bar-level proxy. It cannot establish that aggressive volume traded at the exact rejection price or prove passive absorption there.

## Execution and risk assumptions

- Stop beyond the original rejection candle extreme by \`0.10 × prior ATR\`.
- Fixed targets: 1.5R, 2R and 3R. Primary comparison is 2R.
- Maximum holding period: four hours. Exit at the last completed 5-minute bar before the next 00:00/08:00/16:00 UTC funding boundary; funding cashflows are excluded.
- Stop first if stop and target are both touched within one 5-minute candle. Gap-through stop exits use the worse opening price; target gaps fill at target.
- One open trade at a time per asset/model and at most one trade per side per UTC day. Trades are included only when their complete entry-exit lifecycle fits inside one data split.
- Cost sensitivity: 4, 7, 10 and 20 bps round-trip on entry plus exit notionals. Primary comparison assumes 10 bps round-trip. No independent spread, slippage or market-impact model is included.

## Validation design and reporting

- Chronological split by UTC calendar day: 70% development, 15% validation, 15% untouched out-of-sample. Features for each bar use only information available at that time; the preceding day's complete profile may carry across a split boundary.
- Report trade count, win rate, profit factor, gross/net R, max drawdown in R, maximum losing streak, long/short counts, TP/SL/time exits, positive active months, monthly P&L, one-hour regime attribution, target sensitivity and transaction-cost sensitivity.
- Out-of-sample is reported once as a final diagnostic and must not be used for parameter selection.
- Provisional promotion gate: at least 30 development trades and 15 validation trades; positive net R and profit factor at least 1.10 in both at 2R/10 bps; at least 50% positive active months in both; and no material degradation at 20 bps. Underpowered samples are inconclusive, not passes.
- A strategy failing or missing the gate remains experimental. No live signals, production rule changes or order execution are permitted from this study.

## Explicit limitations

This is a controlled proxy study. Volume Profile uses candle-range allocation rather than true trades-at-price; TPO uses 5-minute bar range occupancy; delta is aggregate per 5-minute bar rather than delta-at-price. Results must not be described as a full tick-level footprint backtest. Fees are sensitivity assumptions, not a verified account fee tier; funding is avoided by time-based exits rather than modeled as cashflow.
