# Binance BTCUSDT 1H EMA20/50 cross-exchange replication — results

**Run:** GitHub Actions 44451403028 — success  
**Artifact:** binance-btcusdt-1h-ema20-50-cross-exchange-2026-11-19.zip  
**Artifact SHA-256:** aaf3d5502895be6b89628f2b04ac672451e0882b2b27e1e50eef18b0b4a89623  
**Decision:** reject for promotion; retain as experimental evidence only.

## Frozen hypothesis and rules

This was a single-configuration, preregistered venue replication of the Delta candidate: completed 1H EMA20/EMA50 crossover, next 1H open entry, 1.5 × Wilder ATR14 stop anchored to signal close, fixed 3R target, both directions, no higher-timeframe entry filter, one position at a time. No Binance parameter search was performed.

The same repository feature and execution engine used for the Delta study was reused. Binance 5-minute klines were aggregated into complete UTC 1H bars. Actual Binance fundingTime records defined the next settlement; positions were exited at the last complete 1H close strictly before settlement. No funding cashflow was applied because no position crossed a settlement.

## Data integrity

- Binance USD-M BTCUSDT: 191,160 5-minute rows, 0 missing 5-minute intervals.
- Complete 1H bars: 8,814, 0 missing hourly intervals.
- Warm-up began 2024-11-16 00:00 UTC; evaluation began 2025-09-08 12:00 UTC.
- 23 monthly kline archives and 13 monthly funding archives were downloaded; all 36 ZIP checksums verified against Binance public-data CHECKSUM files.
- Funding records: 1,102; maximum observed interval 8.0000044 hours (timestamp precision jitter); 0 trade/funding overlaps.
- Source 5m CSV SHA-256: 62f01bab9589eec20d7db9e202ef67ea466b3269288e9b507671be67f47599a1
- Funding CSV SHA-256: 1fd908846d2a6b3ba5f0078292cd7f36e89c850793484ca80d7891c3ef53dca9

## Chronological partitions

- Development: [2025-09-08 12:00, 2026-07-07 13:00) UTC.
- Validation: [2026-07-07 13:00, 2026-09-10 06:00) UTC.
- Final OOS after 2026-09-10 06:00 UTC was not evaluated.
- A 12-hour data buffer through 2026-09-10 18:00 UTC was used only to establish the next funding boundary and reject trades that would cross a partition. No post-validation signals or trades were simulated.

This is cross-exchange evidence on overlapping dates, not independent temporal OOS.

## Primary results — 10 bps round-trip cost

| Split | Trades | Win rate | PF | Net R | Avg R/trade | Max DD | Max losing streak | Positive months |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Development | 94 | 40.43% | 0.933 | -2.27R | -0.024R | -10.80R | 7 | 6/11 |
| Validation | 24 | 62.50% | 2.953 | +8.57R | +0.357R | -1.57R | 4 | 2/3 |

### Cost sensitivity

| Split | 4 bps | 7 bps | 10 bps | 20 bps |
|---|---:|---:|---:|---:|
| Development net R | +4.53R | +1.13R | -2.27R | -13.59R |
| Validation net R | +10.58R | +9.57R | +8.57R | +5.20R |

Development breaks below zero between 7 and 10 bps. Validation remains positive at 20 bps, but has only 24 trades and three active months.

### Exit-type and stability diagnostics

- Development: 2 target exits, 19 stop exits, 73 time exits.
- Validation: 1 target exit, 1 stop exit, 22 time exits.
- Development positive months: 6/11. Validation: 2/3.
- Validation monthly net R: July 2026 +6.54R, August -0.36R, September +2.38R.
- Development side attribution: long +1.68R; short -3.94R.
- Validation side attribution: long +3.66R; short +4.91R.
- Development 4H-regime attribution: bear -1.87R; bull -0.40R.
- Validation 4H-regime attribution: bear +2.14R; bull +6.43R.

The 3R target was rarely reached; most positions exited at the funding-safe time limit. This makes the result primarily a short-horizon directional drift test, not evidence that the 3R target is being achieved consistently.

## Independent artifact audit

The downloaded 118-trade ledger was independently recalculated:
- Both split summaries reconcile exactly to the published CSV after rounding.
- No overlapping positions within either split.
- Every exit timestamp is strictly before its recorded next fundingTime.
- Zero funding-settlement overlaps.
- Development and validation trades do not cross their respective split boundaries.

## Cluster bootstrap uncertainty audit

50,000 resamples per unit, resampling active UTC day/week/month clusters with replacement and preserving all trades within a selected cluster. Net R is after 10 bps round-trip cost.

### Mean net R per trade — 95% intervals

| Split | Day clusters | Week clusters | Month clusters |
|---|---:|---:|---:|
| Development | [-0.1935, +0.1647] | [-0.1719, +0.1380] | [-0.1723, +0.1788] |
| Validation | [-0.0295, +0.8277] | [+0.0664, +0.7762] | [-0.0446, +0.5958] |

Validation bootstrap probability of positive mean: day 96.34%, week 99.47%, month 96.35%. However, the 3-month interval still crosses zero; validation has only 21 active days and 10 active weeks. Its three largest winners contribute 57.78% of all positive R.

Development bootstrap probability of positive mean was only 37.82%–39.00%, with all intervals crossing zero. PF intervals cross 1 in development and in validation day/month resamples. These are descriptive cluster-bootstrap diagnostics, not proof of an edge and not a cure for the earlier 24-configuration screening.

## Decision

**Reject for promotion.** The frozen candidate again loses in development at 10 bps, on both Delta (-1.90R) and Binance (-2.27R). Both venues show a positive but small validation sample, with much of the result concentrated in a few time clusters/winners. The cross-exchange replication confirms the validation-only pattern rather than establishing robust edge.

No parameter changes were made. Do not tune this candidate against the inspected validation period. A genuinely future holdout and prospective paper-trading period would still be required even if later evidence improves.

## Execution blocker and resolution

The first GitHub Actions attempt using Binance REST endpoints failed with HTTP 451 from the runner environment. The pipeline was changed to use Binance's official public monthly archives and verify each ZIP against its matching SHA-256 CHECKSUM file. The final run succeeded with all 36 archive checksums verified.

## Reproducibility

- Workflow: https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44451403028
- Frozen preregistration: research/BINANCE_BTCUSDT_1H_EMA20_50_CROSS_EXCHANGE_PREREGISTRATION_2026-11-19.md
- Runner: research/binance_btcusdt_1h_ema_crossover_replication.py
- Bootstrap audit: research/bootstrap_binance_btc_ema20_50_replication.py
- Full artifact contains source 5m candles, funding rates, archive manifest, trade ledger, summary, monthly, regime, side, cost sensitivity and metadata.
