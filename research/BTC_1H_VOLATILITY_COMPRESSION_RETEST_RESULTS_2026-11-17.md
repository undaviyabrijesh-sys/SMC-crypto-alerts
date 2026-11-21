# BTC 1H volatility-compression release → 15M retest continuation — results (2026-11-17)

## Decision

**REJECT / INSUFFICIENT SAMPLE.** The preregistered 2R primary configuration failed the development gate materially and the validation sample was far below the minimum trade count. The untouched final 15% was not loaded into the feature pipeline and was not evaluated.

## Prior-art / duplication audit

Before testing, the `ai-quant-rebuild` branch was inspected:

- `research/squeeze_breakout_intraday_backtest.py` already tests 15m Bollinger-inside-Keltner squeeze runs, 15m Donchian close breaks, next-open entries, multiple stops/targets, sessions and direction filters. It is a broad 15m squeeze-breakout matrix.
- `research/btc_volatility_compression_expansion_event_study.py` already tests 15m realized-volatility compression followed by true-range expansion and a prior-16-bar close break. It is a forward-return event study, not a stop-defined retest strategy.

This experiment is a distinct, narrower variant: 1h Bollinger-bandwidth percentile compression, a 1h break of the prior 20 completed hours, then a 15m retest-and-hold entry with a retest-structure stop and a funding-safe maximum hold. It does not duplicate either existing rule set, but belongs to the same broad volatility-compression/breakout family. The negative result should be therefore be considered alongside those earlier studies rather than treated as an entirely independent family discovery.

## Data and split

- Instrument: Delta BTCUSD perpetual, traded-price OHLCV.
- Source: the frozen BTC 5m CSV embedded in PDRT historical artifact from workflow [43857702736](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43857702736), artifact [14221154137](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43857702736/artifacts/14221154137).
- Source rows: 210,239; 2024-11-16 11:30 UTC through 2026-11-16 11:20 UTC.
- Source SHA-256: `5b612e1c496f16277b459f58ddff33b69d8f7912b70d8f733f0a17be844eb4fb`.
- Data quality: zero 5m gaps, zero duplicate timestamps, zero malformed OHLC rows, 334 zero-volume bars retained.
- Complete bars built from contiguous 5m constituents: 59,570 x 15m; 14,892 x 1h; 3,723 x 4h.
- Chronological boundaries rounded up to UTC 4h boundaries: development ends 2026-04-11 12:00 UTC; validation ends 2026-07-30 00:00 UTC. The 31,529 source rows at/after the validation boundary were not loaded into the feature pipeline; no OOS result exists.

## Frozen rules implemented

1. Build 1h Bollinger bandwidth from 20 completed 1h closes: `(upper - lower) / middle`, with 2 population standard deviations.
2. A completed 1h bar is compressed when its bandwidth is at/below the 20th percentile of the preceding 100 completed bandwidth observations; at least 80 valid prior observations are required. The threshold is shifted/prior-only.
3. Treat a contiguous run of compressed hours as one compression episode. Only the first completed 1h bar after that episode can be the release bar, avoiding repeated signals from one squeeze.
4. The release bar must close above the prior 20 completed 1h highs by at least 0.05 prior 1h ATR(14), or below the prior 20 completed 1h lows by the same buffer. Range and ATR are shifted; the breakout candle does not define its own level.
5. Within the next eight completed 15m bars, wait for a retest within 0.15 prior 15m ATR(14) of the broken level, a close back on the breakout side and in the directional half of the candle. Enter at the following 15m open only if it remains on the breakout side.
6. Stop beyond the retest extreme by 0.10 prior 15m ATR(14); skip stop distance above 2.5 prior 15m ATR.
7. Compare 1.5R, 2R (preregistered primary) and 3R fixed targets. Maximum hold four hours, but exit at the last 15m close strictly before the next UTC 00:00/08:00/16:00 funding boundary. One open position globally per target configuration.

## Execution and costs

