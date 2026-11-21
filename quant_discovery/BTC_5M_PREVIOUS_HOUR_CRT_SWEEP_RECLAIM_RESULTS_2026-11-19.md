# BTC 5m previous-hour CRT-style sweep/reclaim — results

**Run date:** 2026-11-19. **Decision:** reject all eight tested configurations. No OOS evaluation and no promotion. Post-run ledger audit found prior CRT v1/v2/v3 studies using 15m execution with 1H/4H/1D/weekly ranges. This is a 5m execution-resolution variant within that existing family, not a new independent family; the prior-art check should have happened before execution.

## Data and verification

- 210,239 Delta BTCUSD 5-minute candles, 2024-11-16 11:30 UTC to 2026-11-16 11:20 UTC.
- Source SHA-256: 5b612e1c496f16277b459f58ddff33b69d8f7912b70d8f733f0a17be844eb4fb.
- Zero missing intervals; zero invalid OHLC rows; 17,519 complete UTC hourly reference candles.
- Eight configurations × five cost assumptions; 80 summary rows and 38,228 configuration-trade rows across development/validation (not unique independent signals across configurations).
- Five deterministic tests passed. Independent audit reconstructed every summary metric with maximum absolute difference 0, found no overlapping positions within a configuration, verified cooldowns and funding-boundary flattening. A clean second execution reproduced seven principal outputs byte-for-byte.

## Least-negative configuration at 10 bps

The least-negative 10 bps configuration was close0.25_next_bar_break_range. This is a diagnostic ranking, not a successful strategy.

| Metric | Development | Validation |
|---|---:|---:|
| Trades | 3,001 | 659 |
| Win rate | 28.56% | 25.80% |
| Profit factor | 0.287 | 0.278 |
| Net R | -2,586.739R | -617.590R |
| Average R/trade | -0.862R | -0.937R |
| Maximum drawdown | -2,588.857R | -617.590R |
| Longest losing streak | 23 | 16 |
| Positive months | 0/18 | 0/4 |

Across all eight configurations at 10 bps:
- Development PF 0.254–0.312; net R -2,586.739R to -4,057.627R.
- Validation PF 0.177–0.293; net R -617.590R to -883.027R.
- Every configuration had zero positive months in development and validation.
- Longest losing streak: 19–23 development; 11–18 validation.

## Cost sensitivity

At 4 bps, all configurations still lost: development PF 0.548–0.607; validation PF 0.441–0.611. At 0 bps, PF was only 0.942–1.011 in development and 0.835–1.062 in validation; small positive net R appeared in different configurations in the two partitions, with no stable winner.

Median initial stop risk was 16.30 bps of entry price; the 10th percentile was 6.43 bps. A 10 bps round-trip cost therefore consumed about 0.61R at median risk and 1.55R at the 10th-percentile risk.

## Regime and monthly stability

For the least-negative 10 bps configuration:

| Split | Regime | Trades | PF | Net R |
|---|---|---:|---:|---:|
| Development | Bear | 1,286 | 0.313 | -993.499R |
| Development | Bull | 1,219 | 0.295 | -1,035.844R |
| Development | Neutral | 443 | 0.216 | -501.506R |
| Validation | Bear | 278 | 0.369 | -220.498R |
| Validation | Bull | 286 | 0.180 | -307.950R |
| Validation | Neutral | 95 | 0.313 | -89.142R |

No active month was positive at 10 bps for this configuration (0/18 development; 0/4 validation). The same zero-positive-month result held for all eight configurations.

## Decision

All eight configurations failed the development/validation screening gate encoded in the script; this was not a separately timestamped GitHub preregistration. The final 15% was not evaluated. Do not tune these thresholds against validation or OOS. This mechanical prior-hour range sweep/reclaim definition is rejected under the stated assumptions; this does not disprove every discretionary or higher-timeframe CRT implementation.

Full code, source data, trade ledger and audit are in the downloadable research package. This CRT run was executed locally; no GitHub Actions execution is claimed.
