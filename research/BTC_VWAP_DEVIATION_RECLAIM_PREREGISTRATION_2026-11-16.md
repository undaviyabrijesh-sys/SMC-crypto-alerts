# BTC 5m UTC-day VWAP deviation/reclaim event study — preregistration

Date: 2026-11-16 UTC
Branch: ai-quant-rebuild
Status: frozen before the historical run

## Hypothesis

After BTC makes a large intraday extension away from its UTC-day anchored, volume-weighted average price (VWAP), a confirmed 5m rejection that moves back inside the extreme deviation band may predict a short-horizon move back toward VWAP. This is a mechanical event-study hypothesis, not a claim that VWAP is institutional fair value or that the event is independently tradable.

## Instrument and data

- Delta Exchange India BTCUSD perpetual, traded-price OHLCV.
- Native 5m candles, requested over the latest 730 days.
- Keep only closed, valid candles; do not fill missing intervals.
- UTC calendar-day VWAP reset. Typical price is (H+L+C)/3, weighted by traded volume. Zero-volume candles contribute no weight.
- ATR(14) is Wilder-smoothed true range using only candles completed before the signal candle; it normalizes VWAP distance.
- A completed 4h EMA50/EMA200 regime is attribution/matching only, not an entry filter.

## Frozen primary event definition

For each 5m candle t, use the VWAP and OHLCV known at its close:

- Upper extension: previous completed 5m close was at least +1.5 prior-ATR units above its own UTC-day VWAP; current close has moved back below +1.5 ATR but remains above VWAP; current candle is bearish and closes in the lower half of its range. Signal is short.
- Lower extension: previous completed 5m close was at least -1.5 prior-ATR units below its own UTC-day VWAP; current close has moved back above -1.5 ATR but remains below VWAP; current candle is bullish and closes in the upper half of its range. Signal is long.
- Enter at the next 5m candle open. No same-candle entry.
- One global event stream and an 8-hour timestamp cooldown across directions.
- Reset ATR/structure calculations after a 5m data gap; do not create signals across gaps.

A 2.0 ATR threshold is included as a predeclared robustness diagnostic only. It is not eligible to replace the primary 1.5 ATR threshold based on these results.

## Matched controls

Use non-event moderate-deviation rejection bars: prior close deviation between 0.5 and 1.0 ATR (short above VWAP, long below VWAP), same candle direction/rejection-half confirmation, and current close still at least 0.25 ATR from VWAP. Enter at next 5m open.

Match 1:1 without replacement by exact UTC date, direction, completed 4h EMA50/EMA200 regime and 3-hour UTC bucket. Exclude controls within ±30 minutes of any event entry in that chronological sample. Choose nearest timestamp; ties go to earlier control. Controls are a diagnostic benchmark, not independent executable trades.

## Evaluation and costs

- Chronological split by valid 5m row index: 70% development, 15% validation, final 15% untouched.
- Forward horizons: 1h and 4h, measured from next-bar entry open to the close after 12 or 48 complete 5m bars.
- A return is excluded if its horizon crosses a data gap or its sample boundary.
- Round-trip cost assumptions: 6, 12 and 20 bps; primary gate at 12 bps.
- Funding is excluded because historical settlement cashflow mapping is not yet verified. Flat costs do not separately model spread, market impact or slippage.
- 2,000 UTC-day cluster-bootstrap replicates for paired event-minus-control lift; fixed seed 20261116.

## Frozen decision gate — primary 1.5 ATR threshold only

At least one predeclared horizon (1h or 4h) must pass every condition in both development and validation:

- At least 100 development events and 30 validation events.
- At least 50 matched development pairs and 20 matched validation pairs.
- Positive mean absolute event return after 12 bps assumed round-trip cost.
- Positive mean paired event-minus-control return.
- 95% day-cluster bootstrap lower bound for paired lift strictly above zero.
- At least 50% of active event months have positive summed net return.

If no horizon passes both chronological gates, reject or rethink the event definition. Do not tune the validation period or inspect the final 15%.

## Interpretation limits

This is an event study without stop/target rules. R is not applicable; event-sequence drawdown and PF are descriptive forward-return statistics, not account-equity results. A gate pass only authorizes a separate preregistered stop/target execution study; it does not validate or promote a strategy. No production, main-branch, alert or order changes are authorized.
