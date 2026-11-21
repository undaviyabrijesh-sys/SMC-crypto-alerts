# BTCUSDT USD-M premium/index-basis dislocation event study

**Classification: descriptive event study; no executable strategy or PnL.**

- Analysis: 2025-11-01 inclusive to 2026-11-01 exclusive; 12 complete UTC months.
- Warmup: 2025-10-01; prior-only 30-day basis z-score.
- Aligned analysis bars: 105,120; 13 monthly archive sets (warmup plus analysis), four series each.
- Series: contract, index, mark and premium-index klines; derived features remain distinct.

## Frozen rules

- Event: absolute prior-only 30-day rolling z-score of contract/index basis >= 2.5.
- Positive event means perpetual rich; negative event means perpetual cheap.
- Event cooldown: 245 minutes; no overlapping 4h event horizons.
- Primary outcome: signed basis reversion; positive means movement toward zero.
- Primary horizon: 1h; 15m and 4h are secondary descriptive horizons.
- Controls match split, basis side, development-defined 24h return decile, development-defined 24h realized-volatility quartile and fixed prior-24h regime.
- Nearest eligible control within +/-24h; at least 245 minutes from every event and selected control; no reuse.
- 5,000 UTC event-day cluster bootstrap replicates; intervals are descriptive, not p-values.

## Chronological splits

| Split | Start | End exclusive | Bars |
|---|---|---|---:|
| development | 2025-11-01T00:00:00+00:00 | 2026-06-11T11:15:00+00:00 | 63,072 |
| validation | 2026-06-08T00:00:00+00:00 | 2026-08-23T11:15:00+00:00 | 21,024 |
| oos | 2026-08-20T00:00:00+00:00 | 2026-11-04T11:15:00+00:00 | 21,024 |

## Results

| Split | Horizon | Events | Matched | Event reversion bps | Control reversion bps | Lift bps | 95% cluster CI |
|---|---:|---:|---:|---:|---:|---:|---:|
| development | 15m | 511 | 197 | 4.806 | 0.800 | 4.007 | 3.591 to 4.372 |
| development | 1h | 511 | 197 | 4.903 | 0.647 | 4.256 | 3.649 to 4.502 |
| development | 4h | 511 | 197 | 5.088 | 0.791 | 4.296 | 3.729 to 4.628 |
| validation | 15m | 136 | 81 | 3.602 | 0.744 | 2.857 | 2.491 to 3.532 |
| validation | 1h | 136 | 81 | 3.777 | 0.568 | 3.208 | 2.787 to 3.853 |
| validation | 4h | 136 | 81 | 3.872 | 0.597 | 3.276 | 2.920 to 3.999 |
| oos | 15m | 171 | 66 | 4.175 | 0.615 | 3.560 | 2.860 to 4.359 |
| oos | 1h | 171 | 66 | 4.380 | 1.057 | 3.324 | 2.720 to 4.164 |
| oos | 4h | 171 | 66 | 4.542 | 0.700 | 3.842 | 3.332 to 4.721 |

## Decision

**candidate_for_separate_execution_preregistration**

The preregistered gate uses the primary 1h horizon: at least 30 matched pairs in each split, positive mean paired lift in development/validation/OOS, and a positive lower bound of the OOS event-day cluster-bootstrap interval. This is a screening rule, not a formal significance test.

## Costs and trading metrics

No position, entry, stop, target or execution is simulated. Fees, spread, slippage and funding are not applicable. Win rate, PF, net R, trading drawdown and losing streak are not applicable. Any later execution strategy requires a separate preregistration with actual funding, fees/slippage and conservative intrabar handling.

## Data integrity and limitations

- All 52 monthly archive ZIPs and sibling SHA-256 checksums are verified. If a monthly archive has only complete missing UTC days, the exact corresponding daily archive is checksum/CRC/schema/row/boundary verified and used as a deterministic patch; partial-day gaps fail closed. Final month grids and four-series alignment must be complete.
- October 2025 is warmup only; event sample begins 1 November 2025.
- Premium-index close is not assumed equal to contract/index basis or mark/index premium.
- Binance REST cross-check is unavailable from the prior runner due HTTP 451; no REST parity claim is made.
- Matching controls observable context but does not prove causality; cluster intervals may not remove all serial dependence.
- No threshold/lookback/cooldown/horizon grid was run; definitions were frozen before the full download.
