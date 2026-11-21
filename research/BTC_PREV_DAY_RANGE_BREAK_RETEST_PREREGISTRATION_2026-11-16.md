# BTC prior-UTC-day range break/retest — preregistration

Date: 2026-11-16 UTC
Branch: ai-quant-rebuild
Status: hypothesis frozen; implementation/backtest not yet run

## Hypothesis

A confirmed 15m close outside the previous completed UTC-day high/low, followed by a 5m retest that holds the broken level and resumes in the breakout direction, may distinguish accepted range expansion from failed breakouts. This is a mechanical prior-day-level role-reversal hypothesis, not a claim that all prior-day highs/lows contain resting liquidity.

## Instrument and data

- Delta Exchange India BTCUSD perpetual traded-price OHLCV.
- Native 5m candles, with complete 15m bars derived only from contiguous 5m data.
- Use at least the latest 730 days where available.
- Prior UTC-day high/low becomes available only after the full UTC day has closed.
- 15m breakout boundary must be computed from the completed prior UTC-day range; no current-day high/low may enter the reference.
- ATR calculations use only completed bars and reset after data gaps.

## Frozen entry definition

1. At the close of a completed 15m candle, price closes at least 0.10 × prior 15m ATR(14) beyond the previous UTC-day high (long) or low (short).
2. Within the next 12 completed 5m bars, price must revisit the broken level within 0.15 × prior 5m ATR(14).
3. The retest candle must close back on the breakout side of the level and close in the directional half of its range (upper half for long, lower half for short).
4. Entry is the next 5m open after retest confirmation.
5. Cancel the setup if a 5m candle closes back inside the prior-day range before entry, if the level is not retested within 12 bars, or if the retest extreme invalidates the breakout before confirmation.
6. One open BTC position at a time; each prior-day level may generate at most one entry per direction per UTC day. No overlapping positions.
7. Maximum holding time: 4 hours.

## Stop and target

- Initial stop: beyond the 5m retest extreme with a 0.10 × prior 5m ATR buffer.
- Skip if stop distance is non-positive or greater than 2.5 × prior 5m ATR.
- Targets: fixed 1.5R, 2R and 3R. These are the only target variants in the first matrix.
- Same-bar stop/target ambiguity resolves stop first. Stops gapped through fill at the worse opening price; target gaps fill at target. If a gap or missing interval makes the first touch unknowable, mark the trade unresolved and exclude it from performance while reporting it separately.
- Time exit at the last completed 5m close at or before the 4-hour limit.

## Evaluation

- Small matrix: both breakout directions in one combined stream, 1.5R/2R/3R targets; 3 configurations.
- Chronological 70% development / 15% validation / final 15% untouched.
- No OOS evaluation unless at least one configuration passes both development and validation gates.
- Costs: assumed 6/12/20 bps round trip, 12 bps primary. Funding excluded until historical settlement cashflow semantics are verified; disclose that spread, slippage and market impact are not separately modelled unless measured data becomes available.
- Report trade count, long/short counts, win rate, PF, net R, average R, maximum drawdown in R, maximum losing streak, holding time, monthly and regime breakdown, unresolved paths, and sensitivity at all three cost levels.

## Frozen promotion gate

At least one target must satisfy both development and validation:
- At least 100 development trades and 30 validation trades.
- Positive net R and PF above 1 after 12 bps assumed round-trip cost.
- Positive mean R per trade.
- At least 50% positive active months.
- Maximum drawdown and losing streak reported; no gate may be passed by a single month or direction dominating the entire result.
- Neighbouring target results should not collapse abruptly; the 1.5R/2R/3R comparison is a robustness check, not an optimisation licence.

If no configuration passes, reject the frozen definition. Do not tune the validation period or inspect the final 15%.

## Research boundary

This is research-only. Do not alter production, `APPROVED_STRATEGIES`, live alerts, exchange orders or the `main` branch. A pass only authorizes a separate review; it does not validate a live strategy.
