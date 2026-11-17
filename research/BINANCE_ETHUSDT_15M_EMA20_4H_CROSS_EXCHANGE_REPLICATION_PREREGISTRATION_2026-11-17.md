# Binance ETHUSDT 15m cross-exchange replication — preregistration (2026-11-17)

Purpose: independently replicate the frozen Delta ETHUSD 15m EMA20 pullback/reclaim event study on Binance USDⓈ-M ETHUSDT perpetual. This is a cross-exchange robustness check, not a parameter search and not a new strategy family.

## Frozen rules
- Source: Binance USDⓈ-M ETHUSDT perpetual 15m klines. Fetch only 2025-03-08 00:00 UTC through 2026-07-15 00:00 UTC (end-exclusive). Do not fetch or inspect the reserved final four months beginning 2026-07-15.
- Build 4h candles only from 16 contiguous 15m candles aligned to UTC epoch boundaries. A 4h context becomes available only at its right-edge close.
- Completed 4h regime: close > EMA50 > EMA200 permits longs; close < EMA50 < EMA200 permits shorts; otherwise neutral.
- 15m EMA20 uses adjust=False/min_periods=20. ATR14 is Wilder RMA seeded with the first 14 true ranges within each contiguous segment.
- Long signal on a completed 15m candle: previous close <= previous EMA20; current low within ±0.10 × current ATR14 of current EMA20; current close > current EMA20 and > current open; completed 4h regime is bull. Short is the exact inverse in a bear regime.
- Signal timestamp and entry timestamp are the next 15m bar open (signal candle close); enter at that bar's open. One global event per 8 hours.
- Fixed forward-return horizons: 1h and 4h. Exclude a 4h observation if its endpoint reaches or crosses the next assumed 00:00/08:00/16:00 UTC funding boundary. Funding cashflows are not applied.
- Controls: one deterministic non-signal control per event, same UTC day, side, completed 4h regime and 3h UTC bucket, without replacement; exclude candidate controls within ±1h of any raw qualifying signal.
- Round-trip cost sensitivities: 4/7/10/20 bps; 10 bps primary. No extra spread/impact model.
- Warm-up: six months before evaluation. Evaluation: 2025-09-08 12:00 UTC through 2026-07-15 00:00 UTC. Report two-month chronological folds. Final four months are untouched and not downloaded.

## Required reporting
- Data integrity: row count, first/last timestamp, duplicates, malformed OHLC, missing 15m intervals, complete 4h bars.
- Event/control counts, match rate, win rate, descriptive fixed-horizon PF, mean/median net bps, paired-control lift, day-cluster bootstrap intervals, monthly/fold stability, side/regime diagnostics and cost sensitivity.
- R, stop-based PnL and executable account drawdown are not applicable because this is a fixed-horizon event study without stops/targets.

## Decision gates
- This is a replication, not optimisation. Do not alter thresholds, cooldown, matching, horizons or costs after observing results.
- Inconclusive if either asset/exchange replication is underpowered, event means are not robustly positive, confidence intervals include zero, or results depend on one event/month/fold.
- No stop/target grid follows a weak replication. Do not inspect the final holdout. No production/live changes, orders or alerts.
