# ETHUSDT 15m Supertrend intraday cross-asset replication — preregistration

Date: 2026-11-20
Branch: `ai-quant-rebuild`
Status: preregistered; no market result until the full archive workflow and artifact are inspected.

## Motivation and prior-art boundary

BTC 15m Supertrend studies already tested broad indicator/entry/session matrices and found zero validation-passing configurations. This study does not retune those BTC results. It tests one conventional, frozen Supertrend baseline on a different liquid crypto instrument (ETHUSDT) using official Binance USD-M historical klines. The purpose is cross-asset falsification/generalization, not selecting an ETH-specific winner.

The previous BTC 8h intraday study is not directly comparable on holding horizon. To avoid silently omitting perpetual funding, this ETH study uses a 4h maximum holding period and excludes entries whose full 4h maximum horizon reaches or crosses the next 00:00/08:00/16:00 UTC funding settlement. This is a causal entry-time exclusion; no funding cashflow is imputed.

## Frozen rules

- Instrument/source: Binance USD-M ETHUSDT perpetual, official 15m kline archives.
- Data window: 2025-03-08 00:00 UTC inclusive to 2026-07-15 00:00 UTC exclusive. Do not download or inspect data at/after the end boundary.
- Indicator: existing `research/supertrend_intraday_backtest.py` implementation; HL2 source, Wilder ATR(10), multiplier 3.0, TradingView-style final-band recurrence.
- Signal: confirmed 15m Supertrend direction flip at completed candle close.
- Entry: next 15m open.
- Direction: both long and short; no direction-specific selection.
- Stop: fixed Supertrend line from the signal candle.
- Target: fixed 2R.
- Holding cap: 16 bars / 4 hours; exit at the final completed bar close if neither stop nor target is touched.
- Position concurrency: one position at a time.
- Session: all UTC hours; no session optimisation.
- Funding exclusion: discard a signal if entry time + 4 hours is greater than or equal to the next 00:00/08:00/16:00 UTC settlement timestamp. Report excluded-signal counts by UTC hour. This avoids applying an unverified historical funding cashflow model.
- Execution: same-bar stop/target ambiguity resolved stop-first; adverse gap-through stop fill; target fills at target without favourable gap improvement; no trade crosses a data gap or chronological split; skip non-positive or >5% initial stop risk.
- Costs: 12 bps round trip primary; recalculate identical gross trades at 6 and 20 bps. Flat cost is an assumption, not a verified fee tier. No separate spread/slippage/market-impact model.
- Risk unit: initial entry-to-stop distance. Report net R, not account return.

## Chronological evaluation

- Split the verified contiguous source rows chronologically 70% development / 15% validation / 15% final holdout.
- Compute indicators causally on completed candles. Signals enter only on the next candle open.
- Development gate: at least 40 trades, net R > 0, PF >= 1.05, max drawdown >= -25R, and at least 50% positive active months.
- Validation gate: at least 20 trades, net R > 0, PF >= 1.05, max drawdown >= -15R, and at least 50% positive active months.
- Evaluate the final holdout once only if the single frozen configuration passes both gates. Otherwise record OOS as not evaluated.
- No parameter grid, no long/short subgroup selection, no session selection, and no tuning after viewing validation.

## Required outputs

Archive count and checksums; ZIP CRC; source SHA-256; row count/date coverage; missing/duplicate/invalid candle counts; funding-excluded signal count; split boundaries; trade ledger; cost sensitivity; trade count, win rate, PF, net R, average R, max drawdown, longest losing streak, TP/SL/TIME counts; monthly and completed-4h bull/bear/neutral attribution; ambiguous stop/target bar count; and exact code/test metadata.

## Known limitations

This is one cross-asset baseline, not proof that all Supertrend methods work or fail. OHLC cannot reveal intrabar ordering beyond the conservative stop-first rule. The funding exclusion reduces the eligible entry-time population and may change session composition; the excluded counts must be disclosed. Flat costs do not represent actual maker/taker fees, spread, variable slippage or market impact. A passing result would still require prospective paper observation and a separate fee/funding execution audit before promotion.

No production rules, live alerts, exchange orders, or `main` branch changes are permitted.
