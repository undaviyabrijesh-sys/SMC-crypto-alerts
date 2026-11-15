# BTC exhaustion-to-mean-reversion (EMT-inspired proxy) — preregistration, 2026-11-16

## Scope and terminology

This is a new, mechanical EMT-inspired exhaustion-to-mean-reversion proxy. It is not represented as the canonical definition of any discretionary Exhaustion Mean Theory. The goal is to test whether a measurable volume/range climax after a directional extension predicts a short-horizon reversal in BTC. No profitability is assumed.

## Instrument and data

- Delta Exchange India BTCUSD perpetual, traded-price OHLCV.
- Primary signal/execution: 5m; completed 15m and 1h context only.
- Two years where available; retain UTC timestamps, data hashes, source row counts, gaps, duplicate/invalid rows and zero-volume counts.
- Do not fill missing bars. Feature and trade windows reset at gaps.

## Frozen event definition

For each completed 5m candle:

1. **Directional extension:** the prior 12 completed 5m closes show a signed return whose absolute value exceeds the prior-only rolling 30-day 90th percentile of absolute 1h returns. The 1h return series is available only after the relevant 1h candle closes.
2. **Volume climax:** current 5m volume is at or above the prior-only 95th percentile of the same UTC 5m time-of-day bucket over the preceding 30 calendar days (minimum 20 valid observations).
3. **Range expansion:** current 5m true range is at least 1.5 times the prior-only median true range of the previous 20 completed 5m candles.
4. **Rejection:** after an upward extension, upper wick is at least 40% of the candle range and close location is in the lower 40% of the range; after a downward extension, lower wick is at least 40% and close location is in the upper 40% of the range.
5. **Confirmation:** the next completed 5m candle closes in the reversal direction and closes beyond the midpoint of the exhaustion candle. Enter at the following 5m open.

Long and short events are evaluated separately. The same exhaustion event may not generate more than one trade; use an 8h global cooldown and one position at a time.

## Execution hypothesis (only if event study shows positive lift)

- Initial stop: beyond the exhaustion candle extreme plus 0.1 × completed 5m ATR14.
- Targets: 1R, 1.5R and 2R, tested as a small predeclared comparison.
- Maximum hold: 4h; time exit at last completed 5m close.
- Same-bar stop/target ambiguity: stop first; adverse stop-gap fill; no fills across missing bars.
- 6/12/20 bps assumed round-trip costs; funding excluded until historical cashflow mapping is verified.

## First-stage event study

Before any stop/target grid, compare 1h and 4h forward returns after events against matched non-event controls matched by UTC day, direction, completed 4h regime and 3h UTC time bucket. Require controls to be outside a ±30m event window. Use only prior-known features and freeze all signal timestamps.

## Evaluation

- Chronological 70/15/15 train/validation/untouched OOS split.
- Forward outcomes and all trade horizons must remain inside the sample.
- Report event count, side, regime, forward-return distribution, win rate, mean/median net return, matched-control lift, bootstrap intervals where sample permits, monthly consistency and 6/12/20 bps cost sensitivity.
- Do not evaluate OOS unless a frozen candidate passes both train and validation gates.
- Do not tune validation or OOS. Keep the event study distinct from the subsequent stop/target execution backtest.

## Decision rule

If the event underperforms matched controls, reject the event definition without expanding a large parameter grid. If the event has a robust positive lift, proceed to the small stop/target grid. Any strategy remains experimental until a separate promotion review is completed.

No production, main-branch, alert or order changes are permitted.
