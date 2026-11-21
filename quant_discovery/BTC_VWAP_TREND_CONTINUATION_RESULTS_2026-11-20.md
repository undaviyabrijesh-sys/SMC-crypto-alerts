# BTCUSD 5m UTC VWAP trend-continuation — 648-configuration research result

**Workflow:** [GitHub Actions 44636952868](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44636952868)  
**Artifact:** [14583764076](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44636952868/artifacts/14583764076) · ZIP SHA-256 `0bcea9c86fe4c7a8654577c3573c4baf8779be11998d95f97f322da0dcf8373b`  
**Source 5m CSV SHA-256:** `e8ccc36a920ee30050cc3e37881ac425591c55d257de1e0fdbe014ae3703e23d`  
**Decision:** reject this exact VWAP trend-continuation family under the preregistered gates. No OOS and no promotion.

## Data integrity

- Venue/instrument: Delta Exchange India BTCUSD perpetual, traded-price 5m OHLCV.
- 210,383 rows from 2024-11-19 11:25 UTC through 2026-11-19 23:15 UTC (last candle close 23:20 UTC).
- Zero missing intervals, duplicate rows, empty request chunks or negative-volume bars; 334 zero-volume bars.
- 106 historical requests; observed-span coverage 100%. The request's expected-candle estimate was 210,384 because its end timestamp was not aligned to a 5m boundary; the observed contiguous span contains 210,383 expected/observed candles.
- 70,127 complete 15m bars, 17,531 complete 1h bars and 4,382 complete 4h bars; one contiguous segment.
- Delta candle volume is exchange-specific and is not consolidated market-wide volume.

## Frozen strategy and matrix

- Completed 1h close > EMA50 > EMA200 for long; inverse for short.
- UTC-day anchored typical-price VWAP from completed 15m bars; four-bar VWAP slope must agree with direction and completed 15m close must be on the trend side.
- Completed 5m trigger intersects a 0.10/0.20 ATR band around the latest completed 15m VWAP. Confirmation is either close reclaim or close beyond prior 5m extreme. Entry is next 5m open.
- Relative-volume filters: none, 1.0x or 1.5x the median of the prior 20 completed 5m bars.
- Stops: signal-candle extreme, 1.0 ATR or 1.5 ATR. Targets: 1.5R, 2R or 3R. Maximum hold four hours.
- Sessions: all UTC, 07:00–13:00 UTC, 13:00–19:00 UTC. Optional completed 4h EMA50 slope filter.
- 648 configurations. Primary matrix cost 12bp assumed round trip; separate diagnostic cost recalculation at 6/12/20bp is below.
- Execution: next 5m open, same-bar stop first, adverse stop gap at worse open, target at target, reject entry if next open is through stop. One position at a time per configuration.
- Chronological 70/15/15 by row count. Train 147,268 bars; validation 31,557; OOS 31,558. Actual split bars: last train open 2026-04-14 19:40 UTC; validation starts 19:45 UTC; last validation open 2026-08-02 09:25 UTC; OOS starts 09:30 UTC. The first run's metadata labelled the first bar of the next split as the prior split's end; the split logic itself was end-exclusive and correct. A follow-up code commit corrected these metadata labels and added a boundary regression test.
- Gates: train >=40 trades, PF >=1.05, net R >0, max DD >=-20R and >=50% positive active months; shortlist top 25; validation >=20 trades, PF >=1.05, net R >0, max DD >=-12R and >=50% positive active months; OOS only after both gates.

## Matrix outcome

<badge color="danger">0 / 648 training-qualified</badge>

- 648 configurations evaluated at 12bp.
- 522 had at least 40 train trades.
- Zero configurations achieved train PF >=1.05 (maximum train PF was 1.0289).
- Only 8 had positive train net R.
- 90 met the train drawdown threshold; 20 met the positive-month fraction threshold.
- No configuration passed all training gates; therefore zero validation candidates were shortlisted and zero validation gates passed.
- OOS was not evaluated. The final 15% remains an untouched holdout in the artifact, but the strategy does not qualify to inspect it.

## Best training-net diagnostic (not eligible)

