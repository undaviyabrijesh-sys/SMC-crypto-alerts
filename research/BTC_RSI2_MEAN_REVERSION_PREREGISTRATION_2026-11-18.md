# BTC RSI(2) short-term mean-reversion — preregistration (2026-11-18)

## Hypothesis
Extreme two-period RSI readings on completed 15-minute candles may produce short-horizon snapback trades, with an optional completed-1H EMA200 regime filter. This is a distinct mean-reversion family from the Donchian trend-breakout experiment.

## Data and splits
- Use the same archived Delta BTCUSD perpetual 5-minute OHLCV source used in the Donchian baseline; aggregate only complete UTC-aligned 15-minute bars.
- 70% development / 15% validation / final 15% OOS by chronological row position; exact bar-aligned boundaries recorded in metadata.
- Feature warm-up may use only prior bars. Trades cannot cross partition boundaries. Reserve the full 24-hour maximum holding horizon at each split end.

## Frozen matrix (16 configurations)
- RSI: standard Wilder RSI(2), seeded with the first two-period simple average of gains/losses and updated with Wilder smoothing.
- Long threshold: RSI(2) <= 5 or <= 10.
- Short threshold: RSI(2) >= 95 or >= 90 (symmetric thresholds).
- Trend filter: off, or require latest fully completed 1H close > 1H EMA200 for longs and < EMA200 for shorts. Hourly candles must be built from completed 15-minute close timestamps; partial-hour values are prohibited.
- Entry: next 15-minute open after the signal close.
- Stop: 1.5x or 2.0x Wilder ATR(14), measured at signal close and applied from entry price.
- Target: 1.5R or 2R.
- One open position per configuration; no overlapping positions.
- Maximum holding: 24 hours (96 15-minute bars), then exit at the final bar close.
- Same-bar stop and target: stop first. Adverse stop gap-through fills at bar open; favorable target gaps are capped at target.
- Round-trip cost sensitivity: 4, 7, 10 and 20 bps of entry notional; net R = gross R minus cost_bps / initial_stop_risk_bps.
- No post-result changes to thresholds, stop, target, or regime filter.

## Promotion gate (at 10 bps round-trip cost)
At least 100 development and 30 validation trades; PF > 1.10 and net R > 0 in both; at least 55% positive active months in both. OOS is not evaluated unless a frozen configuration passes every development and validation gate. Do not select long-only, short-only or regime subsets after inspecting results.

## Required reporting
Trade count, net win rate, PF, net R, average R, trade-sequence max drawdown, max losing streak, positive/active months, long/short split, 1H EMA200 regime attribution, monthly results and all cost sensitivities.

## Limitations
Historical Delta funding cashflows and the user-specific fee tier are not present in the source archive. Funding is therefore omitted and any results are pre-funding; no candidate can be promoted without a funding-aware replay. Spread/slippage/market impact are not separately modeled beyond flat round-trip cost sensitivities.

## Decision discipline
This is a finite, predeclared mean-reversion matrix, not a search for the best threshold. Keep it on ai-quant-rebuild; do not change main, production rules, live alerts or place orders.
