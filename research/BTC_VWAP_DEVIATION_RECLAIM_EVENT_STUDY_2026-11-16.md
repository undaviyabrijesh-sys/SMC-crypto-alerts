# BTC 5m UTC-day VWAP deviation/reclaim event study — completed 2026-11-16

## Decision

**Reject the frozen VWAP deviation/reclaim event definition as a tradable candidate.** Absolute forward returns were negative after the primary 12 bps assumed round-trip cost in both development and validation at both 1h and 4h horizons. The 1h event-minus-control lift was positive, but that did not translate into positive absolute expectancy. The 4h lift was positive in development and slightly negative in validation, with a confidence interval spanning zero. The final 15% remains untouched.

This was a forward-return event study, not a stop-defined trading system. R is not applicable. Event-sequence drawdown and PF are descriptive statistics, not an account-equity backtest.

## Reproducibility and workflow

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts`
- Branch: `ai-quant-rebuild`
- Frozen preregistration: `research/BTC_VWAP_DEVIATION_RECLAIM_PREREGISTRATION_2026-11-16.md`
- Code: `research/btc_vwap_deviation_event_study.py`
- Workflow: [43823543440](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43823543440)
- Artifact: [14205532400](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43823543440/artifacts/14205532400)
- Workflow conclusion: success. Python compilation, synthetic VWAP reset, future-perturbation/no-lookahead, gap segmentation, event-timing and matching tests passed. Historical download, event computation, summary publication and artifact upload completed.
- The first push-triggered run [43823460606](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43823460606) failed its synthetic event test before downloading market data because the synthetic rejection candle was accidentally bullish. The test candle was corrected and the successful rerun above is authoritative. No market result is taken from the failed run.
- Artifact digest reported by GitHub: `sha256:c5381889c8b71928c244761fea6616211f99b87f7d38d8bb31c957bb2e15030f`.

## Dataset

- Instrument: Delta Exchange India BTCUSD perpetual, traded-price OHLCV.
- Native timeframe: 5m.
- Coverage: 2024-11-16 07:25 UTC to 2026-11-16 07:15 UTC.
- Source rows: 210,238; valid closed rows: 210,237.
- Duplicates removed: 0.
- Invalid timestamps/OHLC/shape: 0.
- Missing volume: 0; zero-volume candles: 332.
- 5m gaps: 1; largest gap: 15 minutes. Any forward horizon crossing a segment boundary was excluded.
- Normalized-data SHA-256: `249e204a8c7746ef27dc790941f9ce31145438f5bbaf5a7abf28f6741590a9b8`.
- Chronological split by valid 5m row index: 70% development (end row 147,165), 15% validation (end row 178,701), final 15% untouched (rows 178,701–210,236). OOS was not evaluated.

## Frozen rules

- UTC calendar-day VWAP reset, using cumulative typical-price `(H+L+C)/3` multiplied by traded volume and divided by cumulative volume.
- Wilder ATR(14) normalizer uses only bars completed before the signal candle (one-bar shift).
- Primary 1.5 ATR upper event: previous close at least +1.5 ATR above its own day VWAP; current close re-enters below +1.5 ATR but remains above VWAP; current candle is bearish and closes in the lower half. Short signal.
- Primary 1.5 ATR lower event: previous close at least -1.5 ATR below VWAP; current close re-enters above -1.5 ATR but remains below VWAP; current candle is bullish and closes in the upper half. Long signal.
- Entry reference: next 5m open after the signal candle closes.
- One global event stream and 8-hour cooldown across directions.
- 2.0 ATR threshold was a predeclared robustness diagnostic only; it was not eligible to replace the primary threshold.
- Completed 4h EMA50/EMA200 regime was used for matching/attribution only, not as an entry filter.
- Forward horizons: 1h (12 completed 5m bars) and 4h (48 bars), measured from next-bar entry open to the corresponding final close. Both horizons had to remain inside the chronological sample and contiguous data segment.

## Matched controls

- Controls: non-event moderate deviations with prior close between 0.5 and 1.0 ATR above/below VWAP, same directional rejection candle, and current close still at least 0.25 ATR from VWAP.
- 1:1 matching without replacement by exact UTC date, side, completed 4h EMA50/EMA200 regime and 3-hour UTC bucket.
- Controls within ±30 minutes of any event entry in the same sample were excluded; nearest timestamp chosen, earlier timestamp breaks ties.
- Paired confidence intervals: 2,000 UTC-day cluster bootstrap replicates, fixed seed 20261116.
- Round-trip cost assumptions: 6/12/20 bps; 12 bps primary.
- Funding excluded because historical settlement cashflow mapping remains unverified. Spread, market impact and slippage were not separately modelled.

## Primary 1.5 ATR results at 12 bps

| Metric | Development 1h | Development 4h | Validation 1h | Validation 4h |
|---|---:|---:|---:|---:|
| Events | 1,138 | 1,138 | 235 | 235 |
| Matched pairs | 349 | 349 | 73 | 73 |
| Win rate | 35.50% | 43.85% | 28.51% | 42.98% |
| Profit factor | 0.482 | 0.730 | 0.367 | 0.721 |
| Mean net return | -12.23 bps | -10.76 bps | -13.75 bps | -9.15 bps |
| Median net return | -11.46 bps | -7.75 bps | -12.62 bps | -10.70 bps |
| Event-sequence max drawdown | -14,143.39 bps | -13,012.96 bps | -3,289.91 bps | -2,381.34 bps |
| Longest losing streak | 13 | 13 | 16 | 8 |
| Positive active months | 1/18 | 2/18 | 0/4 | 1/4 |

Event-sequence drawdown is the cumulative sum of event returns measured against prior peaks; it is not a deployable account-equity curve. R is not applicable because there are no stop/target rules.

### Cost sensitivity — mean net return

| Horizon | Development 6 / 12 / 20 bps | Validation 6 / 12 / 20 bps |
|---|---:|---:|
| 1h | -6.23 / -12.23 / -20.23 bps | -7.75 / -13.75 / -21.75 bps |
| 4h | -4.76 / -10.76 / -18.76 bps | -3.15 / -9.15 / -17.15 bps |

Every primary-threshold absolute result was negative, even at 6 bps.

## Matched-control lift

| Horizon | Development lift (95% CI) | Validation lift (95% CI) |
|---|---:|---:|
| 1h | +12.11 bps (+7.19, +17.32) | +11.35 bps (+3.06, +20.85) |
| 4h | +8.88 bps (+2.31, +15.36) | -0.68 bps (-9.14, +7.66) |

The 1h event group outperformed the matched moderate-deviation controls in both periods, but its own absolute net returns were materially negative. The 4h relative lift did not persist into validation. This is not evidence of a profitable strategy.

## Robustness and regime observations

- The predeclared 2.0 ATR diagnostic also had negative absolute development and validation mean returns at 12 bps: 1h -15.43/-11.50 bps and 4h -17.42/-6.08 bps (development/validation). It did not improve the primary conclusion.
- At 12 bps, all completed 4h EMA regimes (bull, bear, neutral) had negative mean net event returns for the primary 1.5 ATR threshold in both development and validation.
- Long and short side/regime attribution was also negative across the reported groups. Do not select a post-hoc side or regime subset.
- Development 4h had only two positive active months, with February 2026 accounting for the only substantial positive monthly contribution; validation 4h had one positive month (June 2026). Monthly consistency fails the frozen 50% gate.

## Frozen gate and decision

The primary 1.5 ATR threshold had sufficient event and matched-pair counts, and 1h matched-control lift confidence bounds were positive. Nevertheless:
- Absolute mean net returns failed in development and validation at both horizons.
- Positive-month fractions failed the 50% requirement in both periods.
- 4h validation paired lift was not positive and its confidence interval crossed zero.

**Neither horizon passed both chronological gates. Reject this event definition as tested.** Do not tune validation, choose post-hoc long/short or regime subsets, or inspect the final 15% to search for a winner.

## Next research step

A separate hypothesis is preregistered in `research/BTC_PREV_DAY_RANGE_BREAK_RETEST_PREREGISTRATION_2026-11-16.md`: a completed 15m break of the prior UTC-day high/low followed by a 5m retest-and-hold confirmation. It is not yet backtested. The first implementation will use a small frozen matrix, chronological 70/15/15 splits, 6/12/20 bps costs, conservative same-bar stop-first handling and a 4-hour intraday cap.

No main-branch, production, approved-strategy, live-alert or exchange-order changes were made.
