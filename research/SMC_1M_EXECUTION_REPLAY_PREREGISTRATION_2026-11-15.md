# BTC SMC 5m entry / 1m execution replay — preregistration (2026-11-15)

## Purpose

The 2026-11-15 5m OHLC ambiguity audit found no bars that spanned both stop and target in the 48-configuration train/validation matrix. That does not prove the intrabar path: 5m OHLC can conceal minute-level ordering. This follow-up freezes the two diagnostic configurations from the completed SMC study and replays their exits using Delta BTCUSD traded-price 1m candles.

This is an execution-resolution audit, not a new strategy search. It does not change the signal definition, entry timestamps, candidate selection, or promotion status.

## Frozen candidates

1. `best_train_candidate`: external pivot strength 3; local pivot strength 3; MSS wait 8 15m bars; 5m next-open entry; structural stop at sweep-to-MSS extreme (0 ATR buffer); 1.5R target; no 4h filter; both directions; all hours.
2. `best_validation_diagnostic_not_selected`: same signal and entry; 0.1 ATR stop buffer; 2R target; no 4h filter; both directions; all hours. This row is an audit diagnostic only and is not eligible for promotion because it did not pass the training gate.

Both candidates use the original 5m-generated signals and entries. The 1m data is used only to determine the first exit touch and time exit.

## Data and execution

- Instrument: Delta Exchange India BTCUSD perpetual traded-price candles.
- Data: 730-day 1m history, plus the matching 5m signal/entry history.
- API: public `GET /v2/history/candles`, `resolution=1m`; API documents a maximum of 2,000 candles per response. Requests will be chunked below that limit.
- Preserve timestamps in UTC; sort returned rows; remove duplicate timestamps; reject invalid OHLC; do not fill missing minutes.
- Require contiguous 1m bars from the 5m entry timestamp through the full 5m exit bar. If a minute is missing before a touch, mark the trade unresolved rather than infer a path.
- Keep the 5m entry price, stop and target fixed. On each 1m bar, resolve opening gaps first, then intrabar touches. If the 1m bar opens between stop and target and spans both, headline replay is stop-first and an optimistic target-first bound is reported.
- Compare aggregated 1m OHLC against native 5m OHLC on complete aligned 5m buckets. Report coverage and all mismatches; do not silently substitute one feed for the other.
- Replay maximum hold remains 4 hours. If no stop/target is hit, exit at the last complete 1m close in the 4-hour window.
- Recalculate 6/12/20 bps round-trip cost sensitivities. Funding, spread and market-impact cashflows remain excluded and explicitly disclosed.

## Evaluation

- Reproduce the original chronological 70/15/15 row-index split for comparability. Do not evaluate OOS because the preceding 5m study had zero validation passes.
- Report resolved and unresolved trades, 1m gaps, 1m ambiguous bars, 1m outcome, win rate, PF, net R, average R, drawdown, losing streak, positive-month fraction, 1m-vs-5m OHLC alignment, and cost sensitivity.
- No parameter changes, no selection based on validation, no new direction/session filters, and no production promotion.
- If 1m coverage or 1m/5m OHLC reconciliation is inadequate, retain the original 5m conservative result and label the 1m replay inconclusive.

## Decision rule

This audit can improve execution realism; it cannot turn a failed validation into a validated strategy. The SMC setup remains experimental and no execution alerts or live orders are enabled.

Official API reference: https://docs.delta.exchange/
