# Binance BTCUSDT true-footprint multi-month event study — 2026-11-19

## Decision

**Reject both exact fixed-horizon event definitions as a standalone edge at the preregistered 10 bps round-trip cost. No strategy is promoted.**

The four-month descriptive study produced 741 unique signal events (1,482 event-horizon return rows). All eight pooled family/direction/horizon groups had negative mean net returns and descriptive PF below 1.0. The 1h continuation long and short means were consistently negative in every month and their pooled event-day bootstrap 95% intervals were entirely below zero.

This is a fixed-horizon event study, not a stop-defined strategy backtest. It has no R-multiple, account PnL, funding cashflow, spread, slippage, market-impact or executable fill model. The four months are a contiguous historical descriptive sample, not an untouched future OOS period.

## Reproducibility and source data

- Event-study workflow: [44553749894](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44553749894) — all four monthly jobs and the pooled job completed successfully.
- Frozen feature-build workflow: [44513565570](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44513565570) — June–September feature gates passed.
- Preregistration: [multi-month event-study amendment](../research/BINANCE_BTCUSDT_TRUE_FOOTPRINT_MULTI_MONTH_EVENT_STUDY_PREREGISTRATION_2026-11-19.md).
- Runner: [binance_btcusdt_true_footprint_event_study.py](../research/binance_btcusdt_true_footprint_event_study.py).

| Month | 5m bars | aggTrade rows | Exact-price rows | Alignment eligible | Excluded | Volume error p95 / max | Taker-buy error p95 / max |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-06 | 8,640 | 58,149,575 | 10,543,875 | 8,188 | 452 | 0.0721% / 27.7013% | 0.0413% / 22.1748% |
| 2026-07 | 8,928 | 34,057,419 | 6,931,096 | 8,778 | 150 | 0.0060% / 36.1954% | ~0% / 4.8371% |
| 2026-08 | 8,928 | 35,676,321 | 7,371,552 | 8,823 | 105 | 0.0042% / 5.3838% | ~0% / 3.1592% |
| 2026-09 | 8,640 | 36,036,629 | 8,510,392 | 8,521 | 119 | 0.0044% / 2.6441% | 0.0007% / 7.9392% |
| **Total** | **35,136** | **163,919,944** | **33,356,915** | **34,310** | **826** | — | — |

The continuation screen required both per-bar total-volume and taker-buy relative error to be <=0.10%; 97.65% of all monthly bars passed. Absorption used official kline per-bar delta and did not depend on aggTrade-derived bar delta. The per-bar screen reduces known boundary-assignment risk but does not prove every exact-price aggTrade assignment is correct; raw-trade boundary validation remains necessary before any executable strategy claim.

## Frozen methodology

- Absorption: official kline delta fraction `(2 × taker_buy_base − total_base_volume) / total_base_volume`; z-score against the preceding 288 completed 5m bars, shifted one bar, minimum 96 prior observations, population standard deviation. Short: z >= +2 and close location <=0.25; long: z <= -2 and close location >=0.75.
- Continuation: exact 0.1 USDT price ticks; diagonal imbalance ratio >=3; numerator >=0.10 BTC; at least three consecutive ticks; close location confirms direction; event bar must pass the 0.10% per-bar alignment screen.
- 48-bar global cooldown per family across directions. First 288 and final 48 bars of each month censored. Signal at candle close; entry at next 5m open. Fixed 12-bar (1h) and 48-bar (4h) horizons, exit at corresponding horizon close.
- 10 bps round-trip deduction. 10,000 event-day-cluster bootstrap resamples per pooled family/direction/horizon.

## Pooled results at 10 bps

Each event appears once per horizon. PF and drawdown are descriptive fixed-horizon return statistics, not stop-based trade or account-equity metrics.

| Family | Direction | Horizon | Events | Win % | PF | Mean net bps | 95% event-day bootstrap CI |
|---|---|---:|---:|---:|---:|---:|---:|
| Absorption | Long | 1h | 25 | 32.00 | 0.463 | -8.15 | [-22.71, +4.52] |
| Absorption | Long | 4h | 25 | 28.00 | 0.471 | -10.35 | [-25.59, +6.51] |
| Absorption | Short | 1h | 28 | 39.29 | 0.421 | -9.23 | [-19.67, +0.68] |
| Absorption | Short | 4h | 28 | 32.14 | 0.525 | -23.58 | [-75.18, +29.85] |
| Continuation | Long | 1h | 343 | 33.24 | 0.455 | -11.01 | [-16.49, -5.43] |
| Continuation | Long | 4h | 343 | 41.98 | 0.896 | -2.91 | [-11.06, +5.79] |
| Continuation | Short | 1h | 345 | 32.75 | 0.468 | -10.98 | [-16.92, -5.00] |
| Continuation | Short | 4h | 345 | 42.90 | 0.787 | -6.79 | [-16.46, +2.47] |

## Monthly stability

Mean net event return in bps after the fixed 10 bps cost:

| Family / side | Horizon | June | July | August | September |
|---|---:|---:|---:|---:|---:|
| Absorption long | 1h | -6.65 | -2.93 | -11.06 | -10.97 |
| Absorption long | 4h | -14.56 | -17.30 | +9.38 | -19.15 |
| Absorption short | 1h | -6.58 | -5.79 | -22.45 | +1.68 |
| Absorption short | 4h | +10.14 | -13.76 | -99.23 | +14.53 |
| Continuation long | 1h | -15.94 | -12.42 | -5.96 | -10.90 |
| Continuation long | 4h | -2.81 | -8.22 | +0.47 | -1.30 |
| Continuation short | 1h | -5.49 | -7.81 | -20.12 | -11.78 |
| Continuation short | 4h | +17.91 | -12.13 | -24.58 | -11.88 |

Continuation 1h is negative in every month and both directions. The isolated positive continuation-short 4h June result did not repeat. Absorption samples are small (4–10 events per side/month) and unstable; no positive subgroup is supported.

## Files and artifacts

- Pooled output artifact: [14543313409](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44553749894/artifacts/14543313409).
- June: [14545065024](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44553749894/artifacts/14545065024).
- July: [14543678870](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44553749894/artifacts/14543678870).
- August: [14543528989](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44553749894/artifacts/14543528989).
- September: [14543544154](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44553749894/artifacts/14543544154).
- Full 32-row monthly summary: `BINANCE_BTCUSDT_TRUE_FOOTPRINT_MULTI_MONTH_EVENT_STUDY_MONTHLY_2026-11-19.csv`.
- Pooled summary: `BINANCE_BTCUSDT_TRUE_FOOTPRINT_MULTI_MONTH_EVENT_STUDY_POOLED_2026-11-19.csv`.
- Metadata: `BINANCE_BTCUSDT_TRUE_FOOTPRINT_MULTI_MONTH_EVENT_STUDY_METADATA_2026-11-19.json`.

## Next research step

Do not tune these absorption/continuation thresholds or convert the isolated positive month/side into a strategy. Close these exact fixed-horizon definitions as rejected at 10 bps.

Next crypto research candidate: frozen ETHUSDT 15m EMA20 pullback/reclaim with completed 4h EMA50/EMA200 regime, cross-exchange replication of the existing Delta event study. The existing sample was underpowered (17 ETH events; 4h mean positive but event-mean CI crossed zero). The current Binance script uses REST, which previously returned HTTP 451 from GitHub runners; adapt it to official monthly archives with checksum verification without changing signal rules. Reconcile ETH 5m versus 15m bars before any stop-defined execution study. No parameter search or production promotion.
