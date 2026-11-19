# BTC 1H EMA20/50 candidate — clustered uncertainty audit

**Date:** 2026-11-19 UTC  
**Scope:** Statistical robustness audit of the already-tested Delta candidate; no new trading parameters or backtest entries were introduced.  
**Candidate:** EMA20/EMA50 crossover, 1.5 × Wilder ATR14 stop, 3R target, no 4H filter, both directions, 10 bps round-trip cost.

## Source and reproducibility

- Source ZIP: btc_1h_ema_crossover_funding_safe_research_2026-11-18.zip
- Source member: ema_cross_research/results/trades_dev_val_10bps.csv
- Source SHA-256: 6464234b5f85c276fa2937ad6817b72070ad4f940f7ddf9e874edecf723d3686
- Candidate trade rows: 133 (106 development, 27 validation).
- Bootstrap: 50,000 resamples per cluster unit; resample active clusters with replacement, preserving all trades within each selected cluster.
- Seeds: day 20261119, week 20261120, month 20261121.
- Returns are net R after 10 bps assumed round-trip cost.

## Point estimates

| Split | Trades | Active days | Active weeks | Active months | Net R | Mean R/trade | Win rate | PF | Top 3 winners / positive R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Development | 106 | 86 | 41 | 11 | -1.8966 | -0.0179 | 41.51% | 0.9505 | 22.89% |
| Validation | 27 | 23 | 10 | 3 | +7.9900 | +0.2959 | 62.96% | 2.3380 | 53.91% |

## Cluster bootstrap — mean net R per trade, 95% interval

| Split | Day clusters | Week clusters | Month clusters |
|---|---:|---:|---:|
| Development | [-0.1832, +0.1609] | [-0.1659, +0.1437] | [-0.1691, +0.1885] |
| Validation | [-0.0649, +0.7343] | [-0.0002, +0.6950] | [-0.2127, +0.6422] |

All three validation intervals include zero or touch it within rounding. Development point expectancy is negative, and all three development intervals include zero.

## Bootstrap probability of positive mean net R

| Split | Day | Week | Month |
|---|---:|---:|---:|
| Development | 40.82% | 41.06% | 42.01% |
| Validation | 94.12% | 97.50% | 85.10% |

The validation point estimate is encouraging but unstable: only 27 trades, 23 active days and three active months. Its three largest winners account for 53.91% of all positive R.

## Profit-factor uncertainty

| Split | Day PF 95% CI | Week PF 95% CI | Month PF 95% CI |
|---|---:|---:|---:|
| Development | [0.559, 1.535] | [0.595, 1.465] | [0.575, 1.624] |
| Validation | [0.800, 9.283] | [0.999, 7.162] | [0.475, 5.932] |

The wide validation PF intervals are consistent with a small, concentrated sample. The monthly bootstrap has only three validation clusters and is therefore a coarse sensitivity check, not a precise confidence statement.

## Decision

**Do not promote.** The development net result is negative at 10 bps; all development mean-R intervals straddle zero; the validation result is concentrated in a few winners and has very wide PF uncertainty. This supports retaining the candidate as an experimental research lead only.

No parameter changes were made and no validation/OOS observations were used for tuning. A genuine prospective period and independent future holdout would still be required even if a cross-exchange replay looked better.

## Limitations

- Cluster bootstrap is descriptive and cannot repair selection bias from screening 24 configurations.
- Day/week/month blocks capture some dependence but do not fully model regime shifts or all serial dependence.
- The validation contains only three active months; month-cluster inference is weak.
- These results are from the existing trade ledger, not a fresh execution backtest.
