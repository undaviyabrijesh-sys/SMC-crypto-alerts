# ETHUSDT 15m Supertrend intraday cross-asset replication — authoritative result

Date: 2026-11-20  
Workflow: [44693535437](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44693535437)  
Branch: `ai-quant-rebuild`  
Decision: **Rejected — development and validation gates failed; no OOS evaluation.**

## Frozen rule

- Binance USD-M ETHUSDT perpetual, 15-minute official klines.
- HL2 Supertrend, Wilder ATR(10), multiplier 3.0.
- Confirmed direction flip at completed candle close; enter next 15-minute open.
- Both directions, all UTC hours, no trend/session filter.
- Stop at the signal candle's Supertrend line; fixed 2R target.
- Maximum 16 bars / four hours; one position at a time.
- Funding screen used in this run: exclude an entry if the full four-hour maximum holding window reaches or crosses the assumed default 00:00/08:00/16:00 UTC grid. This is not a verified historical settlement schedule. No funding cashflow is imputed.
- Inherited simulator guard: reject non-positive initial risk or stop distance greater than 5% of entry.
- Same-bar stop/target ambiguity is stop-first; adverse gap-through stop fill; no trades cross a data gap or split.
- Primary assumed cost: 12 bps round trip; sensitivity at 6 and 20 bps. This is not a verified account fee tier and does not separately model spread, variable slippage or market impact.
- R is normalized by initial stop distance, not account return.

## Verified data

- 53/53 official Binance archive SHA-256 checksums verified.
- 38 daily and 15 monthly archives.
- 47,424 15-minute bars from 2025-03-08 00:00 UTC through 2026-07-14 23:45 UTC.
- Zero missing/irregular 15-minute intervals and zero zero-volume rows.
- Source SHA-256: `9f6379bb53003daa04779960095af65065127aa89f9ed46f4016d8cd28c50f59`.
- Reserved segment begins 2026-05-01 21:30 UTC. It is retired/contaminated and was not evaluated.

## Chronological splits

| Split | First bar | Last bar |
|---|---|---|
| Development | 2025-03-08 00:00 UTC | 2026-02-16 18:45 UTC |
| Validation | 2026-02-16 19:00 UTC | 2026-05-01 21:15 UTC |
| Retired holdout | 2026-05-01 21:30 UTC | 2026-07-14 23:45 UTC |

The final 15% was accidentally materialized during local preflight before the gates were applied. It is explicitly retired. No performance metrics are reported for it and it cannot be used for an OOS claim.

## Primary results — 12 bps round trip

| Metric | Development | Validation |
|---|---:|---:|
| Trades | 332 | 75 |
| Profitable trades | 43.07% | 37.33% |
| Profit factor | 0.789 | 0.748 |
| Net R | -24.25R | -8.26R |
| Average net R/trade | -0.073R | -0.110R |
| Maximum drawdown | -28.58R | -18.42R |
| Maximum losing streak | 13 | 11 |
| Positive active months | 2/12 | 1/3 |
| TP / SL / TIME | 22 / 58 / 252 | 6 / 18 / 51 |
| Long / short | 151 / 181 | 39 / 36 |

Independent recalculation from the saved trade ledgers reproduced trade count, win rate, PF, net R, average R, drawdown, losing streak and exit counts. No duplicate entry timestamps or overlapping positions were found.

## Gross edge versus cost burden

| Metric | Development | Validation |
|---|---:|---:|
| Gross R | +4.393R | -0.783R |
| Gross mean R/trade | +0.0132R | -0.0104R |
| Gross PF | 1.044 | 0.972 |
| Total assumed cost | 28.640R | 7.477R |
| Median cost/trade | 0.0767R | 0.0888R |
| 90th percentile cost/trade | 0.1377R | 0.1598R |

Development had only a marginal gross advantage and lost after even the optimistic 6 bps assumption. Validation was negative before costs.

## Cost sensitivity

| Split | Cost | Trades | Win rate | PF | Net R | Max DD | Losing streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Development | 6 bps | 332 | 43.98% | 0.907 | -9.93R | -17.34R | 13 |
| Development | 12 bps | 332 | 43.07% | 0.789 | -24.25R | -28.58R | 13 |
| Development | 20 bps | 332 | 39.16% | 0.657 | -43.34R | -44.54R | 13 |
| Validation | 6 bps | 75 | 40.00% | 0.851 | -4.52R | -15.29R | 11 |
| Validation | 12 bps | 75 | 37.33% | 0.748 | -8.26R | -18.42R | 11 |
| Validation | 20 bps | 75 | 36.00% | 0.634 | -13.24R | -22.59R | 11 |

## Monthly and regime stability

Only 2 of 12 development months and 1 of 3 validation months were positive at 12 bps. Development's positive months were August 2025 (+2.57R) and December 2025 (+8.73R); validation's only positive month was February 2026 (+8.64R). March and April 2026 were -7.16R and -9.75R.

All completed-4H bull, bear and neutral attribution groups were negative in validation:
- Bear: 31 trades, PF 0.791, -2.70R.
- Bull: 14 trades, PF 0.586, -2.96R.
- Neutral: 30 trades, PF 0.795, -2.60R.

No regime filter is justified by this sample.

## Funding-selection limitation

There were 1,043 raw flips. The **assumed default-8h grid screen** removed 543 (52.06%) and left 500 signals for this conditional replay; the inherited 5% risk guard rejected three more. Exclusions were concentrated in entry hours 04–07, 12–15 and 20–23 UTC, materially changing the session mix. Binance USD-M funding settlement intervals can change to hourly and four-hour schedules; the official funding history exposes the actual per-event `fundingTime`, `fundingRate` and associated `markPrice`. Therefore the 543/500 counts are not verified actual-settlement counts, and this replay is not funding-aware. See [Binance funding history API](https://developers.binance.info/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) and [Binance interval-change notice](https://www.binance.com/en/square/post/23518010224298).

## Execution audit

- Development: 0 first-touch bars with both stop and target touched; 0 adverse stop-gap fills.
- Validation: 0 first-touch bars with both stop and target touched; 0 adverse stop-gap fills.
- Independent trade-ledger audit: zero duplicate entry times and zero overlapping positions in both splits.

## Decision and next step

Do not promote this ETH Supertrend baseline. The tested default-grid subset fails development and validation gates, has weak gross expectancy, poor month/regime stability and does not survive the 6 bps sensitivity. This is a rejection of the tested proxy implementation, not a complete funding-aware assessment of every raw flip. Do not tune the same validation sample or inspect the retired holdout.

Next diagnostic: replay the unchanged signals/entries/exits against actual Binance funding events and associated mark prices, report exact funding cashflows plus conservative bounds for funding events falling inside an OHLC exit bar, and compare with the default-grid exclusion. This is an accounting correction only, not a strategy rescue or OOS evaluation.

The successful workflow produced the 12-file artifact `ethusdt-supertrend-intraday-replication-2026-11-20.zip`; the saved trade ledgers and supporting tables are retained there. No strategy was promoted, no live alerts were sent and no orders were placed.