- Same-bar stop/target: stop first.
- Stop gap-through: fill at the worse opening price; target gap: fill at target.
- A missing 15m interval inside the planned trade horizon causes the trade to be excluded; source data had no 5m gaps.
- Round-trip cost sensitivities: 4/7/10/20 bps. Primary assumption: 10 bps, consistent with the public base taker/taker headline rate, not verified against the user's account tier. Cost is applied to average entry/exit notional relative to initial price risk.
- Funding cashflows excluded; positions are capped strictly before the next scheduled funding boundary. Spread, slippage and market impact are not separately modelled.

## Deterministic tests

Eight test groups passed: complete-bar aggregation rejects missing 5m constituents; Wilder ATR future perturbation; Bollinger/quantile future perturbation; compression episode boundaries; retest timing and next-open entry; strict funding-safe exit; same-bar stop-first and adverse gap stop; and sample-boundary isolation. Python compilation also passed.

## Results at 10 bps round-trip cost

### Primary 2R configuration

| Metric | Development | Validation |
|---|---:|---:|
| Candidate entries | 31 | 4 |
| Executed trades | 29 | 4 |
| Net-profitable trade rate | 17.24% | 50.00% |
| Profit factor | 0.178 | 1.093 |
| Gross R | -11.643R | +2.000R |
| Net R | **-24.900R** | **+0.303R** |
| Average net R/trade | -0.8586R | +0.0757R |
| Maximum trade-sequence drawdown | -24.900R | -1.870R |
| Longest losing streak | 9 | 1 |
| Positive active months | 1/13 | 1/3 |
| TP / SL / time exits | 4 / 20 / 5 | 2 / 2 / 0 |

### Target diagnostics at 10 bps

| Target | Sample | Trades | Net win rate | PF | Net R | Max DD | Losing streak | Positive active months |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1.5R | Development | 29 | 17.24% | 0.111 | -26.900R | -26.900R | 9 | 1/13 |
| 1.5R | Validation | 4 | 50.00% | 0.786 | -0.697R | -1.870R | 1 | 1/3 |
| 2R | Development | 29 | 17.24% | 0.178 | -24.900R | -24.900R | 9 | 1/13 |
| 2R | Validation | 4 | 50.00% | 1.093 | +0.303R | -1.870R | 1 | 1/3 |
| 3R | Development | 29 | 13.79% | 0.229 | -24.897R | -24.897R | 10 | 1/13 |
| 3R | Validation | 4 | 25.00% | 0.396 | -2.371R | -2.371R | 2 | 0/3 |

### Primary 2R cost sensitivity

| Round-trip cost | Development net R | Validation net R |
|---:|---:|---:|
| 4 bps | -16.946R | +1.321R |
| 7 bps | -20.923R | +0.812R |
| 10 bps | -24.900R | +0.303R |
| 20 bps | -38.156R | -1.395R |

Development was materially negative even at the optimistic 4 bps assumption. Validation's small positive result comes from four trades and is not persuasive.

### Side and regime diagnostics (2R, 10 bps)

- Development: 11 longs -10.605R (PF 0.155); 18 shorts -14.294R (PF 0.194).
- Validation: 2 longs +0.324R (PF 1.233); 2 shorts -0.021R (PF 0.989).
- Development 4h regime: bear 15 trades -10.608R; bull 13 trades -13.021R; unknown 1 trade -1.271R.
- Validation 4h regime: bear 2 trades -0.021R; bull 2 trades +0.324R,
- These subgroup samples are too small for filter selection; no side/regime variant is promoted.
- Gate: 2R required >=30 development trades and >=12 validation trades, positive net R, PF >=1.05, max DD no worse than -20R development/-10R validation, and >=50% positive active months in both. Development failed all but the lossing-streak constraint (29 trades, -24.900R, PF 0.178, DD -24.900R, 1/13 positive months); validation had only 4 trades and 1/3 positive active months. **Decision: reject / insufficient sample; do not inspect OOS, tune validation, or promote post-hoc side/regime subsets.**
- No main, production, approved-strategy, live-alert or exchange-order changes.
