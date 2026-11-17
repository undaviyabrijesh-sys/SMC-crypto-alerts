# ETH 15m EMA20 pullback cross-asset replication — preregistration (2026-11-17)

Purpose: replicate the exact BTC 15m EMA20 pullback/reclaim event definition on ETH without changing parameters. This is a cross-asset replication, not an optimisation.

- Data: Delta ETHUSD native 15m traded-price OHLCV; complete contiguous 4h bars built from 16 consecutive 15m candles.
- Regime: completed 4h close > EMA50 > EMA200 permits longs; completed 4h close < EMA50 < EMA200 permits shorts. Context is usable only at the 4h right-edge close.
- Long: previous 15m close <= previous EMA20; current low within ±0.10 × Wilder ATR(14) of current EMA20; current close > EMA20 and > open; 4h regime bull. Short is the exact inverse in bear regime.
- Entry: next 15m open. One global event per 8 hours. Horizons: 1h and 4h fixed forward returns.
- Funding: evaluate only from 2025-09-08 12:00 UTC onward; exclude 4h outcomes reaching or exceeding next 00:00/08:00/16:00 UTC settlement. Do not apply funding cashflows.
- Controls: one deterministic non-signal control per event, same UTC day, side, completed 4h regime and 3h UTC bucket, without replacement; exclude all raw qualifying signals and controls within ±1h of any raw signal.
- Costs: 4/7/10/20 bps round-trip assumptions; 10 bps primary.
- Chronology: six-month indicator warm-up; fixed two-month folds; final four months reserved and excluded from feature construction/evaluation. No parameter search.
- Acceptance: a positive point estimate alone is not validation. Inconclusive if samples are small, paired-lift or absolute-mean intervals include zero, or results depend on a single month/side/outlier. No stop/target grid follows a weak replication.