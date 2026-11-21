# Binance ETHUSDT 15m EMA20 / completed-4H regime cross-exchange replication

**Run:** [GitHub Actions 44635977816](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44635977816)  
**Artifact:** 14583462052 · ZIP SHA-256 `92ce6f2d61bfe7f7075f1080fbedd89bcc481347ffb4f918e86c180cb9f23829`  
**Source CSV SHA-256:** `9f6379bb53003daa04779960095af65065127aa89f9ed46f4016d8cd28c50f59`  
**Decision:** 1h definition rejected; 4h point estimate is interesting but statistically inconclusive. No strategy promotion.

## Data integrity

- Instrument: Binance USDⓈ-M ETHUSDT perpetual, 15-minute klines.
- Downloaded exactly 53 official archive periods: 38 daily and 15 monthly.
- All 53 SHA-256 sidecars matched; all 53 ZIP CRC checks passed.
- 47,424 expected and observed 15-minute bars; zero duplicates, malformed rows or missing intervals.
- First bar: 2025-03-08 00:00 UTC. Last bar open: 2026-07-14 23:45 UTC.
- 2,964 complete 4-hour candles.
- Reserved period beginning 2026-07-15 00:00 UTC was not downloaded or evaluated.
- Seven deterministic tests passed, including completed-4H aggregation, future-perturbation invariance, funding-settlement grid, exact 53-archive window, ZIP/CSV parser and side/regime groupby regression.

## Frozen rules

This is a cross-exchange replication of the existing Delta event study, not an optimization.

- Completed 4H regime: close > EMA50 > EMA200 permits longs; close < EMA50 < EMA200 permits shorts; otherwise neutral.
- 15m EMA20 uses adjust=False and 20-bar warm-up. ATR14 is Wilder RMA, reset at data gaps.
- Long: previous close <= previous EMA20; current low within ±0.10 × ATR14 of EMA20; current close > EMA20 and candle open; completed 4H regime bullish. Short is the exact inverse in a bearish regime.
- Entry at the next 15m open. One global event per 8 hours.
- Fixed forward horizons: 1h and 4h. Outcomes reaching or crossing the next 00:00/08:00/16:00 UTC funding boundary are excluded; funding cashflows are not applied.
- One deterministic non-signal control per event, matched on UTC day, side, completed 4H regime and 3h UTC bucket, without replacement. Controls within ±1h of any raw qualifying signal are excluded.
- Cost sensitivity: 4/7/10/20 bps round trip; 10 bps primary.
- 5,000 day-cluster bootstrap resamples. No parameter search.

## Results at 10 bps round-trip cost

| Metric | 1h | 4h |
|---|---:|---:|
| Qualifying events | 17 | 17 |
| Matched event/control pairs | 16 | 16 |
| Win rate on matched events | 37.50% | 43.75% |
| Descriptive PF | 0.437 | 2.198 |
| Mean event return, net | -17.08 bps | +30.18 bps |
| Median event return, net | -18.96 bps | -13.18 bps |
| Matched control mean, net | -6.03 bps | -4.93 bps |
| Paired event-minus-control lift | -11.05 bps | +35.11 bps |
| Event-mean 95% day-cluster CI | [-44.50, +10.27] | [-20.91, +91.27] |
| Paired-lift 95% day-cluster CI | [-53.59, +24.71] | [-14.20, +92.77] |
| Positive months | 2/8 | 5/8 |
| Positive non-empty 2-month folds | 1/5 | 3/5 |
| Maximum losing streak | 4 | 4 |
| Event-sequence drawdown | -441.28 bps | -239.52 bps |

The event-sequence drawdown is a fixed-horizon return-sequence diagnostic, not an account-equity drawdown. R, stop-based PnL and executable account drawdown are not applicable because this is an event study without stops or targets.

## Outlier sensitivity

The positive 4h mean is highly concentrated:

- Full matched sample: +30.18 bps mean, 2.198 PF.
- Remove the single largest winner: +10.87 bps mean, 1.404 PF.
- Remove the two largest winners: -2.80 bps mean, 0.903 PF.
- Remove the three largest winners: -17.96 bps mean, 0.421 PF.

The 4h median is negative despite the positive mean. Only 16 event/control pairs were available. The 1h result is negative. Long-side observations comprise only two matched events and both are negative; most observations are short/bear-regime events.

## Cost sensitivity

| Round-trip cost | 1h event mean | 4h event mean | 4h control mean |
|---:|---:|---:|---:|
| 4 bps | -11.08 | +36.18 | +1.07 |
| 7 bps | -14.08 | +33.18 | -1.93 |
| 10 bps | -17.08 | +30.18 | -4.93 |
| 20 bps | -27.08 | +20.18 | -14.93 |

All values are bps on the 16 matched observations. The paired event-minus-control lift is unchanged by a common flat cost deduction.

## Interpretation and decision

The Binance 4h mean (+30.18 bps) is directionally similar to the prior Delta point estimate (+35.51 bps), which is worth recording as cross-exchange descriptive consistency. It is not robust evidence of an edge: both event-mean and paired-lift confidence intervals cross zero, the median is negative, and removing two large winners makes the mean negative. The event sample is underpowered and concentrated in short/bear conditions.

- **1h:** reject this exact event definition at the tested costs.
- **4h:** inconclusive; retain only as a research observation. Do not run a stop/target grid, optimize thresholds, choose a side, or inspect the reserved final four months based on this result.
- No strategy is validated or promoted.

## Limitations

- Fixed-horizon event study, not an executable strategy backtest.
- No stop/target, position sizing, account equity or account-level drawdown.
- Funding-boundary-crossing outcomes are excluded, but funding cashflows are not applied.
- Flat round-trip cost assumptions are not fee-tier verified; no explicit spread, market impact or variable slippage model.
- Controls are matched descriptive comparators, not randomized controls.
- The final four-month holdout remains untouched.

Detailed monthly, chronological-fold, cost and side/regime tables are committed alongside this report. Full source and trade/control CSVs remain in the 30-day GitHub Actions artifact.

## Independent rerun reproducibility check

A second PR-triggered run, [44636199588](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44636199588), also completed and uploaded artifact [14584126868](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44636199588/artifacts/14584126868). The second ZIP was downloaded and extracted. All 14 files were byte-identical to the first artifact, including the source 15m CSV, 53-entry archive manifest, events, controls, event/control returns, monthly results, folds, side/regime and cost tables, report, metadata and summary. The source SHA-256 was identical. The two ZIP container digests differ because the ZIP archives were generated separately; their extracted file contents are identical.

The second full run was already queued under the prior pull-request trigger guard. The workflow was subsequently tightened so pull requests and ordinary pushes run deterministic tests only; a full archive replication now requires manual workflow dispatch or the explicit marked push.