Configuration: 0.20 ATR band, reclaim-close, 1.5x prior-20 volume, signal-extreme stop, 3R target, 13:00–19:00 UTC, no 4h slope filter.

| Metric | Train | Validation diagnostic |
|---|---:|---:|
| Trades | 34 | 8 |
| Win rate | 41.18% | 12.50% |
| PF | 1.029 | 0.234 |
| Net R at 12bp | +0.864R | -7.453R |
| Max drawdown | -11.682R | -9.727R |
| Max losing streak | 5 | 7 |
| Positive months | 7/15 | 1/4 |
| TP / SL / TIME | 11 / 20 / 3 | 1 / 7 / 0 |

It fails the 40-trade minimum, PF >=1.05 and 50% positive-month requirements. Its validation diagnostic is only eight trades and is strongly negative.

## Best validation-net diagnostic with at least 20 validation trades (not eligible)

Configuration: 0.20 ATR band, break-prior-extreme, no volume filter, 1.5 ATR stop, 2R target, 07:00–13:00 UTC, no 4h slope filter.

| Metric | Train | Validation |
|---|---:|---:|
| Trades | 118 | 21 |
| Win rate | 33.90% | 42.86% |
| PF | 0.341 | 0.472 |
| Net R at 12bp | -89.960R | -10.808R |
| Max drawdown | -89.960R | -10.808R |
| Max losing streak | 11 | 3 |
| Positive months | 3/18 | 0/4 |
| TP / SL / TIME | 42 / 75 / 1 | 10 / 11 / 0 |

This validation diagnostic is not a promoted candidate: its development performance is deeply negative and it failed the training gate.

## Post-run cost sensitivity of the two diagnostic ledgers

The workflow's matrix-level cost_sensitivity.csv is empty because no configuration passed the training/validation gates. The following values were independently recalculated from the retained 12bp diagnostic trade ledger by scaling each trade's cost_R proportionally. They are not a full 648-configuration cost matrix.

| Diagnostic candidate / split | Cost | Win rate | PF | Net R | Max DD | Positive months |
|---|---:|---:|---:|---:|---:|---:|
| Best train-net / train | 6bp | 41.18% | 1.384 | +9.593R | -8.088R | 8/15 |
| Best train-net / train | 12bp | 41.18% | 1.029 | +0.864R | -11.682R | 7/15 |
| Best train-net / train | 20bp | 38.24% | 0.709 | -10.776R | -20.351R | 6/15 |
| Best validation-net min20 / validation | 6bp | 47.62% | 0.941 | -0.904R | -5.021R | 1/4 |
| Best validation-net min20 / validation | 12bp | 42.86% | 0.472 | -10.808R | -10.808R | 0/4 |
| Best validation-net min20 / validation | 20bp | 28.57% | 0.197 | -24.014R | -24.014R | 0/4 |

Median stop risk was 28.52bp for the best training-net diagnostic and 18.42bp for the best validation-net diagnostic. At 12bp, median cost consumed 0.42R and 0.65R respectively. Costs exceeded 0.5R on 32.4% and 81.0% of those trades; costs exceeded 1R on 5.9% and 33.3%.

## Stability and limitations

- Best training-net diagnostic: 7/15 positive months; bear-regime 12 trades +1.179R, bull-regime 22 trades -0.315R.
- Best validation-net min20 diagnostic: 0/4 positive months; bear 8 trades -3.093R and bull 13 trades -7.716R.
- No configuration met the training PF gate; the best PF was only 1.0289.
- Funding cashflows were excluded. Exact account fee tier, spread, variable slippage and market impact were not verified/modelled. The 6/12/20bp figures are flat assumed round-trip costs.
- No account sizing or capital curve. Net R is initial-stop-risk normalized and is not account return.
- The full matrix was run at 12bp; the 6/20bp sensitivity is only for the two diagnostic ledgers.
- The final OOS split was not evaluated. No threshold or parameter optimization after seeing the results.

## Decision

Reject the exact 648-configuration VWAP trend-continuation family under the frozen gates. Do not select the 6bp-only training diagnostic, widen stops, isolate a session or inspect OOS to rescue the family. The next research task should be a distinct, preregistered BTC hypothesis after a prior-art audit; this family is closed unless new independent data or a materially different hypothesis is justified.
