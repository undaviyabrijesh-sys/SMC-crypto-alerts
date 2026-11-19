# Binance BTCUSDT 1H EMA20/50 cross-exchange replication — preregistration

Frozen: 2026-11-19 UTC
Branch: ai-quant-rebuild
Status: preregistered; Binance market results not inspected at freeze time.
Purpose: venue-robustness replication of one Delta BTCUSD configuration, not an independent temporal OOS test.

## Hypothesis

The single development-ranked Delta configuration (EMA20/EMA50 crossover, 1.5 × Wilder ATR14 stop, 3R target, no 4H filter) may produce similar behaviour on Binance USD-M BTCUSDT. The prior Delta experiment failed its development promotion gate; this replication is descriptive and cannot promote the strategy by itself.

## Frozen configuration — no parameter search

- Venue/instrument: Binance USD-M BTCUSDT perpetual.
- Source: Binance 5-minute klines; aggregate to complete UTC-aligned 1-hour bars using exactly 12 contiguous 5-minute bars, matching the Delta study construction. Bars are right-labelled by exact close time.
- Signal: completed 1H EMA20 crosses above EMA50 for long; crosses below for short.
- Entry: next 1H bar open, equal to the signal bar close timestamp.
- Stop: signal close minus/plus 1.5 × Wilder ATR(14), anchored to signal close.
- Target: fixed 3R using actual next-open entry and initial stop distance.
- Direction: both long and short.
- Filter: none. A completed 4H EMA200 regime is recorded for diagnostics only, not used for entries.
- Positioning: one position at a time; no overlapping trades.
- Maximum hold: last complete 1H candle close strictly before the next actual Binance fundingTime timestamp.
- Funding: use actual historical Binance funding timestamps to define safe exits; assert no position overlaps a settlement. Do not apply funding cashflow because no position is held at settlement.
- Execution: same-bar stop wins if stop and target are both touched; adverse stop gap fills at the worse open; favourable target gap is capped at target; no trade crosses a data gap or sample boundary.
- Costs: assumed 4/7/10/20 bps round trip; 10 bps primary. No user-specific fee tier, spread, slippage, impact or queue-position model.
- Stop-risk cap: skip if initial stop distance exceeds 8% of entry.

## Dates and partitions

- Warm-up 5-minute data starts 2024-11-16 00:00 UTC.
- Evaluation starts 2025-09-08 12:00 UTC, matching the post-funding-mechanism transition used in the Delta study.
- Development: [2025-09-08 12:00, 2026-07-07 13:00) UTC.
- Validation: [2026-07-07 13:00, 2026-09-10 06:00) UTC.
- Final OOS after 2026-09-10 06:00 UTC is not evaluated. A 12-hour data buffer after validation end is used only to establish funding boundaries and exclude positions that would cross the split; no post-validation signal or trade is simulated.
- The same calendar boundaries are used as the frozen Delta experiment. Because dates overlap, this is cross-exchange venue-robustness evidence, not independent temporal OOS.

## Frozen Delta reference — same exact configuration, 10 bps

- Development: 106 trades, 41.51% profitable, PF 0.950, -1.90R net, -11.32R max drawdown, 9-trade maximum losing streak, 6/11 positive active months.
- Validation: 27 trades, 62.96% profitable, PF 2.338, +7.99R net, -2.76R max drawdown, 5-trade maximum losing streak, 2/3 positive active months.
- It failed development promotion criteria and had a small validation sample. No selection or retuning is permitted on Binance.

## Promotion gate — diagnostic only

At 10 bps, require both development and validation to have:
- at least 50 development trades and 20 validation trades;
- PF > 1.10 and net R > 0;
- at least 50% positive active months;
- max drawdown no worse than -20R development and -10R validation.

Passing this gate would still not make the strategy validated: an independent future holdout and prospective paper-trading period would remain necessary.

## Required outputs

- Source 5-minute klines, aggregated complete 1-hour bars and funding-rate history, SHA-256 hashes and coverage/gap metadata.
- Trade ledger with entry/stop/target/exit, side, signal/entry/exit timestamps, next funding timestamp, gross R, net R at each cost, outcome and bars held.
- Development/validation summaries, cost sensitivity, monthly stability, 4H-regime and side breakdowns, max drawdown, maximum losing streak and funding-overlap assertion.
- Deterministic tests inherited from the frozen Delta engine for right-labelled bar/next-open alignment, Wilder ATR seed, future-perturbation invariance, stop-first/gap fills, funding-safe exit and split isolation, plus actual funding-time lookup.

## Explicit limitations

- The underlying Delta candidate failed development at 10 bps; Binance replication cannot erase that failure.
- Historical dates overlap Delta; not an independent time holdout.
- Funding cashflow is not applied because trades are closed before settlements; fee tier, spread, slippage, market impact and queue position are not modelled.
- 1H OHLC cannot resolve intrabar ordering beyond the conservative stop-first assumption.
- This experiment is research-only. No production rule, live alert or exchange order is changed or emitted.
