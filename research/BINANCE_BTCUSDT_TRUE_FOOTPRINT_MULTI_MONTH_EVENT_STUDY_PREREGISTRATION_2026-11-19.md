# BTCUSDT multi-month true-footprint event study — frozen amendment

**Date:** 2026-11-19  
**Branch:** `ai-quant-rebuild`  
**Status:** preregistered descriptive event study; not a stop-defined strategy backtest or promotion test.

## Research question

Do the previously defined BTCUSDT 5-minute absorption and exact-price footprint-continuation event families show consistent fixed-horizon directional returns across June–September 2026 after a fixed 10 bps round-trip cost?

This is a four-month descriptive replication. It does not establish an independent future OOS edge and cannot promote a strategy.

## Frozen source artifacts

Feature-build workflow: [44513565570](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44513565570), completed successfully. All four month jobs passed their metadata gate and 10 deterministic feature tests.

| Month | Artifact ID |
|---|---:|
| 2026-06 | 14524680968 |
| 2026-07 | 14525415431 |
| 2026-08 | 14524786744 |
| 2026-09 | 14525551088 |

Each artifact contains official Binance USD-M BTCUSDT aggTrades and matching 5m kline archives, exact-price footprint levels, daily VP/TPO tables, per-bar reconciliation, metadata and report. Artifact retention is 30 days from 2026-11-19. The event-study workflow downloads only these frozen artifacts; it does not refetch or replace source data.

## Why this is an amendment

The prior September event pilot used aggTrade-derived 5m delta. The multi-month feature builder reports per-bar aggTrade-to-kline differences even where monthly aggregate totals reconcile exactly. The largest known September per-bar errors were 2.6441% for total volume and 7.9392% for taker-buy volume. A boundary-shifted aggTrade can therefore distort a bar-level delta z-score.

This amendment changes only the bar-level absorption delta source and adds a conservative per-bar alignment screen for continuation. The original September event study remains historical provenance and is not overwritten.

## Frozen event definitions

### 1. Absorption proxy — official kline delta

- Use official Binance 5m kline total base volume and taker-buy base volume.
- `delta_fraction = (2 × taker_buy_base_volume − total_base_volume) / total_base_volume`.
- Compute rolling mean and population standard deviation (`ddof=0`) from the preceding 288 completed 5m bars only; shift both statistics by one bar; minimum 96 prior observations.
- Short event: `delta_z >= +2.0` and close location `(close-low)/(high-low) <= 0.25`.
- Long event: `delta_z <= -2.0` and close location `>= 0.75`.
- Zero-volume or zero-range bars cannot signal.

### 2. Footprint continuation proxy — exact-price aggTrades with alignment screen

- Use exact 0.1 USDT price ticks and taker buy/sell base quantity from the frozen aggTrade footprint table.
- Diagonal buy imbalance at price tick p: `buy(p) >= 3 × sell(p-1 tick)` and `buy(p) >= 0.10 BTC`.
- Diagonal sell imbalance at p: `sell(p) >= 3 × buy(p+1 tick)` and `sell(p) >= 0.10 BTC`.
- Require at least three consecutive price ticks flagged on the same side.
- Long requires close location `>= 0.75`; short requires close location `<= 0.25`.
- A continuation signal bar is eligible only when both per-bar total-volume and taker-buy relative errors versus official klines are `<= 0.10%`. Bars outside this screen are excluded from continuation signal generation.
- If both long and short continuation conditions occur on the same bar, exclude that bar as ambiguous.
- The screen reduces known boundary misalignment but does not prove that every price-level assignment is exact; raw-trade boundary validation is still required before any executable strategy claim.

### 3. Common event handling

- Apply a 48-bar (4h) global cooldown separately within each event family, across long and short directions.
- Censor the first 288 bars of each month for rolling warm-up and cross-month cooldown protection.
- Censor the final 48 bars of each month so all forward horizons remain inside the source month.
- Signal is known only after the 5m candle closes; enter at the next 5m open.
- Fixed descriptive horizons: 12 bars (1h) and 48 bars (4h); exit at the corresponding horizon candle close.
- Deduct 10 bps round trip from every event return.
- Report event count, win rate after cost, descriptive PF, mean/median net bps, event-sequence maximum drawdown in bps, maximum losing streak, positive UTC days, and 10,000 day-cluster bootstrap 95% intervals.
- Report each month separately and a pooled June–September day-cluster summary. Do not select a best month or side.

## Exclusions and limitations

- No stop, target, R-multiple, account return, leverage, funding cashflow, spread, slippage, market impact or executable fill model.
- No threshold, cooldown, horizon, imbalance ratio, quantity floor or cost search.
- No parameter tuning, best-side selection or promotion.
- The four months are a contiguous historical descriptive sample, not a prospectively untouched OOS period. Do not label the pooled sample OOS.
- If an event family is positive, it only creates a hypothesis for a separately preregistered stop-defined strategy with chronological development/validation and a future untouched holdout.

## Reproducibility

- Runner: `research/binance_btcusdt_true_footprint_event_study.py`.
- Source feature builder: `research/binance_btcusdt_true_footprint_build.py`.
- Workflow: `.github/workflows/binance-btcusdt-footprint-event-study.yml`.
- The workflow must run deterministic self-tests, validate source feature metadata status PASS, emit per-month event ledgers and summary/bootstrap CSVs, then aggregate the four monthly outputs.
- No production, main-branch, live-alert, paper-state or exchange-order changes.
