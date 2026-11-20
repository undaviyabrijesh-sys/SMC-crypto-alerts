# ETHUSDT Supertrend — actual funding cashflow audit preregistration

Date: 2026-11-20  
Parent run: [authoritative Supertrend replay 44693535437](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44693535437)  
Branch: `ai-quant-rebuild`  
Type: execution-accounting correction only; **not** a new strategy search or promotion test.

## Motivation

The parent replay excluded signals using an assumed default UTC funding grid of 00:00/08:00/16:00. Binance USD-M funding intervals can change to hourly or four-hour schedules. The official funding history API provides actual per-event `fundingTime`, `fundingRate` and the mark price associated with the funding charge. The parent replay's 543 excluded / 500 remaining signals are therefore proxy counts, not verified funding-safe counts.

Official references:
- [Binance USD-M Get Funding Rate History](https://developers.binance.info/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)
- [Binance funding interval-change notice, 25 April / effective 2 May 2025](https://www.binance.com/en/square/post/23518010224298)
- [Binance funding-rate FAQ and subsequent interval updates](https://www.binance.com/az-AZ/support/faq/detail/360033525031)

## Frozen strategy rules — unchanged

- Binance USD-M ETHUSDT, 15-minute bars from the verified parent source file.
- HL2 Supertrend, Wilder ATR(10), multiplier 3.0.
- Confirmed direction flip on completed 15m candle; entry next 15m open.
- Both directions, all UTC hours, no trend/session filter.
- Stop at signal candle Supertrend line; fixed 2R target.
- Maximum 16 bars / four hours; one position at a time.
- Inherited simulator guard: skip non-positive initial risk or stop distance greater than 5% of entry.
- Primary transaction cost remains assumed 12 bps round trip; sensitivities 6 and 20 bps.
- Same-bar stop-first and adverse stop-gap handling remain unchanged.

## Funding data and verification

- Obtain ETHUSDT official USD-M historical funding-rate records for the parent candle window, preferably checksum-verified monthly `fundingRate` archives under `data/futures/um/monthly/fundingRate/ETHUSDT/`.
- Require actual event timestamp, rate and associated mark price. If archives omit mark price, use the official `GET /fapi/v1/fundingRate` endpoint with inclusive start/end pagination (max 1,000 records per page); never synthesize a mark price.
- Validate monotonic unique `fundingTime`, finite rates, positive mark prices, archive checksums/CRC, coverage from before the first entry through the last possible exit, and the empirical distribution of adjacent settlement intervals. Do not assume 8h.
- Persist funding source SHA-256, archive manifest, row count, exact first/last event times and interval histogram.

## Funding cashflow calculation

For unit ETH quantity, each actual settlement event while a position is open has quote-currency funding cashflow:

`cashflow_quote = -side_sign * markPrice * fundingRate`

where `side_sign=+1` for long and `-1` for short. Convert to initial-risk R using the trade's per-unit stop risk:

`funding_R = cashflow_quote / abs(entry - stop)`

Positive funding means longs pay and shorts receive; negative funding reverses the sign. Sum all event cashflows for the trade and add them to gross R before subtracting the existing transaction-cost R.

## Settlement boundary convention

- A settlement strictly after entry and strictly before the exit bar's open is definitely inside the position interval and is charged.
- A settlement exactly at entry time is treated as post-settlement entry in the lower bound and charged only in the conservative upper bound.
- A settlement inside the 15m exit candle is ambiguous for TP/SL OHLC exits because the intrabar exit time is unknown: no charge in the lower bound, charge in the upper bound. For TIME exits, the position remains open through the final candle close and the settlement is charged if it occurs before that close.
- Report ambiguous-event count and lower/upper funding_R separately. Do not collapse ambiguity to a falsely precise point estimate.

## Evaluation

- Re-run the same raw 1,043 flips with no fixed 00/08/16 exclusion, preserving the exact parent development/validation row boundaries.
- Final 15% holdout remains retired and **must not be evaluated**.
- Report raw flips, risk-guard exclusions, trades by split, actual settlements per trade, interval distribution, long/short funding paid/received, funding_R lower/upper, gross R, transaction cost R, net R lower/upper, win rate, PF, drawdown, losing streak, monthly and completed-4H regime breakdown.
- Compare actual-event cashflow results with the parent default-grid subset only as an execution-accounting diagnostic.
- No threshold, ATR, target, stop, session, direction or holding-period tuning. No selection of a best variant. No strategy promotion.
- If official historical mark prices or full funding coverage cannot be verified, stop the PnL replay and report the precise missing field/period.

## Deliverables

- Reproducible script and deterministic tests for rate sign, long/short direction, mark-price notional, entry/exit boundary cases, hourly/four-hour interval changes, multiple settlements in one trade, missing mark price, duplicate/missing funding records and split isolation.
- Official funding data manifest and normalized funding-event CSV.
- Development/validation funding-aware trade ledger and summary, with lower/upper ambiguity bounds.
- Updated research ledger and Quant Terminal metadata.
