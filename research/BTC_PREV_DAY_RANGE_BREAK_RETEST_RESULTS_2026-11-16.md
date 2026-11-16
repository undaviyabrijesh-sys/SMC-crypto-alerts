# BTC prior-UTC-day range break/retest — completed, rejected

Date: 2026-11-16 UTC  
Branch: \`ai-quant-rebuild\`  
Workflow: [43857702736](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43857702736)  
Artifact: [14221154137](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43857702736/artifacts/14221154137)

## Frozen hypothesis and rules

A completed 15m close beyond the previous completed UTC-day high/low, followed by a 5m retest-and-hold, may distinguish accepted range expansion from a failed breakout.

- Long breakout: completed 15m close at least 0.10 prior 15m ATR(14) above the previous completed UTC-day high.
- Short breakout: symmetric close below the previous completed UTC-day low.
- Prior-day high/low is available only after the full prior UTC day closes. A prior day is accepted only with exactly 288 contiguous 5m candles; incomplete days are not used.
- Within the next 12 complete 5m candles, price must revisit the level within 0.15 prior 5m ATR(14), close back on the breakout side and in the directional half of its range.
- Entry: next 5m open. Cancel if that open is back inside the prior-day range.
- Stop: beyond the retest candle extreme by 0.10 prior 5m ATR. Skip non-positive risk or risk above 2.5 ATR.
- Targets: 1.5R, 2R and 3R. Maximum hold: 4 hours. One open position per configuration and at most one candidate per UTC day per direction.
- Same-bar stop/target ambiguity: stop first. Stop gaps fill at the worse open; target gaps fill at target. A data gap before first exit makes the path unresolved; unresolved paths are excluded and reserve the full 4-hour window before another entry.

The 1H/4H features are attribution only, not entry filters.

## Dataset and validation

- Source: Delta Exchange India BTCUSD perpetual, traded-price OHLCV, native 5m.
- Coverage: 2024-11-16 11:30 UTC to 2026-11-16 11:20 UTC.
- 210,240 source rows; 210,239 valid closed candles.
- Zero duplicates, invalid timestamps, malformed OHLC, missing volume or 5m gaps; 334 zero-volume candles retained.
- Derived complete bars: 70,079 15m and 4,379 4h; 729 complete prior UTC days.
- Normalized 5m SHA-256: \`bfcaa7a0a081246a9e8ec0dcaca0d01c25e793b250e8399699bddf2c7f0756e3\`.
- Chronological row split: 70% development, 15% validation, final 15% untouched.
- 295 candidate entries were generated. Each target produced 207 development trades and 43 validation trades. Zero unresolved holding paths.
- The synthetic tests passed for prior-day level availability/no-lookahead, 5m retest entry, gap segmentation, stop-first ambiguity and unresolved gap paths. The full historical workflow completed and its artifact was downloaded and inspected.

## Results at 12 bps assumed round-trip cost

| Target | Sample | Trades | Win rate | PF | Net R | Avg R/trade | Max DD | Max losing streak | Positive months |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.5R | Development | 207 | 33.33% | 0.229 | -187.29R | -0.905R | -188.21R | 10 | 0/18 |
| 1.5R | Validation | 43 | 34.88% | 0.222 | -37.30R | -0.868R | -38.38R | 7 | 0/4 |
| 2R | Development | 207 | 27.05% | 0.273 | -193.33R | -0.934R | -194.75R | 13 | 0/18 |
| 2R | Validation | 43 | 34.88% | 0.337 | -33.30R | -0.775R | -35.88R | 7 | 0/4 |
| 3R | Development | 207 | 23.19% | 0.358 | -183.39R | -0.886R | -185.80R | 21 | 1/18 |
| 3R | Validation | 43 | 37.21% | 0.559 | -23.30R | -0.542R | -28.81R | 5 | 1/4 |

All target variants had 112 long / 95 short development trades and 26 long / 17 short validation trades.

## Cost sensitivity — net R

| Target | Development at 6 / 12 / 20 bps | Validation at 6 / 12 / 20 bps |
|---:|---:|---:|
| 1.5R | -94.65 / -187.29 / -310.82 | -15.15 / -37.30 / -66.84 |
| 2R | -100.69 / -193.33 / -316.86 | -11.15 / -33.30 / -62.84 |
| 3R | -90.74 / -183.39 / -306.92 | -1.15 / -23.30 / -52.84 |

Even the most favourable predeclared target (3R) was negative in both periods at the lowest 6bp assumption. The 3R validation result at 6bp was close to flat but remained negative; its development result was deeply negative.

## Why costs dominate

The structural retest stops were tight relative to BTC notional:

- Median initial risk was about 0.181% of entry notional in development and 0.162% in validation.
- At 12bp round-trip cost, median cost was approximately 0.66R in development and 0.74R in validation.
- Mean cost was 0.895R per development trade and 1.030R per validation trade.

The 3R development variant was almost flat before costs (+1.91R gross across 207 trades) but lost -183.39R after the assumed 12bp round-trip cost. This is not a profitable edge that merely needs a slightly better target.

## Decision

**Reject this frozen prior-day range break/retest definition.**

No target passed the frozen development and validation gate (minimum trade counts, positive net R, PF above 1, positive average R and at least 50% positive active months in both periods). The final 15% was not evaluated. No parameter tuning or post-hoc side selection is authorised from these results.

## Limitations

- 6/12/20 bps are round-trip cost assumptions, not the user's verified Delta fee tier.
- Funding is excluded because historical settlement cashflow mapping remains unresolved.
- Spread, market impact and separate slippage are not independently modelled. This makes the negative result no less concerning.
- The study tests this exact mechanical prior-day break/retest definition, not every discretionary breakout/retest method.
- The R drawdown is a sequential fixed-1R trade-series drawdown, not a rupee account-equity simulation.

## Reproducibility and boundary

- Code: [\`research/btc_prev_day_range_break_retest_backtest.py\`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/blob/ai-quant-rebuild/research/btc_prev_day_range_break_retest_backtest.py)
- Frozen specification: [\`research/BTC_PREV_DAY_RANGE_BREAK_RETEST_PREREGISTRATION_2026-11-16.md\`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/blob/ai-quant-rebuild/research/BTC_PREV_DAY_RANGE_BREAK_RETEST_PREREGISTRATION_2026-11-16.md)
- Workflow: [\`.github/workflows/btc-prev-day-range-break-retest.yml\`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/blob/ai-quant-rebuild/.github/workflows/btc-prev-day-range-break-retest.yml)

Research only. No main-branch, production, approved-strategy, live-alert or exchange-order changes.
