# BTC/ETH 15m EMA20 pullback + completed 4h trend bias — cross-asset event study

**Run date:** 2026-11-17  
**Status:** exploratory BTC timing variation + frozen ETH replication; not validated  
**Branch:** ai-quant-rebuild only  
**Final holdout:** not loaded into features or evaluated

## Motivation and frozen rule

The repository already contains a 1h EMA20 pullback event study with completed 4h EMA50/EMA200 regime; it was underpowered. This study tests one narrower timing variation, not a new independent strategy family: retain the 4h regime, identify the pullback/reclaim on a completed 15m candle, and enter at the next bar open. BTC was exploratory; the exact rule was then frozen and replicated on ETH without parameter changes.

- Bull regime: completed 4h close > EMA50 > EMA200. Bear regime: completed 4h close < EMA50 < EMA200. The 4h context is available only at its right-edge close.
- Long: previous 15m close <= previous EMA20; current 15m low within ±0.10 × Wilder ATR(14) of EMA20; current close > EMA20 and > open; completed 4h regime bull. Short is the inverse in a bear regime.
- Entry: next 15m open. BTC uses the first 5m open at the same timestamp; ETH uses native next-15m open.
- One global event per 8h; fixed 1h/4h forward-return horizons; no stop/target fitting.
- Evaluate only after the 2025-09-08 12:00 UTC funding-grid transition. Exclude any 4h outcome that reaches or exceeds the next 00:00/08:00/16:00 UTC settlement. No funding cashflow applied.
- Controls: one deterministic non-signal control per event, same UTC day, side, completed 4h regime and 3h UTC bucket; without replacement; exclude raw qualifying signals and controls within ±1h of any raw signal.
- Cost sensitivities: 4/7/10/20 bps round trip; 10 bps primary.

## Data

| Item | BTC | ETH |
|---|---:|---:|
| Source | Delta BTCUSD 5m traded-price | Delta ETHUSD native 15m traded-price |
| Rows | 210,239 | 70,127 |
| Coverage | 2024-11-16 11:30 to 2026-11-16 11:20 UTC | 2024-11-15 07:30 to 2026-11-15 19:00 UTC |
| Missing intervals | 0 | 0 |
| Zero-volume rows | 334 | 85 |
| SHA-256 | 5b612e1c496f16277b459f58ddff33b69d8f7912b70d8f733f0a17be844eb4fb | f58ce4233c5d7242974e460d811198c03614e113c6097805884ac580ebd8b95a |
| Evaluation | 2025-09-08 12:00 to 2026-07-16 00:00 UTC | 2025-09-08 12:00 to 2026-07-15 00:00 UTC |
| Final holdout starts | 2026-07-16 | 2026-07-15 |

Both use a six-month indicator warm-up and two-month chronological folds. Final four months were excluded before feature construction/evaluation; no OOS result exists.

### BTC feed discrepancy

Native BTC 15m versus 15m bars aggregated from BTC 5m: 19 OHLC mismatches among 70,015 common bars (99.9729% exact agreement); nine mismatches fell inside the evaluation period. Maximum absolute differences: $1,611 open, $517 high, $198 low. BTC used 5m-derived 15m bars; native BTC 15m was retained only for audit. ETH uses native 15m and was not independently reconciled against ETH 5m in this run.

## Results at 10 bps round-trip cost

Fixed-horizon event diagnostics on matched samples, not executable trade statistics. PF is descriptive on fixed-horizon returns; drawdown is cumulative event-return sequence in bps, not account-equity DD. R is not applicable without a stop-defined risk unit.

| Asset / horizon | Events | Matched | Win | Descriptive PF | Mean net | Median net | Control mean | Paired lift | 95% day-cluster CI for lift |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC 1h | 23 | 17 (73.9%) | 35.3% | 0.753 | -2.89 bps | -9.91 | -1.86 | -1.03 | [-20.24, 19.61] |
| BTC 4h | 23 | 17 (73.9%) | 41.2% | 2.892 | +29.60 bps | -4.09 | +0.32 | +29.28 | [4.89, 55.72] |
| ETH 1h | 17 | 15 (88.2%) | 40.0% | 0.718 | -9.40 bps | -20.92 | -2.17 | -7.23 | [-71.23, 44.69] |
| ETH 4h | 17 | 15 (88.2%) | 46.7% | 2.283 | +35.51 bps | -5.13 | -6.49 | +42.00 | [-22.31, 113.22] |

The 4h event-mean CIs include zero on both assets: BTC [-12.18, 81.29] bps; ETH [-21.36, 104.06] bps.

| Asset / horizon | Positive months | Positive 2m folds | Event-sequence DD | Max losing streak |
|---|---:|---:|---:|---:|
| BTC 1h | 2/9 | 2/5 | -103.85 bps | 4 |
| BTC 4h | 5/9 | 3/5 | -166.98 bps | 5 |
| ETH 1h | 3/9 | 2/5 | -458.62 bps | 4 |
| ETH 4h | 4/9 | 3/5 | -328.28 bps | 5 |

The 4h median is negative on both assets and the mean is right-tailed. Removing each asset's largest 4h event reduces the matched event mean from +29.60 to +10.24 bps on BTC and +35.51 to +15.20 bps on ETH. Most matched events were shorts in bear regimes (BTC 10 short/7 long; ETH 14 short/1 long); do not select a side post hoc.

At 20 bps assumed round-trip cost, 4h event mean remains +19.60 bps BTC and +25.51 bps ETH; 1h is -12.89 and -19.40 bps. These are price-return sensitivities, not funding-inclusive perp PnL.

## Decision

**Not validated.** Both 1h results are negative. The 4h paired-lift point estimates are positive, but the ETH paired-lift interval and both absolute event-mean intervals include zero; samples are only 17 and 15 matched events, medians are negative, and results are concentrated in short/bear observations and a heavy right tail. No stop-defined R, executable PnL or final-holdout result exists. Do not tune sides, stops or targets against this sample.

## Next step and reproducibility

Obtain ETH 5m (or trade-level) data and reconcile it to the existing ETH 15m series. Only if the frozen signal survives finer-resolution replication with adequate sample should a stop-defined execution study follow. Full scripts, source CSVs, event/control ledgers, folds, cost sensitivity and data reconciliation are in the downloadable research package.

Deterministic tests passed: complete-bar aggregation, future-perturbation invariance, completed-4h context availability, settlement-grid handling and forward-return direction.